# ==========================================
# 📝 テキスト折り返し（純ロジック）
# ==========================================
# 📏 描画幅の計測関数を引数で注入する設計にし、Pillow に依存させずに
# 単体テストできるようにしてある。日本語の禁則処理（行頭禁則・
# 行末禁則）の簡易版もここで扱う。
# 😀 絵文字を含むテキスト向けに、解決済みトークン列を折り返す版も置く。
# トークン版では画像を「フォントサイズ相当の正方形・分割不能な1単位」
# として扱い、幅は連続するテキストの実測と画像幅の合計で数える。
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .emoji import ImageToken, ResolvedToken, TextToken

# 🚫 行頭に置けない文字（句読点・閉じ括弧・長音・小書き仮名など）
NO_LINE_START = "、。，．！？：；）」』】〉》ー〜…‥・ゝゞ々ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮ"

# 🚫 行末に残せない文字（開き括弧）
NO_LINE_END = "（「『【〈《"

# 📏 文字列の描画幅を返す関数の型
MeasureFn = Callable[[str], float]

# 🧹 行頭で捨てる空白（半角スペースと全角スペース）
_LEADING_SPACES = (" ", "　")


# ------------------------------------------
# ✂️ プレーンテキストの折り返し
# ------------------------------------------
def wrap_text(text: str, max_width: float, measure: MeasureFn) -> list[str]:
    """テキストを max_width に収まる行へ分割する。改行は段落区切りとして尊重する。"""
    lines: list[str] = []
    for paragraph in text.replace("\r\n", "\n").split("\n"):
        if paragraph == "":
            lines.append("")
            continue
        line = ""
        for ch in paragraph:
            if line == "":
                if ch in _LEADING_SPACES:
                    continue  # 🧹 行頭の空白は捨てる
                line = ch
                continue
            if measure(line + ch) <= max_width:
                line += ch
                continue
            # ↩️ ここで折り返しが発生する
            if ch in NO_LINE_START:
                # 📌 行頭禁則: 前の行へ追い込む（多少はみ出しても崩さない）
                line += ch
                continue
            last = line[-1]
            if last in NO_LINE_END and len(line) >= 2:
                # 📌 行末禁則: 開き括弧は次の行へ送る
                lines.append(line[:-1])
                line = last + ch
                continue
            lines.append(line)
            line = "" if ch in _LEADING_SPACES else ch
        if line != "" or len(lines) == 0:
            lines.append(line)
    return lines


# ------------------------------------------
# 😀 絵文字トークンを含む折り返し
# ------------------------------------------
# 🧩 内部表現の単位: ("char", 文字) または ("image", ImageToken)
_Atom = tuple


def _to_atoms(tokens: list[ResolvedToken]) -> list[_Atom]:
    """トークン列を、文字と画像の単位列へ分解する。"""
    atoms: list[_Atom] = []
    for token in tokens:
        if isinstance(token, TextToken):
            atoms.extend(("char", ch) for ch in token.text)
        else:
            atoms.append(("image", token))
    return atoms


def _from_atoms(atoms: list[_Atom]) -> list[ResolvedToken]:
    """単位列をトークン列へ戻す。連続する文字は1つの TextToken にまとめる。"""
    tokens: list[ResolvedToken] = []
    for kind, value in atoms:
        if kind == "char":
            if tokens and isinstance(tokens[-1], TextToken):
                tokens[-1].text += value
            else:
                tokens.append(TextToken(value))
        else:
            tokens.append(value)
    return tokens


def measure_rich_atoms(atoms: list[_Atom], measure: MeasureFn, emoji_width: float) -> float:
    """単位列1行分の描画幅。テキストは連続部分ごとに実測し、画像は emoji_width で数える。"""
    width = 0.0
    run = ""
    for kind, value in atoms:
        if kind == "char":
            run += value
            continue
        if run:
            width += measure(run)
            run = ""
        width += emoji_width
    if run:
        width += measure(run)
    return width


def measure_rich_line(line: list[ResolvedToken], measure: MeasureFn, emoji_width: float) -> float:
    """トークン列1行分の描画幅を返す。"""
    return measure_rich_atoms(_to_atoms(line), measure, emoji_width)


def _split_paragraphs(tokens: list[ResolvedToken]) -> list[list[ResolvedToken]]:
    """トークン列を改行で段落へ分割する（画像トークンは段落内に残る）。"""
    paragraphs: list[list[ResolvedToken]] = [[]]
    for token in tokens:
        if not isinstance(token, TextToken):
            paragraphs[-1].append(token)
            continue
        parts = token.text.replace("\r\n", "\n").split("\n")
        for idx, part in enumerate(parts):
            if idx > 0:
                paragraphs.append([])
            if part != "":
                paragraphs[-1].append(TextToken(part))
    return paragraphs


