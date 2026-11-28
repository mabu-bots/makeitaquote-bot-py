# 🤖 Bot 本体のテスト（プレゼンス・削除ボタン・コマンド・エラー処理）
import asyncio
import io
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
from PIL import Image

import makeitaquote.bot as bot_module
from makeitaquote.bot import (
    MAX_AVATAR_BYTES,
    QuoteBot,
    _avatar_or_fallback,
    _handle_quote_delete,
    _register_commands,
    _reply_with_quote,
    build_quote_delete_custom_id,
    build_quote_delete_view,
    can_delete_quote,
    format_elapsed_minutes,
    next_presence_send,
    parse_quote_delete_custom_id,
    presence_cycle_text,
)
from makeitaquote.config import Config


# ------------------------------------------
# スタブ
# ------------------------------------------
def _tiny_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


class FakeAsset:
    """display_avatar の代わり。"""

    def __init__(self, data: bytes = b"", exc: Exception | None = None, delay: float = 0.0):
        self._data = data
        self._exc = exc
        self._delay = delay

    def with_size(self, size: int):
        return self

    async def read(self) -> bytes:
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._exc:
            raise self._exc
        return self._data


class FakeUser:
    def __init__(self, id=222, name="quoted", display_name="引用 太郎", asset=None):
        self.id = id
        self.name = name
        self.display_name = display_name
        self.display_avatar = asset if asset is not None else FakeAsset(data=_tiny_png())


class FakeResponse:
    def __init__(self, done: bool = False):
        self._done = done
        self.sent: list[tuple] = []
        self.deferred = False

    def is_done(self) -> bool:
        return self._done

    async def send_message(self, content=None, **kwargs):
        self.sent.append((content, kwargs))
        self._done = True

    async def defer(self, **kwargs):
        self.deferred = True
        self._done = True


class FakeFollowup:
    def __init__(self):
        self.sent: list[dict] = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(id=999)


class FakeMessage:
    def __init__(self, content="", author=None):
        self.content = content
        self.author = author
        self.deleted = False

    async def delete(self):
        self.deleted = True


def make_interaction(user_id=111, *, message=None, response_done=False):
    return SimpleNamespace(
        user=SimpleNamespace(id=user_id, name="requester"),
        guild=None,
        guild_id=None,
        channel_id=555,
        response=FakeResponse(done=response_done),
        followup=FakeFollowup(),
        message=message,
        client=SimpleNamespace(
            user=SimpleNamespace(name="QuoteBot", discriminator="1234")
        ),
    )


def make_bot(guild_id=None) -> QuoteBot:
    return QuoteBot(Config(token="test-token", client_id=123, guild_id=guild_id))


# ------------------------------------------
# 🎮 プレゼンス・サイクル（純ロジック）
# ------------------------------------------
def test_format_elapsed_minutes():
    assert format_elapsed_minutes(0) == "0分"
    assert format_elapsed_minutes(59_999) == "0分"
    assert format_elapsed_minutes(60_000) == "1分"
    assert format_elapsed_minutes(26 * 60_000) == "26分"
    assert format_elapsed_minutes(86 * 60_000) == "1時間26分"
    assert format_elapsed_minutes(65 * 60_000) == "1時間05分"
    assert format_elapsed_minutes(-5_000) == "0分"


def test_presence_cycle_text_phases():
    # Unix 分が偶数 → 経過時間、奇数 → 現在時刻（JST）
    assert presence_cycle_text("Bot", 0, 10 * 60_000) == "Bot | 起動して 10分"
    assert presence_cycle_text("Bot", 0, 11 * 60_000) == "Bot | 現在時刻 09:11 JST"


def test_next_presence_send():
    assert next_presence_send(0) == (59_800, 60_000)
    assert next_presence_send(30_000) == (59_800, 60_000)
    # 送信予定を過ぎていたら翌分へ前進する
    assert next_presence_send(59_800) == (119_800, 120_000)
    assert next_presence_send(59_999) == (119_800, 120_000)


# ------------------------------------------
# 🗑️ 削除ボタン（純ロジック）
# ------------------------------------------
def test_custom_id_round_trip():
    custom_id = build_quote_delete_custom_id(111, 222)
    assert custom_id == "quote-delete:111:222"
    assert parse_quote_delete_custom_id(custom_id) == (111, 222)


