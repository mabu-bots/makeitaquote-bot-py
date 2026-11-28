# ==========================================
# 📋 コマンド実行ログ
# ==========================================
# 📋 コマンドが実行されるたびに、標準出力へ1行のメタ情報を残す
# （pm2 の out ログに残る）。ユーザーの入力テキスト（オプション値・
# 本文）は記録せず、コマンド名・ID・成否だけを残す（文字数は可）。
# 書式は全 Bot 共通:
#   [exec] <ISO時刻> cmd=<名前> route=<slash|context|prefix> guild=<ID>
#          channel=<ID> user=<ID> [chars=<文字数>] result=<ok|error>
# 失敗時は末尾に error="<要点>" が付く。
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def iso_now() -> str:
    """現在時刻を、ミリ秒3桁 + Z の ISO 形式（JS の Date.toISOString() と同じ形式）で返す。"""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def summarize_error(error: Optional[BaseException]) -> str:
    """エラーを1行の要点に整形する（空白を潰し、引用符を置換し、長すぎれば切り詰める）。"""
    if error is None:
        return ""
    raw = f"{type(error).__name__}: {error}"
    one_line = " ".join(raw.split()).replace('"', "'").strip()
    return one_line[:100] + "…" if len(one_line) > 100 else one_line


def format_execution_log(
    *,
    cmd: str,
    route: str,
    guild_id: Optional[int],
    channel_id: Optional[int],
    user_id: int,
    chars: Optional[int] = None,
    ok: bool,
    error: Optional[BaseException] = None,
    now: Optional[str] = None,
) -> str:
    """実行ログの1行を組み立てる。"""
    parts = [
        "[exec]",
        now if now is not None else iso_now(),
        f"cmd={cmd}",
        f"route={route}",
        f"guild={guild_id if guild_id is not None else '-'}",
        f"channel={channel_id if channel_id is not None else '-'}",
        f"user={user_id}",
    ]
    if chars is not None:
        parts.append(f"chars={chars}")
    parts.append(f"result={'ok' if ok else 'error'}")
    if not ok:
        parts.append(f'error="{summarize_error(error)}"')
    return " ".join(parts)


def log_execution(
    interaction,
    *,
    cmd: str,
    route: str,
    chars: Optional[int] = None,
    ok: bool,
    error: Optional[BaseException] = None,
) -> None:
    """コマンド実行ログを標準出力へ出す。"""
    guild_id = interaction.guild.id if interaction.guild is not None else None
    print(
        format_execution_log(
            cmd=cmd,
            route=route,
            guild_id=guild_id,
            channel_id=interaction.channel_id,
            user_id=interaction.user.id,
            chars=chars,
            ok=ok,
            error=error,
        ),
        flush=True,
    )
