# ==========================================
# 🚀 エントリポイント
# ==========================================
# ▶️ python -m makeitaquote で起動する。
from .bot import run
from .config import load_config


def main() -> None:
    """設定を読み込んで Bot を起動する。"""
    run(load_config())


if __name__ == "__main__":
    main()
