# ==========================================
# 🤖 Discord Bot 本体（discord.py）
# ==========================================
# 📝 Intents は必要最小限（Guilds のみ、特権インテントは使わない）。
# コマンドは2つ: メッセージのコンテキストメニュー「Make it a Quote」と
# スラッシュコマンド /quote。どちらも生成画像に削除ボタンを付け、
# 生成を監査アーカイブへ残し、実行ログを1行出す。
from __future__ import annotations

import asyncio
import io
import time
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands

from .archive import archive_dir, archive_enabled, save_quote_archive
from .config import Config
from .execution_log import log_execution
from .renderer import fallback_avatar, image_from_bytes, render_quote_image
from .watchdog import watchdog_loop

QUOTE_MAX_CHARS = 300  # 名言テキストの最大文字数

# ------------------------------------------
# 🎮 プレゼンス・サイクル（全 Bot 共通仕様）
# ------------------------------------------
# 📝 Playing で1分ごとに次の2パターンを交互に表示する。
#   経過時間: <Bot名> | 起動して 1時間26分（起点はログイン完了時）
#   現在時刻: <Bot名> | 現在時刻 19:24 JST
# 値は「次の分の境界時点」のものを計算し、境界の 200ms 前に先行送信する
# （Discord のプレゼンス伝播遅延の実測中央値 190ms と相殺する）。
# 位相は Unix 分の偶奇で決まるため、全 Bot が同時に切り替わる。
PRESENCE_SEND_LEAD_MS = 200  # 分の境界より何 ms 早く送信するか


