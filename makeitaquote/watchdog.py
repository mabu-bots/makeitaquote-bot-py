# ==========================================
# 🐶 Gateway 安全構造（READY ウォッチドッグ）
# ==========================================
# 🐶 ログイン後に READY が来ない「サイレント停滞」を検知し、プロセスを
# 終了させて pm2 に再起動させる。接続自体は生きていてハートビート
# ACK も返る状態では discord.py の自動再接続が働かない場合がある
# ための保険。
# なお discord.py は close した Client を同じプロセスで確実に
# 再ログインさせる手段がないため、回復はプロセス再起動に委ねる。
from __future__ import annotations

import asyncio
import os
import time
from typing import Callable, Protocol

NOT_READY_LIMIT_SECONDS = 120.0  # ⏱️ READY でない状態がこの時間（秒）続いたら停滞とみなす
CHECK_INTERVAL_SECONDS = 30.0  # 🔁 ウォッチドッグの確認間隔（秒）


class _BotLike(Protocol):
    """ウォッチドッグが使う Bot の最小インターフェース。"""

    def is_ready(self) -> bool: ...

    def is_closed(self) -> bool: ...

    async def close(self) -> None: ...


# ------------------------------------------
# 👀 READY 受信状況の追跡（判定ロジック）
# ------------------------------------------
class ReadyWatchdog:
    """READY 受信状況を追跡する。"""

    def __init__(self, now: float) -> None:
        """起動時点から「未 READY」として追跡を開始する。"""
        self._not_ready_since: float | None = now

    def observe(self, is_ready: bool, now: float) -> None:
        """現在の READY 状態を観測させる。READY でなくなった瞬間から数え直す。"""
        if is_ready:
            self._not_ready_since = None
        elif self._not_ready_since is None:
            self._not_ready_since = now

    def on_fire(self, now: float) -> None:
        """発動（プロセス終了）の起点をリセットする。"""
        self._not_ready_since = now

    def is_expired(self, now: float, limit_seconds: float) -> bool:
        """停滞が制限時間を超えたかどうかを返す。"""
        return self._not_ready_since is not None and now - self._not_ready_since >= limit_seconds


# ------------------------------------------
# 🔁 ウォッチドッグのループ
# ------------------------------------------
async def watchdog_loop(
    bot: _BotLike,
    *,
    limit_seconds: float = NOT_READY_LIMIT_SECONDS,
    interval_seconds: float = CHECK_INTERVAL_SECONDS,
    log: Callable[[str], None] = lambda message: print(message, flush=True),
    exit_process: Callable[[int], None] = os._exit,
) -> None:
    """READY の停滞を検知したら終了コード 1 でプロセスを終了する（pm2 が再起動する）。"""
    watchdog = ReadyWatchdog(time.monotonic())
    while not bot.is_closed():
        await asyncio.sleep(interval_seconds)
        now = time.monotonic()
        watchdog.observe(bot.is_ready(), now)
        if not watchdog.is_expired(now, limit_seconds):
            continue
        log(
            f"[watchdog] READY が {int(limit_seconds)} 秒以上来ないためプロセスを終了します (pm2 が再起動します)"
        )
        watchdog.on_fire(now)
        # 🔌 まず通常の切断を試み、終わらなければそのまま終了する
        try:
            await asyncio.wait_for(bot.close(), timeout=5)
        except Exception:
            pass
        exit_process(1)
        return
