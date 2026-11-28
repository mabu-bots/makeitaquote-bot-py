# ==========================================
# 😀 絵文字のトークン化と画像解決
# ==========================================
# 📝 引用文・表示名に含まれる絵文字を通常テキストと分離し、画像として
# 行内に描くためのモジュール。同梱フォントには絵文字グリフが無いため、
# Unicode 絵文字は Twemoji の PNG（72x72）、Discord カスタム絵文字は
# Discord CDN の静止画 PNG を取得して配置する。
#
# 🛡️ 取得には防御を適用する: 許可ホストのみ・5秒タイムアウト・
# 1MB 上限・Content-Type 確認。失敗した絵文字は、その絵文字だけを
# 元の文字列（テキスト）に戻して描画を続ける。
#
# 📖 絵文字の基底文字の判定は、本来 Unicode の Extended_Pictographic
# プロパティで行うが、Python の re には Unicode プロパティが無いため
# 範囲表で近似する。範囲表にあって Twemoji に画像が無い文字は、
# 取得失敗→テキスト表示へ自動で戻るため、過剰に一致しても壊れない。
from __future__ import annotations

import io
import re
import urllib.request
from dataclasses import dataclass
from typing import Callable, Union
from urllib.parse import urlparse

from PIL import Image


# ------------------------------------------
# 🔤 トークン
# ------------------------------------------
@dataclass
class TextToken:
    """通常テキストのトークン。"""

    text: str
    kind: str = "text"


@dataclass
class EmojiToken:
    """Unicode 絵文字のトークン。"""

    raw: str
    asset: str  # Twemoji のファイル名部分（主候補）
    kind: str = "emoji"


@dataclass
class CustomToken:
    """Discord カスタム絵文字のトークン。"""

    raw: str
    id: str
    animated: bool
    kind: str = "custom"


@dataclass
class ImageToken:
    """画像へ解決済みのトークン。"""

    raw: str
    image: Image.Image
    kind: str = "image"


RichToken = Union[TextToken, EmojiToken, CustomToken]  # 解決前（テキスト/絵文字/カスタム）
ResolvedToken = Union[TextToken, ImageToken]  # 解決後（テキスト/画像）


# ------------------------------------------
# 📖 絵文字の基底文字（Extended_Pictographic の範囲表による近似）
# ------------------------------------------
_EP_RANGES: list[tuple[int, int]] = [
    (0x00A9, 0x00A9), (0x00AE, 0x00AE), (0x203C, 0x203C), (0x2049, 0x2049),
    (0x2122, 0x2122), (0x2139, 0x2139), (0x2194, 0x2199), (0x21A9, 0x21AA),
    (0x231A, 0x231B), (0x2328, 0x2328), (0x2388, 0x2388), (0x23CF, 0x23CF),
    (0x23E9, 0x23F3), (0x23F8, 0x23FA), (0x24C2, 0x24C2), (0x25AA, 0x25AB),
    (0x25B6, 0x25B6), (0x25C0, 0x25C0), (0x25FB, 0x25FE), (0x2600, 0x2604),
    (0x260E, 0x260E), (0x2611, 0x2611), (0x2614, 0x2615), (0x2618, 0x2618),
    (0x261D, 0x261D), (0x2620, 0x2620), (0x2622, 0x2623), (0x2626, 0x2626),
    (0x262A, 0x262A), (0x262E, 0x262F), (0x2638, 0x263A), (0x2640, 0x2640),
    (0x2642, 0x2642), (0x2648, 0x2653), (0x265F, 0x2660), (0x2663, 0x2663),
    (0x2665, 0x2666), (0x2668, 0x2668), (0x267B, 0x267B), (0x267E, 0x267F),
    (0x2692, 0x2697), (0x2699, 0x2699), (0x269B, 0x269C), (0x26A0, 0x26A1),
    (0x26AA, 0x26AB), (0x26B0, 0x26B1), (0x26BD, 0x26BE), (0x26C4, 0x26C5),
    (0x26C8, 0x26C8), (0x26CE, 0x26CF), (0x26D0, 0x26D1), (0x26D3, 0x26D4),
    (0x26E9, 0x26E9), (0x26EA, 0x26EA), (0x26F0, 0x26F5), (0x26F7, 0x26FA),
    (0x26FD, 0x26FD), (0x2702, 0x2702), (0x2705, 0x2705), (0x2708, 0x270D),
    (0x270F, 0x270F), (0x2712, 0x2712), (0x2714, 0x2714), (0x2716, 0x2716),
    (0x271D, 0x271D), (0x2721, 0x2721), (0x2728, 0x2728), (0x2733, 0x2734),
    (0x2744, 0x2744), (0x2747, 0x2747), (0x274C, 0x274C), (0x274E, 0x274E),
    (0x2753, 0x2755), (0x2757, 0x2757), (0x2763, 0x2764), (0x2795, 0x2797),
    (0x27A1, 0x27A1), (0x27B0, 0x27B0), (0x27BF, 0x27BF), (0x2934, 0x2935),
    (0x2B05, 0x2B07), (0x2B1B, 0x2B1C), (0x2B50, 0x2B50), (0x2B55, 0x2B55),
    (0x3030, 0x3030), (0x303D, 0x303D), (0x3297, 0x3297), (0x3299, 0x3299),
    (0x1F000, 0x1FAFF),
]