def format_elapsed_minutes(ms: float) -> str:
    """経過時間を分粒度で整形する（1時間26分 / 26分 / 0分）。"""
    total_minutes = max(0, int(ms // 60_000))
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}時間{minutes:02d}分" if hours > 0 else f"{minutes}分"


def presence_cycle_text(bot_name: str, started_at_ms: int, at_ms: int) -> str:
    """時刻 at_ms におけるプレゼンス文字列を返す（Unix 分の偶奇で位相が決まる）。"""
    phase = (at_ms // 60_000) % 2
    if phase == 1:
        jst = datetime.fromtimestamp(at_ms / 1000, tz=timezone.utc) + timedelta(hours=9)
        return f"{bot_name} | 現在時刻 {jst:%H:%M} JST"
    return f"{bot_name} | 起動して {format_elapsed_minutes(at_ms - started_at_ms)}"


def next_presence_send(now_ms: int) -> tuple[int, int]:
    """次の分の境界と、その値で先行送信すべき時刻を返す。

    送信予定時刻を過ぎている場合は翌分の境界へ前進する（過ぎた予定で
    即時発火を繰り返すと送信を連打して Gateway レート制限にかかるため）。
    """
    boundary = (now_ms // 60_000) * 60_000 + 60_000
    send_at = boundary - PRESENCE_SEND_LEAD_MS
    if send_at <= now_ms:
        boundary += 60_000
        send_at = boundary - PRESENCE_SEND_LEAD_MS
    return send_at, boundary


# ------------------------------------------
# 🗑️ 名言画像の削除ボタン
# ------------------------------------------
# 🗑️ 生成した名言画像には削除ボタンを付ける。押せるのは
# - 引用された本人（ユーザーIDを使用された人: /quote の user、右クリック経路では元の発言者）
# - 画像を作成した人（コマンドを実行した人）
# の2人だけ。それ以外の人が押した場合は削除せず、その旨を ephemeral で返す。
# ボタンの custom_id に両者の ID を埋め込み、DynamicItem で受け付けるので、
# Bot を再起動しても（ボタンの状態をメモリに持たなくても）判定・削除できる。
QUOTE_DELETE_CUSTOM_ID_PREFIX = "quote-delete"  # 削除ボタンの custom_id の接頭辞


def build_quote_delete_custom_id(quoted_user_id: int, requester_id: int) -> str:
    """削除ボタンの custom_id を組み立てる。"""
    return f"{QUOTE_DELETE_CUSTOM_ID_PREFIX}:{quoted_user_id}:{requester_id}"


def parse_quote_delete_custom_id(custom_id: str) -> tuple[int, int] | None:
    """削除ボタンの custom_id から両者のユーザーIDを取り出す。不正な形式なら None。"""
    parts = custom_id.split(":")
    if len(parts) != 3 or parts[0] != QUOTE_DELETE_CUSTOM_ID_PREFIX:
        return None
    if not parts[1].isdigit() or not parts[2].isdigit():
        return None
    return int(parts[1]), int(parts[2])


def can_delete_quote(clicker_id: int, quoted_user_id: int, requester_id: int) -> bool:
    """削除できるのは、引用された本人と作成者だけ。"""
    return clicker_id == quoted_user_id or clicker_id == requester_id


async def _handle_quote_delete(
    interaction: discord.Interaction, quoted_user_id: int, requester_id: int
) -> None:
    """削除ボタンの押下を処理する。"""
    if not can_delete_quote(interaction.user.id, quoted_user_id, requester_id):
        await interaction.response.send_message(
            "この名言画像を消せるのは、引用された本人と作成者だけです。",
            ephemeral=True,
        )
        return
    try:
        # 🗑️ ボタンの付いたメッセージ自体（Bot の投稿）を削除する
        await interaction.response.defer()
        if interaction.message is not None:
            await interaction.message.delete()
    except Exception as exc:
        print(f"名言画像の削除に失敗しました: {exc!r}")
        try:
            await interaction.followup.send(
                "削除に失敗しました。すでに消えているか、Bot にメッセージ削除の権限がありません。",
                ephemeral=True,
            )
        except Exception:
            # 📝 応答自体が失敗した場合はログのみ
            pass


class QuoteDeleteButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"quote-delete:(?P<quoted_user_id>[0-9]+):(?P<requester_id>[0-9]+)",
):
    """再起動後も受け付けられる削除ボタン（DynamicItem）。"""

    def __init__(self, quoted_user_id: int, requester_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label="削除する",
                emoji="🗑️",
                style=discord.ButtonStyle.danger,
                custom_id=build_quote_delete_custom_id(quoted_user_id, requester_id),
            )
        )
        self.quoted_user_id = quoted_user_id
        self.requester_id = requester_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):  # type: ignore[override]
        """custom_id からボタンインスタンスを復元する。"""
        return cls(int(match["quoted_user_id"]), int(match["requester_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        """ボタン押下時に削除処理を呼ぶ。"""
        await _handle_quote_delete(interaction, self.quoted_user_id, self.requester_id)


def build_quote_delete_view(quoted_user_id: int, requester_id: int) -> discord.ui.View:
    """削除ボタン付きのビューを作る（タイムアウトなし）。"""
    view = discord.ui.View(timeout=None)
    view.add_item(QuoteDeleteButton(quoted_user_id, requester_id))
    return view


# ⏱️ アバター取得の制限（タイムアウト10秒・サイズ上限5MB）
AVATAR_TIMEOUT_SECONDS = 10  # アバター取得のタイムアウト（秒）
MAX_AVATAR_BYTES = 5 * 1024 * 1024  # アバター画像のサイズ上限（5MB）


class QuoteBot(discord.Client):
    """名言画像 Bot 本体。"""

    def __init__(self, config: Config) -> None:
        """Intents とコマンドツリーを初期化する。"""
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(intents=intents)
        self.config = config
        # 🎮 プレゼンス・サイクルの状態（起点は最初の on_ready で固定）
        self._presence_started_at_ms: int | None = None
        self._presence_task: asyncio.Task[None] | None = None
        # 🗑️ 削除ボタンを再起動後も受け付けられるよう DynamicItem を登録する
        self.add_dynamic_items(QuoteDeleteButton)
        self.tree = app_commands.CommandTree(self)
        self.tree.error(self._on_tree_error)
        # 🖼️ 描画はメモリを大きく使うため、同時に走るのは1件までに直列化する
        self.render_semaphore = asyncio.Semaphore(1)
        self._watchdog_task: asyncio.Task[None] | None = None

    async def setup_hook(self) -> None:
        """コマンド登録、ウォッチドッグ開始、コマンド同期を行う。"""
        _register_commands(self)
        # 🐶 READY が来ないサイレント停滞を検知して終了する（watchdog.py）
        self._watchdog_task = asyncio.create_task(watchdog_loop(self))
        # 🔄 sync の失敗でログイン自体を中断しない（失敗時はログを残して起動を続行する）
        try:
            if self.config.guild_id:
                guild = discord.Object(id=self.config.guild_id)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                print(f"コマンドをギルド {self.config.guild_id} に登録しました")
            else:
                await self.tree.sync()
                print("コマンドをグローバルに登録しました")
        except Exception as exc:
            print(f"コマンドの sync に失敗しました (起動は続行します): {exc!r}")

    async def _on_tree_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """コマンド失敗時の受け皿。ユーザーには失敗メッセージを返す。"""
        original = getattr(error, "original", error)
        print(f"コマンドの実行に失敗しました: {original!r}")
        message = "画像の生成に失敗しました。時間をおいてもう一度お試しください。"
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(content=message)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except Exception:
            # 📝 応答自体が失敗した場合はログのみ
            pass

    async def _apply_presence(self, at_ms: int) -> None:
        """時刻 at_ms 時点のサイクル値をプレゼンスに適用する。"""
        if self.user is None or self._presence_started_at_ms is None:
            return
        text = presence_cycle_text(self.user.name, self._presence_started_at_ms, at_ms)
        activity = discord.Activity(type=discord.ActivityType.playing, name=text)
        try:
            await self.change_presence(activity=activity)
            print(f"[presence-cycle] {text}")
        except Exception as exc:
            print(f"[presence-cycle] presence update failed: {exc!r}")

    async def _presence_cycle(self) -> None:
        """分の境界の 200ms 前に、次の分の値を先行送信し続ける。"""
        while True:
            now_ms = int(time.time() * 1000)
            send_at, boundary = next_presence_send(now_ms)
            await asyncio.sleep(max(0, (send_at - now_ms) / 1000))
            # 値は送信時刻ではなく境界時点のものを使う（先行送信）
            await self._apply_presence(boundary)

    async def on_ready(self) -> None:
        """ログイン完了時にプレゼンス・サイクルを開始する。"""
        print(f"ログインしました: {self.user} (ID: {self.user.id})")
        if self._presence_started_at_ms is None:
            self._presence_started_at_ms = int(time.time() * 1000)
        await self._apply_presence(int(time.time() * 1000))
        if self._presence_task is None or self._presence_task.done():
            self._presence_task = asyncio.create_task(self._presence_cycle())


# ------------------------------------------
# 🔧 共通処理
# ------------------------------------------
async def _display_name_of(interaction: discord.Interaction, user: discord.User) -> str:
    """表示名はグローバル表示名を使う（本家に合わせ、サーバーニックネームは使わない）。"""
    return user.display_name or user.name


async def _avatar_or_fallback(user: discord.User, display_name: str):
    """アバター画像を取得し、失敗したら代替画像を作る。

    取得は Asset.read() 任せにせず、明示的に10秒でタイムアウトさせ、
    5MB を超える応答は異常として代替画像に切り替える。
    """
    try:
        data = await asyncio.wait_for(
            user.display_avatar.with_size(512).read(),
            timeout=AVATAR_TIMEOUT_SECONDS,
        )
        if len(data) > MAX_AVATAR_BYTES:
            return fallback_avatar(display_name)
        return image_from_bytes(data)
    except Exception:
        return fallback_avatar(display_name)


async def _reply_with_quote(
    interaction: discord.Interaction,
    *,
    text: str,
    user: discord.User,
    route: str = "slash",
    semaphore: asyncio.Semaphore | None = None,
) -> None:
    """名言画像を生成してフォローアップで送信する。"""
    display_name = await _display_name_of(interaction, user)
    avatar = await _avatar_or_fallback(user, display_name)
    loop = asyncio.get_running_loop()

    def render() -> bytes:
        bot_user = interaction.client.user
        credit = (
            f"{bot_user.name}#{bot_user.discriminator}"
            if bot_user is not None and bot_user.discriminator not in (None, "0")
            else "Make It a Quote#3382"
        )
        return render_quote_image(
            text=text,
            display_name=display_name,
            username=user.name,
            avatar=avatar,
            credit=credit,
        )

    # 🧵 描画はイベントループを塞がないよう別スレッドで実行する
    if semaphore is None:
        png = await loop.run_in_executor(None, render)
    else:
        async with semaphore:
            png = await loop.run_in_executor(None, render)
    message = await interaction.followup.send(
        file=discord.File(io.BytesIO(png), filename="quote.png"),
        # 🗑️ 削除ボタン: 引用された本人（user）と作成者（interaction.user）だけが消せる
        view=build_quote_delete_view(int(user.id), int(interaction.user.id)),
    )
    # 🗄️ 不適切利用の確認用に、生成画像をサーバーへ保存する（archive.py）。
    # 保存に失敗しても生成自体は成功扱いのままにする。
    if archive_enabled():
        try:
            entry = {
                "route": route,
                "guild_id": interaction.guild_id,
                "channel_id": interaction.channel_id,
                "message_id": message.id,
                "requester_id": int(interaction.user.id),
                "quoted_user_id": int(user.id),
                "text": text,
            }
            await loop.run_in_executor(None, lambda: save_quote_archive(archive_dir(), entry, png))
        except Exception as exc:
            print(f"生成画像のアーカイブ保存に失敗しました: {exc!r}")


def _register_commands(bot: QuoteBot) -> None:
    """スラッシュコマンドとコンテキストメニューを登録する。"""
    tree = bot.tree

    @tree.context_menu(name="Make it a Quote")
    async def quote_message(interaction: discord.Interaction, message: discord.Message) -> None:
        """実際のメッセージを名言画像にする（メッセージの右クリック → アプリ）。"""
        text = (message.content or "").strip()
        ok = True
        error: Exception | None = None
        try:
            if not text:
                await interaction.response.send_message(
                    "テキストのないメッセージからは名言画像を作れません。",
                    ephemeral=True,
                )
                return
            # 🔢 /quote と同じ文字数上限をこの経路でも強制する。
            # 超過分を黙って切り捨てず、上限を超えていることを伝えて返る。
            if len(text) > QUOTE_MAX_CHARS:
                await interaction.response.send_message(
                    f"テキストが長すぎます ({len(text)}文字)。"
                    f"名言画像にできるのは最大{QUOTE_MAX_CHARS}文字までです。"
                    "短いメッセージでお試しください。",
                    ephemeral=True,
                )
                return
            await interaction.response.defer()
            await _reply_with_quote(
                interaction,
                text=text,
                user=message.author,
                route="context",
                semaphore=bot.render_semaphore,
            )
        except Exception as exc:
            ok = False
            error = exc
            raise
        finally:
            log_execution(
                interaction, cmd="quote", route="context", chars=len(text), ok=ok, error=error
            )

    @tree.command(name="quote", description="指定したユーザーが言ったことにして名言画像を捏造します")
    @app_commands.describe(user="発言者にするユーザー", text="言ったことにするテキスト")
    async def quote_command(
        interaction: discord.Interaction,
        user: discord.User,
        text: app_commands.Range[str, 1, QUOTE_MAX_CHARS],
    ) -> None:
        text = text.strip()
        ok = True
        error: Exception | None = None
        try:
            if not text:
                await interaction.response.send_message("テキストが空です。", ephemeral=True)
                return
            await interaction.response.defer()
            await _reply_with_quote(
                interaction, text=text, user=user, route="slash", semaphore=bot.render_semaphore
            )
        except Exception as exc:
            ok = False
            error = exc
            raise
        finally:
            log_execution(
                interaction, cmd="quote", route="slash", chars=len(text), ok=ok, error=error
            )


def run(config: Config) -> None:
    """Bot を起動する。"""
    bot = QuoteBot(config)
    bot.run(config.token)