def test_custom_id_invalid():
    assert parse_quote_delete_custom_id("quote-delete:111") is None
    assert parse_quote_delete_custom_id("quote-delete:a:b") is None
    assert parse_quote_delete_custom_id("other:111:222") is None
    assert parse_quote_delete_custom_id("quote-delete:111:222:333") is None


def test_only_quoted_user_and_requester_can_delete():
    assert can_delete_quote(111, 111, 222) is True
    assert can_delete_quote(222, 111, 222) is True
    assert can_delete_quote(333, 111, 222) is False


def test_view_has_delete_button_with_custom_id():
    view = build_quote_delete_view(111, 222)
    assert view.timeout is None
    button = view.children[0].item
    assert button.custom_id == "quote-delete:111:222"
    assert button.label == "削除する"
    assert button.style == discord.ButtonStyle.danger


def test_intents_are_guilds_only():
    async def scenario():
        bot = make_bot()
        assert bot.intents.guilds is True
        assert bot.intents.messages is False
        assert bot.intents.message_content is False
        assert bot.intents.members is False
        await bot.close()

    asyncio.run(scenario())


# ------------------------------------------
# 🗑️ 削除ボタンの処理
# ------------------------------------------
def test_quoted_user_can_delete_message():
    async def scenario():
        message = FakeMessage()
        interaction = make_interaction(user_id=111, message=message)
        await _handle_quote_delete(interaction, quoted_user_id=111, requester_id=222)
        assert message.deleted is True

    asyncio.run(scenario())


def test_requester_can_delete_message():
    async def scenario():
        message = FakeMessage()
        interaction = make_interaction(user_id=222, message=message)
        await _handle_quote_delete(interaction, quoted_user_id=111, requester_id=222)
        assert message.deleted is True

    asyncio.run(scenario())


def test_third_party_cannot_delete():
    async def scenario():
        message = FakeMessage()
        interaction = make_interaction(user_id=333, message=message)
        await _handle_quote_delete(interaction, quoted_user_id=111, requester_id=222)
        assert message.deleted is False
        assert interaction.response.sent
        content, kwargs = interaction.response.sent[0]
        assert "引用された本人と作成者だけ" in content
        assert kwargs.get("ephemeral") is True

    asyncio.run(scenario())


# ------------------------------------------
# 起動まわり
# ------------------------------------------
def test_setup_hook_continues_when_sync_fails():
    async def scenario():
        bot = make_bot()
        bot.tree.sync = AsyncMock(side_effect=RuntimeError("sync boom"))
        await bot.setup_hook()  # 例外で落ちないこと
        names = {c.name for c in bot.tree.get_commands()}
        assert "quote" in names
        assert "Make it a Quote" in names
        bot._watchdog_task.cancel()
        await bot.close()

    asyncio.run(scenario())


def test_error_handler_replies_ephemeral_when_not_done():
    async def scenario():
        bot = make_bot()
        interaction = make_interaction(response_done=False)
        await bot._on_tree_error(interaction, RuntimeError("boom"))
        content, kwargs = interaction.response.sent[0]
        assert "生成に失敗しました" in content
        assert kwargs.get("ephemeral") is True
        await bot.close()

    asyncio.run(scenario())


def test_error_handler_edits_original_when_done():
    async def scenario():
        bot = make_bot()
        interaction = make_interaction(response_done=True)
        edited = {}

        async def edit_original_response(**kwargs):
            edited.update(kwargs)

        interaction.edit_original_response = edit_original_response
        await bot._on_tree_error(interaction, RuntimeError("boom"))
        assert "生成に失敗しました" in edited["content"]
        await bot.close()

    asyncio.run(scenario())


# ------------------------------------------
# コマンド
# ------------------------------------------
def _get_command(bot, name):
    for command in bot.tree.get_commands():
        if command.name == name:
            return command
    raise AssertionError(f"command not found: {name}")


def test_quote_command_rejects_whitespace_only_text():
    async def scenario():
        bot = make_bot()
        _register_commands(bot)
        command = _get_command(bot, "quote")
        interaction = make_interaction()
        await command.callback(interaction, FakeUser(), "   ")
        content, kwargs = interaction.response.sent[0]
        assert content == "テキストが空です。"
        assert kwargs.get("ephemeral") is True
        await bot.close()

    asyncio.run(scenario())


