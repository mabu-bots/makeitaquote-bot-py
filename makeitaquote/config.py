# ==========================================
# ⚙️ 設定ローダー（.env 読み込み）
# ==========================================
# 📝 依存ライブラリを使わず、.env を最小限の自前パーサで読む。
# すでに環境変数として設定されている値は .env で上書きしない
# （os.environ.setdefault を使う）ため、実行環境側の設定が優先される。
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    """Bot の動作に必要な設定一式。"""

    token: str
    client_id: int
    guild_id: int | None


def _strip_value(raw: str) -> str:
    """代入値の後処理を行う。

    - 引用符の外側にあり、直前が空白の ` #` 以降はインラインコメントとして除去する
    - 引用符の中の `#` や、直前が空白でない `#` は値の一部として残す
    - 値全体を囲む引用符（単一・二重）があれば外す
    """
    in_single = False
    in_double = False
    for i, ch in enumerate(raw):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif (
            ch == "#"
            and not in_single
            and not in_double
            and i > 0
            and raw[i - 1] in " \t"
        ):
            raw = raw[:i]
            break
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value


def _read_dotenv(path: Path) -> None:
    """.env ファイルを読み、未設定の環境変数として取り込む。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), _strip_value(value))


def _to_int(name: str, raw: str) -> int:
    """環境変数の文字列を整数へ変換する。失敗時は変数名入りのエラーを出す。"""
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(
            f"環境変数 {name} は整数でなければなりません (.env を確認してください)"
        ) from None


def load_config() -> Config:
    """カレントディレクトリの .env と環境変数から Config を組み立てる。"""
    _read_dotenv(Path.cwd() / ".env")

    token = os.environ.get("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "環境変数 DISCORD_TOKEN が設定されていません (.env を確認してください)"
        )

    client_id_raw = os.environ.get("CLIENT_ID", "").strip()
    if not client_id_raw:
        raise RuntimeError(
            "環境変数 CLIENT_ID が設定されていません (.env を確認してください)"
        )

    guild_raw = os.environ.get("GUILD_ID", "").strip()
    return Config(
        token=token,
        client_id=_to_int("CLIENT_ID", client_id_raw),
        guild_id=_to_int("GUILD_ID", guild_raw) if guild_raw else None,
    )
