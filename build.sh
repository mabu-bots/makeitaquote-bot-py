#!/usr/bin/env bash
# makeitaquote-bot-py 一括ビルド: 依存解決 → テスト
set -euo pipefail
cd "$(dirname "$0")"
python3 -m pip install -r requirements.txt
python3 -m pip install pytest
python3 -m pytest
echo "ビルドとテストが完了しました。起動: ./run.sh (.env が必要です)"