_VS16 = "\uFE0F"  # バリエーションセレクタ16（絵文字表示の指定）
_ZWJ = "\u200D"  # ゼロ幅接合子（ZWJ 連結）
_KEYCAP = "\u20E3"  # キーキャップ結合文字
_SKIN_TONES = {chr(c) for c in range(0x1F3FB, 0x1F400)}  # 肌色修飾子 U+1F3FB..U+1F3FF
_TAG_MIN, _TAG_MAX = 0xE0020, 0xE007E  # タグ文字の範囲
_TAG_CANCEL = 0xE007F  # タグ並びの終端文字
_RI_MIN, _RI_MAX = 0x1F1E6, 0x1F1FF  # 国旗用 Regional Indicator の範囲

_CUSTOM_RE = re.compile(r"<(a)?:[A-Za-z0-9_]{2,32}:(\d+)>")


def _is_ep(cp: int) -> bool:
    """コードポイントが絵文字の基底文字かどうかを返す。"""
    # 🔢 範囲表は昇順（小さい範囲が手前、0x1F000- の大きな範囲が最後）
    for lo, hi in _EP_RANGES:
        if lo <= cp <= hi:
            return True
        if cp < lo:
            return False
    return False


def _consume_unit(text: str, i: int) -> int:
    """基底文字1つと、それに続く修飾（VS16・肌色は最大2つ、タグ並び）を消費し、末尾位置を返す。"""
    j = i + 1
    consumed = 0
    while j < len(text) and consumed < 2 and (text[j] == _VS16 or text[j] in _SKIN_TONES):
        j += 1
        consumed += 1
    # 🏷️ タグ並び: U+E0020..U+E007E が続き、U+E007F で終わる場合のみ消費する
    k = j
    while k < len(text) and _TAG_MIN <= ord(text[k]) <= _TAG_MAX:
        k += 1
    if k < len(text) and ord(text[k]) == _TAG_CANCEL and k > j:
        j = k + 1
    return j


# ------------------------------------------
# 🔗 Twemoji のアセット名と URL
# ------------------------------------------
def twemoji_asset_candidates(raw: str) -> list[str]:
    """Twemoji のファイル名候補を返す。

    コードポイントを16進で "-" 連結する。ZWJ を含まない並びでは
    U+FE0F を落とした名前が主候補、含む並びでは付けた名前が主候補。
    第2候補は FE0F の有無を反転した予備（取得失敗時に試す）。
    """
    code_points = [format(ord(ch), "x") for ch in raw]
    with_vs16 = "-".join(code_points)
    without_vs16 = "-".join(cp for cp in code_points if cp != "fe0f")
    primary = with_vs16 if "200d" in code_points else without_vs16
    secondary = without_vs16 if primary == with_vs16 else with_vs16
    return [primary] if primary == secondary else [primary, secondary]


def twemoji_url(asset: str) -> str:
    """Twemoji 画像の URL を作る。"""
    return f"https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/{asset}.png"


def custom_emoji_url(emoji_id: str) -> str:
    """Discord カスタム絵文字画像の URL を作る。"""
    return f"https://cdn.discordapp.com/emojis/{emoji_id}.png?size=96"


