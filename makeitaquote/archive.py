# ==========================================
# 🗄️ 生成画像のサーバー保存（不適切利用の確認用アーカイブ）
# ==========================================
# 📝 生成した名言画像を Bot のサーバー側へ保存し、捏造画像が不適切に
# 使われていないかを後から確認できるようにする。保存先は運営者だけが
# 見られるサーバー内（既定: data/archive）。
#
# - 画像（PNG）と、1行1件の index.jsonl（いつ・誰が・誰の発言として・
#   どのサーバー/チャンネルで・本文）をセットで残す
# - 無制限に溜めない: 保持は最大30日 かつ 最大1000件。超えた画像は
#   古い順に自動削除する（index.jsonl は監査記録として残す）
# - 保存に失敗しても画像生成自体は失敗させない（呼び出し側で握る）
# - 止めたいときは環境変数 QUOTE_ARCHIVE=off。保存先は QUOTE_ARCHIVE_DIR で変更可
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

ARCHIVE_MAX_ITEMS = 1000  # アーカイブの最大保持件数
ARCHIVE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60  # アーカイブの最大保持期間（30日）
DEFAULT_ARCHIVE_DIR = "data/archive"  # アーカイブの既定の保存先


def archive_enabled(env: dict[str, str] | None = None) -> bool:
    """アーカイブ保存が有効かどうかを返す（QUOTE_ARCHIVE=off/false/0 で無効）。"""
    env = os.environ if env is None else env
    return env.get("QUOTE_ARCHIVE", "").strip().lower() not in ("off", "false", "0")


def archive_dir(env: dict[str, str] | None = None) -> str:
    """アーカイブの保存先ディレクトリを返す。"""
    env = os.environ if env is None else env
    return env.get("QUOTE_ARCHIVE_DIR", "").strip() or DEFAULT_ARCHIVE_DIR


def build_archive_file_name(when: datetime, requester_id: int, quoted_user_id: int) -> str:
    """アーカイブ画像のファイル名を作る（時刻順に並ぶ UTC タイムスタンプ + 両者の ID）。"""
    stamp = when.astimezone(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    return f"{stamp}_{requester_id}_{quoted_user_id}.png"


def select_prune_targets(
    files: list[tuple[str, float]],
    now: float,
    max_items: int = ARCHIVE_MAX_ITEMS,
    max_age_seconds: float = ARCHIVE_MAX_AGE_SECONDS,
) -> list[str]:
    """削除対象の選定（純ロジック）。

    保持期間を超えたものを消し、それでも上限件数を超える場合は古い順に消す。
    対象は .png のみ。
    """
    pngs = sorted((f for f in files if f[0].endswith(".png")), key=lambda f: (f[1], f[0]))
    targets: list[str] = []
    fresh: list[tuple[str, float]] = []
    for name, mtime in pngs:
        if now - mtime > max_age_seconds:
            targets.append(name)
        else:
            fresh.append((name, mtime))
    excess = len(fresh) - max_items
    if excess > 0:
        targets.extend(name for name, _ in fresh[:excess])
    return targets


def save_quote_archive(
    directory: str | Path,
    entry: dict,
    png: bytes,
    now: datetime | None = None,
) -> str:
    """画像とメタデータを保存し、ついでに古い画像を掃除する。保存したファイル名を返す。"""
    now = now or datetime.now(timezone.utc)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    file_name = build_archive_file_name(now, entry["requester_id"], entry["quoted_user_id"])
    (directory / file_name).write_bytes(png)
    record = {"ts": now.astimezone(timezone.utc).isoformat(), "file": file_name, **entry}
    with (directory / "index.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    files = [(p.name, p.stat().st_mtime) for p in directory.glob("*.png")]
    for target in select_prune_targets(files, time.time()):
        try:
            (directory / target).unlink()
        except OSError:
            pass
    return file_name
