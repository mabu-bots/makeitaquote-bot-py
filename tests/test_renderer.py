# 🖼️ レンダラのテスト
import io

from PIL import Image

from makeitaquote.renderer import fallback_avatar, render_quote_image


def _avatar() -> Image.Image:
    return Image.new("RGB", (256, 256), (120, 130, 140))


def _render(text: str, **kwargs) -> Image.Image:
    png = render_quote_image(
        text=text,
        display_name="テスト太郎",
        username="test_taro",
        avatar=_avatar(),
        **kwargs,
    )
    img = Image.open(io.BytesIO(png))
    img.load()
    return img


def test_png_size_and_signature():
    png = render_quote_image(
        text="短い引用文",
        display_name="テスト太郎",
        username="test_taro",
        avatar=_avatar(),
    )
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    img = Image.open(io.BytesIO(png))
    assert img.size == (1200, 630)


def test_long_text_renders():
    img = _render("あ" * 300)
    assert img.size == (1200, 630)


def test_multiline_text_renders():
    img = _render("1行目\n2行目\n3行目")
    assert img.size == (1200, 630)


def test_fallback_avatar():
    img = fallback_avatar("まぶ")
    assert img.size == (630, 630)
    assert img.mode == "RGB"
    # 名前が違えば頭文字も色も変わる（ハッシュ依存）
    assert fallback_avatar("まぶ").tobytes() != fallback_avatar("たろう").tobytes()
    empty = fallback_avatar("")
    assert empty.size == (630, 630)


def test_render_with_emoji():
    def fetcher(url: str):
        return Image.new("RGBA", (72, 72), (0, 200, 0, 255))

    img = _render("絵文字つき😀テキスト", emoji_fetcher=fetcher)
    assert img.size == (1200, 630)


def test_render_with_all_emoji_failed():
    # 取得に全て失敗しても、テキストに戻して描画できる
    img = _render("絵文字つき😀テキスト", emoji_fetcher=lambda url: None)
    assert img.size == (1200, 630)


def test_render_with_emoji_in_display_name():
    def fetcher(url: str):
        return Image.new("RGBA", (72, 72), (0, 0, 200, 255))

    png = render_quote_image(
        text="本文",
        display_name="なまえ🎉",
        username="namae",
        avatar=_avatar(),
        emoji_fetcher=fetcher,
    )
    assert png[:4] == b"\x89PNG"
