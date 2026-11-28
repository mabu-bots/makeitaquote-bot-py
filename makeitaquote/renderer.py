# ==========================================
# 🖼️ 名言画像レンダラ（Pillow）
# ==========================================
# 📐 本家「Make It a Quote」の出力形式に寄せたレイアウト:
# 左にグレースケール化したアバター写真（右へ向けて黒にフェード）、
# 右側に M PLUS Rounded 1c の引用文を中央寄せで置き、その下に
# 「- 表示名」と「@ユーザー名」を続ける。1200x630、モノクロ基調。
from __future__ import annotations

import colorsys
import io
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFont

from .emoji import (
    EmojiFetcher,
    ImageToken,
    TextToken,
    fetch_emoji_image,
    has_emoji_token,
    resolve_rich_tokens,
    tokenize_rich_text,
)
from .wrap import MeasureFn, fit_quote_text, fit_rich_text, measure_rich_line

# ------------------------------------------
# 📐 レイアウト定数
# ------------------------------------------
IMAGE_WIDTH = 1200  # 画像の幅（px）
IMAGE_HEIGHT = 630  # 画像の高さ（px）

BG = (0, 0, 0)  # 背景色（黒）
TEXT = (247, 245, 240)  # 引用文の文字色
NAME_TEXT = (239, 239, 239)  # 表示名の文字色
SUB_TEXT = (163, 163, 171)  # ユーザー名の文字色
CREDIT = (111, 111, 118)  # クレジットの文字色

AVATAR_WIDTH = 640  # アバター領域（左端から）。右端はフェードで隠れる
TEXT_CENTER_X = 862  # 本文ブロックの中心 x
TEXT_WIDTH = 596  # 本文の最大幅（564..1160）
QUOTE_MAX_HEIGHT = 372  # 引用文ブロックの最大の高さ

FADE_START = 280  # フェード開始 x
FADE_END = 620  # フェード完了 x（アバター右端 640 より手前）

QUOTE_FONT_FILE = "MPLUSRounded1c-Regular.ttf"  # 引用文・発言者名（本家のデフォルト font=mplus）
SANS_FONT_FILE = "NotoSansJP-Regular.ttf"  # クレジット・代替アバター

_fonts_dir: Path | None = None  # フォントディレクトリのキャッシュ


def _find_fonts_dir() -> Path:
    """assets/fonts の場所を探す（モジュールの場所から上方向に辿る）。"""
    global _fonts_dir
    if _fonts_dir is not None:
        return _fonts_dir
    here = Path(__file__).resolve().parent
    for base in (here, *here.parents):
        candidate = base / "assets" / "fonts"
        if (candidate / SANS_FONT_FILE).exists():
            _fonts_dir = candidate
            return candidate
    raise FileNotFoundError(f"フォントが見つかりません: assets/fonts/{SANS_FONT_FILE}")


def _font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    """フォント種別（quote / sans）とサイズから FreeType フォントを返す。"""
    name = QUOTE_FONT_FILE if kind == "quote" else SANS_FONT_FILE
    return ImageFont.truetype(str(_find_fonts_dir() / name), size)


def _measure_at(size: int) -> MeasureFn:
    """引用文フォントの、指定サイズでの描画幅計測関数を作る。"""
    font = _font("quote", size)
    return lambda s: font.getlength(s)


# ------------------------------------------
# 🌑 アバターのグレースケール化とフェード
# ------------------------------------------
def _grayscale_avatar(avatar: Image.Image) -> Image.Image:
    """アバターを領域（640x630）に cover で収め、グレースケール + 弱いコントラストを付ける。

    PIL の convert("L") は ITU-R 601-2 の輝度重み（0.299/0.587/0.114）を使う。
    """
    w, h = AVATAR_WIDTH, IMAGE_HEIGHT
    scale = max(w / avatar.width, h / avatar.height)
    resized = avatar.convert("RGB").resize(
        (max(1, round(avatar.width * scale)), max(1, round(avatar.height * scale))),
        Image.LANCZOS,
    )
    left = (resized.width - w) // 2
    top = (resized.height - h) // 2
    cropped = resized.crop((left, top, left + w, top + h))
    gray = ImageEnhance.Contrast(cropped.convert("L")).enhance(1.06)
    return gray.convert("RGB")