# ------------------------------------------
# ✂️ トークン化
# ------------------------------------------
def tokenize_rich_text(text: str) -> list[RichToken]:
    """テキストを通常テキストと絵文字のトークンへ分割する。"""
    tokens: list[RichToken] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            tokens.append(TextToken("".join(buf)))
            buf.clear()

    i = 0
    n = len(text)
    while i < n:
        # <:name:id> / <a:name:id> のカスタム絵文字
        m = _CUSTOM_RE.match(text, i)
        if m is not None:
            flush()
            tokens.append(
                CustomToken(raw=m.group(0), id=m.group(2), animated=m.group(1) == "a")
            )
            i = m.end()
            continue
        ch = text[i]
        cp = ord(ch)
        # 🚩 国旗（Regional Indicator のペア）
        if _RI_MIN <= cp <= _RI_MAX and i + 1 < n and _RI_MIN <= ord(text[i + 1]) <= _RI_MAX:
            flush()
            raw = text[i : i + 2]
            tokens.append(EmojiToken(raw=raw, asset=twemoji_asset_candidates(raw)[0]))
            i += 2
            continue
        # 🔢 キートップ（数字・#・* + 任意の VS16 + U+20E3）
        if ch in "0123456789#*":
            j = i + 1
            if j < n and text[j] == _VS16:
                j += 1
            if j < n and text[j] == _KEYCAP:
                flush()
                raw = text[i : j + 1]
                tokens.append(EmojiToken(raw=raw, asset=twemoji_asset_candidates(raw)[0]))
                i = j + 1
                continue
        # 😀 絵文字の並び（基底 + 修飾、ZWJ 連結を含む）
        if _is_ep(cp):
            j = _consume_unit(text, i)
            while j < n and text[j] == _ZWJ and j + 1 < n and _is_ep(ord(text[j + 1])):
                j = _consume_unit(text, j + 1)
            flush()
            raw = text[i:j]
            tokens.append(EmojiToken(raw=raw, asset=twemoji_asset_candidates(raw)[0]))
            i = j
            continue
        buf.append(ch)
        i += 1
    flush()
    if not tokens:
        tokens.append(TextToken(text))
    return tokens


def has_emoji_token(tokens: list[RichToken]) -> bool:
    """絵文字トークン（テキスト以外）を含むかどうかを返す。"""
    return any(t.kind != "text" for t in tokens)


# ------------------------------------------
# 🌐 画像の取得（防御つき）と解決
# ------------------------------------------
MAX_EMOJI_BYTES = 1024 * 1024  # 絵文字画像のサイズ上限（1MB）
ALLOWED_EMOJI_HOSTS = {"cdn.jsdelivr.net", "cdn.discordapp.com"}  # 取得を許可するホスト
EMOJI_FETCH_TIMEOUT_SECONDS = 5  # 絵文字取得のタイムアウト（秒）

EmojiFetcher = Callable[[str], "Image.Image | None"]  # 絵文字画像を取得する関数の型


def is_allowed_emoji_url(url: str) -> bool:
    """絵文字画像の URL が、許可ホストへの HTTPS かどうかを返す。"""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.hostname in ALLOWED_EMOJI_HOSTS


# 💾 取得結果のキャッシュ（失敗 = None もキャッシュする）
_emoji_image_cache: dict[str, Image.Image | None] = {}
_MAX_EMOJI_CACHE_ENTRIES = 256  # キャッシュの最大件数（古い順に1件ずつ捨てる）


def fetch_emoji_image(url: str) -> Image.Image | None:
    """絵文字画像を取得する（結果はキャッシュする）。"""
    if url in _emoji_image_cache:
        return _emoji_image_cache[url]
    result: Image.Image | None = None
    try:
        if is_allowed_emoji_url(url):
            req = urllib.request.Request(url, headers={"User-Agent": "makeitaquote-bot-py"})
            with urllib.request.urlopen(req, timeout=EMOJI_FETCH_TIMEOUT_SECONDS) as res:
                content_type = res.headers.get_content_type()
                if content_type.startswith("image/"):
                    data = res.read(MAX_EMOJI_BYTES + 1)
                    if len(data) <= MAX_EMOJI_BYTES:
                        img = Image.open(io.BytesIO(data))
                        img.load()
                        result = img.convert("RGBA")
    except Exception:
        result = None
    if len(_emoji_image_cache) >= _MAX_EMOJI_CACHE_ENTRIES:
        _emoji_image_cache.pop(next(iter(_emoji_image_cache)))
    _emoji_image_cache[url] = result
    return result


def resolve_rich_tokens(
    tokens: list[RichToken],
    fetcher: EmojiFetcher | None = None,
) -> list[ResolvedToken]:
    """トークン列の絵文字を画像へ解決する。失敗した絵文字はテキストへ戻す。"""
    fetch = fetcher if fetcher is not None else fetch_emoji_image
    resolved: list[ResolvedToken] = []
    for token in tokens:
        if isinstance(token, TextToken):
            resolved.append(token)
            continue
        image: Image.Image | None = None
        if isinstance(token, CustomToken):
            image = fetch(custom_emoji_url(token.id))
        else:
            for asset in twemoji_asset_candidates(token.raw):
                image = fetch(twemoji_url(asset))
                if image is not None:
                    break
        if image is not None:
            resolved.append(ImageToken(raw=token.raw, image=image))
        else:
            resolved.append(TextToken(token.raw))
    return resolved
