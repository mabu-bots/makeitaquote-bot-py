# 😀 絵文字トークン化・解決・絵文字混じり折り返しのテスト
from PIL import Image

from makeitaquote.emoji import (
    CustomToken,
    EmojiToken,
    ImageToken,
    TextToken,
    custom_emoji_url,
    has_emoji_token,
    is_allowed_emoji_url,
    resolve_rich_tokens,
    tokenize_rich_text,
    twemoji_asset_candidates,
    twemoji_url,
)
from makeitaquote.wrap import fit_rich_text, wrap_rich_text


def _kinds(tokens):
    return [t.kind for t in tokens]


# ------------------------------------------
# トークン化
# ------------------------------------------
def test_plain_text():
    tokens = tokenize_rich_text("こんにちは")
    assert len(tokens) == 1
    assert isinstance(tokens[0], TextToken)
    assert tokens[0].text == "こんにちは"
    assert not has_emoji_token(tokens)


def test_single_emoji():
    tokens = tokenize_rich_text("すごい😀ね")
    assert _kinds(tokens) == ["text", "emoji", "text"]
    assert tokens[1].raw == "😀"
    assert tokens[1].asset == "1f600"
    assert has_emoji_token(tokens)


def test_zwj_sequence_is_one_token():
    tokens = tokenize_rich_text("👨‍👩‍👧")
    assert len(tokens) == 1
    assert tokens[0].kind == "emoji"
    assert tokens[0].raw == "👨‍👩‍👧"


def test_skin_tone_is_one_token():
    tokens = tokenize_rich_text("👍🏽")
    assert len(tokens) == 1
    assert tokens[0].raw == "👍🏽"


def test_flag_is_one_token():
    tokens = tokenize_rich_text("🇯🇵")
    assert len(tokens) == 1
    assert tokens[0].kind == "emoji"
    assert tokens[0].raw == "🇯🇵"


def test_keycap_and_plain_digits():
    tokens = tokenize_rich_text("1️⃣")
    assert len(tokens) == 1
    assert tokens[0].kind == "emoji"
    plain = tokenize_rich_text("123")
    assert _kinds(plain) == ["text"]


def test_heart_with_vs16():
    tokens = tokenize_rich_text("❤️")
    assert len(tokens) == 1
    assert tokens[0].kind == "emoji"
    # ZWJ を含まないので主候補は FE0F を落とした名前
    assert tokens[0].asset == "2764"


def test_custom_emoji_static_and_animated():
    static = tokenize_rich_text("<:smile:123456789>")
    assert len(static) == 1
    assert isinstance(static[0], CustomToken)
    assert static[0].id == "123456789"
    assert static[0].animated is False
    animated = tokenize_rich_text("<a:wave:987654321>")
    assert animated[0].animated is True


# ------------------------------------------
# Twemoji のアセット名
# ------------------------------------------
def test_no_zwj_drops_fe0f():
    candidates = twemoji_asset_candidates("❤️")
    assert candidates[0] == "2764"
    assert candidates[1] == "2764-fe0f"


def test_zwj_keeps_fe0f():
    candidates = twemoji_asset_candidates("🏳️‍🌈")
    assert candidates[0] == "1f3f3-fe0f-200d-1f308"


def test_urls_and_allowlist():
    assert twemoji_url("1f600").endswith("/72x72/1f600.png")
    assert is_allowed_emoji_url(twemoji_url("1f600"))
    assert is_allowed_emoji_url(custom_emoji_url("123"))
    assert not is_allowed_emoji_url("http://cdn.jsdelivr.net/x.png")  # http は不可
    assert not is_allowed_emoji_url("https://example.com/x.png")  # 許可外ホスト
    assert custom_emoji_url("123") == "https://cdn.discordapp.com/emojis/123.png?size=96"


# ------------------------------------------
# 解決（取得成功・失敗）
# ------------------------------------------
def _fake_image() -> Image.Image:
    return Image.new("RGBA", (72, 72), (255, 0, 0, 255))


def test_resolve_success_and_failure():
    def fetcher(url: str):
        return _fake_image() if "1f600" in url else None

    resolved = resolve_rich_tokens(tokenize_rich_text("😀と😢"), fetcher)
    assert isinstance(resolved[0], ImageToken)
    assert isinstance(resolved[1], TextToken)
    # 取得に失敗した絵文字は元の文字列に戻る
    assert isinstance(resolved[2], TextToken)
    assert resolved[2].text == "😢"


def test_custom_uses_discord_cdn_url():
    seen: list[str] = []

    def fetcher(url: str):
        seen.append(url)
        return _fake_image()

    resolve_rich_tokens(tokenize_rich_text("<:smile:42>"), fetcher)
    assert seen == ["https://cdn.discordapp.com/emojis/42.png?size=96"]


# ------------------------------------------
# 絵文字混じりの折り返し
# ------------------------------------------
def _resolved(text: str) -> list:
    return resolve_rich_tokens(tokenize_rich_text(text), lambda url: _fake_image())


def _measure(s: str) -> float:
    return len(s) * 10.0


def test_emoji_not_split_and_measured_as_square():
    # 幅25: "ab"(20) の次に絵文字（幅=フォントサイズ相当 20）が来たら次行へ送られる
    lines = wrap_rich_text(_resolved("ab😀"), 25, _measure, 20)
    assert len(lines) == 2
    assert isinstance(lines[1][0], ImageToken)


def test_kinsoku_after_emoji():
    # 絵文字の直後の「、」は行頭禁則で前の行へ追い込まれる
    lines = wrap_rich_text(_resolved("a😀、b"), 25, _measure, 10)
    assert len(lines) == 2
    first = lines[0]
    assert any(isinstance(t, ImageToken) for t in first)
    assert any(isinstance(t, TextToken) and "、" in t.text for t in first)


def test_fit_rich_text():
    fit = fit_rich_text(
        _resolved("短い😀文"),
        max_width=200,
        max_height=200,
        sizes=[40, 30, 20],
        line_height_ratio=1.5,
        measure_at=lambda size: (lambda s: len(s) * size * 0.5),
    )
    assert fit.font_size == 40
    assert len(fit.lines) == 1