def _fade_mask() -> Image.Image:
    """左（不透明）から右（黒）へ直線で消えるグラデーションのマスクを作る。"""
    row = bytes(
        0
        if x <= FADE_START
        else 255
        if x >= FADE_END
        else round((x - FADE_START) / (FADE_END - FADE_START) * 255)
        for x in range(IMAGE_WIDTH)
    )
    strip = Image.frombytes("L", (IMAGE_WIDTH, 1), row)
    return strip.resize((IMAGE_WIDTH, IMAGE_HEIGHT))


# ------------------------------------------
# 😀 絵文字混じりテキストの描画
# ------------------------------------------
def _draw_rich_tokens(
    draw: ImageDraw.ImageDraw,
    surface: Image.Image,
    tokens: list,
    x: float,
    baseline_y: float,
    size: int,
    font: ImageFont.FreeTypeFont,
    fill: tuple,
    measure: MeasureFn,
) -> float:
    """解決済みトークン列を (x, baseline_y) から左寄せで描き、終端の x を返す。

    画像はフォントサイズ相当の正方形として、ベースラインの少し下に
    はみ出す位置（通常の絵文字表示と同じ比率）に配置する。
    """
    cursor = x
    for token in tokens:
        if isinstance(token, TextToken):
            if token.text:
                draw.text((cursor, baseline_y), token.text, font=font, fill=fill, anchor="ls")
                cursor += measure(token.text)
        elif isinstance(token, ImageToken):
            img = token.image.convert("RGBA").resize((size, size), Image.LANCZOS)
            surface.paste(img, (round(cursor), round(baseline_y - size * 0.86)), img)
            cursor += size
    return cursor


# ------------------------------------------
# 🎨 描画本体
# ------------------------------------------
def render_quote_image(
    *,
    text: str,
    display_name: str,
    username: str,
    avatar: Image.Image,
    emoji_fetcher: EmojiFetcher | None = None,
    credit: str = "Make It a Quote#3382",
) -> bytes:
    """名言画像を描画し、PNG のバイト列を返す。"""
    canvas = Image.new("RGB", (IMAGE_WIDTH, IMAGE_HEIGHT), BG)
    canvas.paste(_grayscale_avatar(avatar), (0, 0))
    canvas.paste(Image.new("RGB", (IMAGE_WIDTH, IMAGE_HEIGHT), BG), (0, 0), _fade_mask())

    draw = ImageDraw.Draw(canvas)
    fit_kwargs = dict(
        max_width=TEXT_WIDTH,
        max_height=QUOTE_MAX_HEIGHT,
        sizes=[62, 56, 50, 44, 38, 32, 27],
        line_height_ratio=1.42,
        measure_at=_measure_at,
    )

    # 📐 引用文 + 発言者ブロック全体を縦中央に配置する
    name_size = 29
    user_size = 22

    # 😀 絵文字が本文・表示名のどちらにも無ければ通常経路で描く。
    # 絵文字がある場合は、絵文字画像を行内に配置する経路で描く。
    text_tokens = tokenize_rich_text(text)
    name_tokens = tokenize_rich_text(display_name)
    rich = has_emoji_token(text_tokens) or has_emoji_token(name_tokens)

    name_layer = Image.new("RGBA", (IMAGE_WIDTH, IMAGE_HEIGHT), (0, 0, 0, 0))
    name_draw = ImageDraw.Draw(name_layer)

    if not rich:
        fit = fit_quote_text(text, **fit_kwargs)
        quote_block = len(fit.lines) * fit.line_height
        total_height = quote_block + 22 + name_size + 12 + user_size
        top = (IMAGE_HEIGHT - total_height) / 2

        quote_font = _font("quote", fit.font_size)
        for i, line in enumerate(fit.lines):
            y = top + fit.line_height * (i + 1.0)
            draw.text((TEXT_CENTER_X, y), line, font=quote_font, fill=TEXT, anchor="ms")

        # 👤 発言者名「- 表示名」（発言者ブロックは後段でまとめて傾ける）
        name_y = top + quote_block + 22 + name_size * 0.82
        name_draw.text(
            (TEXT_CENTER_X, name_y),
            f"- {display_name}",
            font=_font("quote", name_size),
            fill=NAME_TEXT + (255,),
            anchor="ms",
        )
    else:
        fetcher = emoji_fetcher if emoji_fetcher is not None else fetch_emoji_image
        resolved_text = resolve_rich_tokens(text_tokens, fetcher)
        resolved_name = resolve_rich_tokens(name_tokens, fetcher)
        fit = fit_rich_text(resolved_text, **fit_kwargs)
        quote_block = len(fit.lines) * fit.line_height
        total_height = quote_block + 22 + name_size + 12 + user_size
        top = (IMAGE_HEIGHT - total_height) / 2

        quote_font = _font("quote", fit.font_size)
        quote_measure = _measure_at(fit.font_size)
        for i, line in enumerate(fit.lines):
            y = top + fit.line_height * (i + 1.0)
            line_width = measure_rich_line(line, quote_measure, fit.font_size)
            _draw_rich_tokens(
                draw,
                canvas,
                line,
                TEXT_CENTER_X - line_width / 2,
                y,
                fit.font_size,
                quote_font,
                TEXT,
                quote_measure,
            )

        # 👤 発言者名「- 表示名」。絵文字は名前サイズの正方形で配置する
        name_y = top + quote_block + 22 + name_size * 0.82
        name_font = _font("quote", name_size)
        name_measure = _measure_at(name_size)
        prefix = "- "
        name_width = name_measure(prefix) + measure_rich_line(
            resolved_name, name_measure, name_size
        )
        name_x = TEXT_CENTER_X - name_width / 2
        name_draw.text(
            (name_x, name_y), prefix, font=name_font, fill=NAME_TEXT + (255,), anchor="ls"
        )
        name_x += name_measure(prefix)
        _draw_rich_tokens(
            name_draw,
            name_layer,
            resolved_name,
            name_x,
            name_y,
            name_size,
            name_font,
            NAME_TEXT + (255,),
            name_measure,
        )

    # 👤 ユーザー名も名前レイヤーに描き、発言者ブロック全体を一緒に傾ける（本家形式）
    user_y = name_y + 12 + user_size
    name_draw.text(
        # 剪断の原点が name_y のため、中心が合うよう x を補正する
        (TEXT_CENTER_X + 0.2 * (user_y - name_y), user_y),
        f"@{username}",
        font=_font("quote", user_size),
        fill=SUB_TEXT + (255,),
        anchor="ms",
    )
    # 🔀 擬似イタリック: 剪断変換（x' = x + 0.2 * (y - name_y) 相当）
    sheared = name_layer.transform(
        (IMAGE_WIDTH, IMAGE_HEIGHT),
        Image.AFFINE,
        (1, 0.2, -0.2 * name_y, 0, 1, 0),
        resample=Image.BICUBIC,
    )
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), sheared).convert("RGB"), (0, 0))
    draw = ImageDraw.Draw(canvas)

    # ©️ クレジット（右下）: 本家形式で Bot 自身のタグ（呼び出し側が渡す）
    draw.text(
        (IMAGE_WIDTH - 30, IMAGE_HEIGHT - 22),
        credit,
        font=_font("sans", 17),
        fill=CREDIT,
        anchor="rs",
    )

    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


