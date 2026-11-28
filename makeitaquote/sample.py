# ==========================================
# 🖼️ サンプル画像の生成
# ==========================================
# ▶️ python -m makeitaquote.sample で docs/sample.png を生成する。
# ダミーのシルエットアバターで描画する（実在ユーザーのアバターは使わない）。
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from .renderer import render_quote_image


def dummy_avatar() -> Image.Image:
    """ダミーのシルエットアバター画像を作る。"""
    size = 630
    img = Image.new("RGB", (size, size), (38, 42, 54))
    draw = ImageDraw.Draw(img)
    # 🎨 縦グラデーション風の背景
    for y in range(size):
        t = y / size
        draw.line(
            [(0, y), (size, y)],
            fill=(
                round(58 - 26 * t),
                round(63 - 27 * t),
                round(76 - 30 * t),
            ),
        )
    # 👤 人型シルエット
    draw.ellipse([size / 2 - 105, 120, size / 2 + 105, 330], fill=(16, 17, 20))
    draw.ellipse([size / 2 - 235, 395, size / 2 + 235, 760], fill=(16, 17, 20))
    return img


def main() -> None:
    """サンプル画像を生成して docs/sample.png に保存する。"""
    png = render_quote_image(
        text="明日から本気出すって、昨日も言ってた気がするんだよな",
        display_name="まぶ",
        username="xx_mabu_xx",
        avatar=dummy_avatar(),
    )
    out = Path(__file__).resolve().parent.parent / "docs" / "sample.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)
    print(f"docs/sample.png を生成しました: {len(png)} bytes")


if __name__ == "__main__":
    main()
