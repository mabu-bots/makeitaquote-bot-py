# 📝 折り返しとサイズ調整のテスト
from makeitaquote.wrap import fit_quote_text, wrap_text


def measure(s: str) -> float:
    """1文字 = 幅10 として計測する。"""
    return len(s) * 10.0


def test_wraps_at_max_width():
    # 幅35 → 1行に3文字まで
    assert wrap_text("abcdefg", 35, measure) == ["abc", "def", "g"]


def test_respects_paragraphs():
    assert wrap_text("ab\ncd", 100, measure) == ["ab", "cd"]
    assert wrap_text("ab\n\ncd", 100, measure) == ["ab", "", "cd"]


def test_crlf_is_normalized():
    assert wrap_text("ab\r\ncd", 100, measure) == ["ab", "cd"]


def test_kinsoku_no_line_start():
    # 「、」は行頭に置けないので、幅を超えても前の行へ追い込む
    assert wrap_text("abc、def", 35, measure) == ["abc、", "def"]


def test_kinsoku_no_line_end():
    # 「「」は行末に残せないので、次の行へ送る
    assert wrap_text("ab「cd", 35, measure) == ["ab", "「cd"]


def test_leading_spaces_dropped():
    assert wrap_text("  abc", 100, measure) == ["abc"]
    assert wrap_text("ab 　cd", 25, measure) == ["ab", "cd"]


def _fit(text: str, **overrides):
    kwargs = dict(
        max_width=200,
        max_height=200,
        sizes=[40, 30, 20],
        line_height_ratio=1.5,
        measure_at=lambda size: (lambda s: len(s) * size * 0.5),
    )
    kwargs.update(overrides)
    return fit_quote_text(text, **kwargs)


def test_fit_picks_largest_fitting_size():
    fit = _fit("短い文")
    assert fit.font_size == 40
    assert fit.lines == ["短い文"]


def test_fit_shrinks_for_long_text():
    fit = _fit("あ" * 60)
    assert fit.font_size < 40
    assert len(fit.lines) * fit.line_height <= 200


def test_fit_truncates_with_ellipsis():
    fit = _fit("あ" * 500, max_height=60)
    # 最小サイズ（20・行高30）で2行まで、最終行は … で終わる
    assert fit.font_size == 20
    assert len(fit.lines) == 2
    assert fit.lines[-1].endswith("…")