def image_from_bytes(data: bytes) -> Image.Image:
    """バイト列を PIL 画像として読み込む。"""
    img = Image.open(io.BytesIO(data))
    img.load()
    return img


# ------------------------------------------
# 👤 アバター取得失敗時の代替画像
# ------------------------------------------
def fallback_avatar(display_name: str) -> Image.Image:
    """名前から決まる色のグラデーション + 頭文字の代替画像を作る。"""
    size = 630
    h = 0
    for ch in display_name:
        h = (h * 31 + ord(ch)) % 360

    def hsl(hue: float, sat: float, light: float) -> tuple[int, int, int]:
        r, g, b = colorsys.hls_to_rgb((hue % 360) / 360.0, light, sat)
        return (round(r * 255), round(g * 255), round(b * 255))

    c1 = hsl(h, 0.32, 0.30)
    c2 = hsl(h + 40, 0.36, 0.16)
    # 🎨 対角グラデーション（横グラデーションと縦グラデーションの平均）
    grad = Image.linear_gradient("L").resize((size, size))
    grad_x = grad.transpose(Image.TRANSPOSE)
    t = ImageChops.add(grad_x, grad, scale=2.0)
    base = Image.composite(Image.new("RGB", (size, size), c2), Image.new("RGB", (size, size), c1), t)

    initial = display_name[0] if display_name else "?"
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.text(
        (size / 2, size / 2 + 3),
        initial,
        font=_font("sans", 300),
        fill=(245, 243, 236, 235),
        anchor="mm",
    )
    return Image.alpha_composite(base.convert("RGBA"), layer).convert("RGB")
