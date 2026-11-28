# 📋 実行ログのテスト
from makeitaquote.execution_log import format_execution_log, summarize_error

NOW = "2026-11-28T00:00:00.000Z"


def test_ok_line_contains_only_metadata():
    line = format_execution_log(
        cmd="quote",
        route="slash",
        guild_id=10,
        channel_id=20,
        user_id=30,
        chars=12,
        ok=True,
        now=NOW,
    )
    assert line == (
        f"[exec] {NOW} cmd=quote route=slash guild=10 channel=20 "
        "user=30 chars=12 result=ok"
    )


def test_context_route_and_dm():
    # DM では guild が None → "-" で出す
    line = format_execution_log(
        cmd="quote",
        route="context",
        guild_id=None,
        channel_id=None,
        user_id=30,
        ok=True,
        now=NOW,
    )
    assert "route=context" in line
    assert "guild=-" in line
    assert "channel=-" in line
    assert "chars=" not in line


def test_error_line_appends_summary():
    line = format_execution_log(
        cmd="quote",
        route="slash",
        guild_id=10,
        channel_id=20,
        user_id=30,
        ok=False,
        error=ValueError("だめ"),
        now=NOW,
    )
    assert line.endswith('result=error error="ValueError: だめ"')


def test_summarize_error_flattens_and_replaces_quotes():
    error = RuntimeError('複数\n行の "エラー" です')
    summary = summarize_error(error)
    assert "\n" not in summary
    assert '"' not in summary
    assert summary.startswith("RuntimeError: ")


def test_summarize_error_truncates_long_messages():
    summary = summarize_error(ValueError("x" * 300))
    assert summary.endswith("…")
    assert len(summary) == 101


def test_summarize_error_none_is_empty():
    assert summarize_error(None) == ""
