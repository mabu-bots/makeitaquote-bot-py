# 🗄️ アーカイブのテスト
import json
from datetime import datetime, timedelta, timezone

from makeitaquote.archive import (
    archive_dir,
    archive_enabled,
    build_archive_file_name,
    save_quote_archive,
    select_prune_targets,
)


def test_file_name_contains_timestamp_and_ids():
    when = datetime(2026, 11, 28, 3, 4, 5, tzinfo=timezone.utc)
    assert build_archive_file_name(when, 111, 222) == "20261128-030405Z_111_222.png"


def test_enabled_unless_off():
    assert archive_enabled({}) is True
    assert archive_enabled({"QUOTE_ARCHIVE": "on"}) is True
    assert archive_enabled({"QUOTE_ARCHIVE": "off"}) is False
    assert archive_enabled({"QUOTE_ARCHIVE": " OFF "}) is False
    assert archive_enabled({"QUOTE_ARCHIVE": "false"}) is False
    assert archive_enabled({"QUOTE_ARCHIVE": "0"}) is False


def test_dir_default_and_override():
    assert archive_dir({}) == "data/archive"
    assert archive_dir({"QUOTE_ARCHIVE_DIR": "/tmp/quotes"}) == "/tmp/quotes"


def _entry() -> dict:
    return {
        "route": "slash",
        "guild_id": 1,
        "channel_id": 2,
        "message_id": 3,
        "requester_id": 111,
        "quoted_user_id": 222,
        "text": "本文",
    }


def test_save_writes_png_and_index_line(tmp_path):
    when = datetime(2026, 11, 28, 3, 4, 5, tzinfo=timezone.utc)
    name = save_quote_archive(tmp_path, _entry(), b"PNGDATA", now=when)
    assert (tmp_path / name).read_bytes() == b"PNGDATA"
    lines = (tmp_path / "index.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["file"] == name
    assert record["requester_id"] == 111
    assert record["quoted_user_id"] == 222
    assert record["text"] == "本文"
    assert record["ts"].startswith("2026-11-28T03:04:05")


def test_prune_selects_old_and_excess():
    now = 1_000_000_000.0
    day = 24 * 60 * 60
    files = [
        ("old.png", now - 31 * day),  # 保持期間（30日）超過
        ("a.png", now - 100),
        ("b.png", now - 90),
        ("c.png", now - 80),
        ("note.txt", now - 40 * day),  # .png 以外は対象外
    ]
    targets = select_prune_targets(files, now, max_items=2, max_age_seconds=30 * day)
    # 期間超過の old.png と、件数超過分として古い a.png
    assert targets == ["old.png", "a.png"]


def test_save_prunes_old_images_but_keeps_index(tmp_path):
    old_name = "20000101-000000Z_1_2.png"
    (tmp_path / old_name).write_bytes(b"old")
    import os

    old_time = datetime.now(timezone.utc) - timedelta(days=40)
    os.utime(tmp_path / old_name, (old_time.timestamp(), old_time.timestamp()))
    save_quote_archive(tmp_path, _entry(), b"new")
    assert not (tmp_path / old_name).exists()
    # index.jsonl は監査記録として残る
    assert (tmp_path / "index.jsonl").exists()