def test_quote_command_strips_text_before_reply(monkeypatch):
    seen: dict = {}

    def fake_render(**kwargs):
        seen.update(kwargs)
        return b"png"

    monkeypatch.setattr(bot_module, "render_quote_image", fake_render)
    monkeypatch.setattr(bot_module, "archive_enabled", lambda: False)

    async def scenario():
        bot = make_bot()
        _register_commands(bot)
        command = _get_command(bot, "quote")
        interaction = make_interaction()
        await command.callback(interaction, FakeUser(), "  前後の空白  ")
        assert interaction.response.deferred is True
        assert len(interaction.followup.sent) == 1
        await bot.close()

    asyncio.run(scenario())
    assert seen["text"] == "前後の空白"


def test_quote_message_rejects_over_300_chars():
    async def scenario():
        bot = make_bot()
        _register_commands(bot)
        menu = _get_command(bot, "Make it a Quote")
        message = FakeMessage(content="あ" * 301, author=FakeUser())
        interaction = make_interaction()
        await menu.callback(interaction, message)
        content, kwargs = interaction.response.sent[0]
        assert "長すぎます (301文字)" in content
        assert kwargs.get("ephemeral") is True
        assert interaction.followup.sent == []
        await bot.close()

    asyncio.run(scenario())


def test_quote_message_accepts_exactly_300_chars(monkeypatch):
    monkeypatch.setattr(bot_module, "render_quote_image", lambda **kwargs: b"png")
    monkeypatch.setattr(bot_module, "archive_enabled", lambda: False)

    async def scenario():
        bot = make_bot()
        _register_commands(bot)
        menu = _get_command(bot, "Make it a Quote")
        message = FakeMessage(content="あ" * 300, author=FakeUser())
        interaction = make_interaction()
        await menu.callback(interaction, message)
        assert interaction.response.deferred is True
        assert len(interaction.followup.sent) == 1
        await bot.close()

    asyncio.run(scenario())


def test_quote_message_rejects_empty_text():
    async def scenario():
        bot = make_bot()
        _register_commands(bot)
        menu = _get_command(bot, "Make it a Quote")
        message = FakeMessage(content="   ", author=FakeUser())
        interaction = make_interaction()
        await menu.callback(interaction, message)
        content, kwargs = interaction.response.sent[0]
        assert content == "テキストのないメッセージからは名言画像を作れません。"
        assert kwargs.get("ephemeral") is True
        await bot.close()

    asyncio.run(scenario())


# ------------------------------------------
# アバター取得の防御
# ------------------------------------------
def test_avatar_oversized_falls_back():
    async def scenario():
        user = FakeUser(asset=FakeAsset(data=b"x" * (MAX_AVATAR_BYTES + 1)))
        img = await _avatar_or_fallback(user, "名前")
        assert img.size == (630, 630)  # 代替画像

    asyncio.run(scenario())


def test_avatar_timeout_falls_back(monkeypatch):
    monkeypatch.setattr(bot_module, "AVATAR_TIMEOUT_SECONDS", 0.05)

    async def scenario():
        user = FakeUser(asset=FakeAsset(data=_tiny_png(), delay=1.0))
        img = await _avatar_or_fallback(user, "名前")
        assert img.size == (630, 630)

    asyncio.run(scenario())


def test_avatar_success_returns_image():
    async def scenario():
        user = FakeUser(asset=FakeAsset(data=_tiny_png()))
        img = await _avatar_or_fallback(user, "名前")
        assert img.size == (8, 8)

    asyncio.run(scenario())


# ------------------------------------------
# 描画の直列化
# ------------------------------------------
def test_rendering_is_serialized_by_semaphore(monkeypatch):
    state = {"current": 0, "peak": 0}

    def fake_render(**kwargs):
        state["current"] += 1
        state["peak"] = max(state["peak"], state["current"])
        time.sleep(0.05)
        state["current"] -= 1
        return b"png"

    monkeypatch.setattr(bot_module, "render_quote_image", fake_render)
    monkeypatch.setattr(bot_module, "archive_enabled", lambda: False)

    async def scenario():
        bot = make_bot()
        user = FakeUser()

        async def one():
            interaction = make_interaction()
            await _reply_with_quote(
                interaction, text="文", user=user, semaphore=bot.render_semaphore
            )

        await asyncio.gather(one(), one(), one())
        await bot.close()

    asyncio.run(scenario())
    assert state["peak"] == 1