def wrap_rich_text(
    tokens: list[ResolvedToken],
    max_width: float,
    measure: MeasureFn,
    emoji_width: float,
) -> list[list[ResolvedToken]]:
    """トークン列を max_width に収まる行（トークン列の配列）へ分割する。"""
    lines: list[list[_Atom]] = []
    for paragraph in _split_paragraphs(tokens):
        atoms = _to_atoms(paragraph)
        if not atoms:
            lines.append([])
            continue
        line: list[_Atom] = []
        for atom in atoms:
            if not line:
                # 🧹 行頭の空白文字は捨てる（画像は対象外）
                if atom[0] == "char" and atom[1] in _LEADING_SPACES:
                    continue
                line = [atom]
                continue
            if measure_rich_atoms(line + [atom], measure, emoji_width) <= max_width:
                line.append(atom)
                continue
            # ↩️ ここで折り返しが発生する
            if atom[0] == "char" and atom[1] in NO_LINE_START:
                # 📌 行頭禁則: 前の行へ追い込む
                line.append(atom)
                continue
            last = line[-1]
            if last[0] == "char" and last[1] in NO_LINE_END and len(line) >= 2:
                # 📌 行末禁則: 開き括弧は次の行へ送る
                lines.append(line[:-1])
                line = [last, atom]
                continue
            lines.append(line)
            line = [] if (atom[0] == "char" and atom[1] in _LEADING_SPACES) else [atom]
        if line or len(lines) == 0:
            lines.append(line)
    return [_from_atoms(line) for line in lines]


# ------------------------------------------
# 🔠 サイズ自動調整
# ------------------------------------------
@dataclass
class FitResult:
    """プレーンテキストのサイズ調整結果。"""

    font_size: int
    lines: list[str]
    line_height: int


@dataclass
class RichFitResult:
    """絵文字トークン版のサイズ調整結果。"""

    font_size: int
    lines: list
    line_height: int


def fit_quote_text(
    text: str,
    *,
    max_width: float,
    max_height: float,
    sizes: list[int],
    line_height_ratio: float,
    measure_at: Callable[[int], MeasureFn],
) -> FitResult:
    """max_width × max_height に収まる最大のフォントサイズと折り返し結果を返す。

    最小サイズでも収まらない場合は、入る行数で切り捨てて末尾に … を付ける。
    """
    ordered = sorted(sizes, reverse=True)
    for size in ordered:
        lines = wrap_text(text, max_width, measure_at(size))
        line_height = round(size * line_height_ratio)
        if len(lines) * line_height <= max_height:
            return FitResult(font_size=size, lines=lines, line_height=line_height)
    size = ordered[-1]
    line_height = round(size * line_height_ratio)
    max_lines = max(1, int(max_height // line_height))
    measure = measure_at(size)
    lines = wrap_text(text, max_width, measure)[:max_lines]
    # ✂️ 最終行に … を付ける（幅に収まるまで末尾を削る）
    last = lines[-1]
    while last and measure(last + "…") > max_width:
        last = last[:-1]
    lines[-1] = last + "…"
    return FitResult(font_size=size, lines=lines, line_height=line_height)


def fit_rich_text(
    tokens: list[ResolvedToken],
    *,
    max_width: float,
    max_height: float,
    sizes: list[int],
    line_height_ratio: float,
    measure_at: Callable[[int], MeasureFn],
) -> RichFitResult:
    """fit_quote_text のトークン版。絵文字はフォントサイズ相当の正方形として扱う。"""
    ordered = sorted(sizes, reverse=True)
    for size in ordered:
        lines = wrap_rich_text(tokens, max_width, measure_at(size), size)
        line_height = round(size * line_height_ratio)
        if len(lines) * line_height <= max_height:
            return RichFitResult(font_size=size, lines=lines, line_height=line_height)
    size = ordered[-1]
    line_height = round(size * line_height_ratio)
    max_lines = max(1, int(max_height // line_height))
    measure = measure_at(size)
    lines = wrap_rich_text(tokens, max_width, measure, size)[:max_lines]
    # ✂️ 最終行に … を付ける（幅に収まるまで末尾の単位を削る）
    last_atoms = _to_atoms(lines[-1])
    ellipsis: _Atom = ("char", "…")
    while last_atoms and measure_rich_atoms(last_atoms + [ellipsis], measure, size) > max_width:
        last_atoms.pop()
    last_atoms.append(ellipsis)
    lines[-1] = _from_atoms(last_atoms)
    return RichFitResult(font_size=size, lines=lines, line_height=line_height)
