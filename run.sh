#!/usr/bin/env bash
# Make It a Quote Bot (Python 版) の起動
set -euo pipefail
cd "$(dirname "$0")"
# 本番は venv 前提（システム Python には依存が無い）ため、venv があればそちらを使う
if [ -x "venv/bin/python" ]; then
  exec venv/bin/python -u -m makeitaquote
fi
exec python3 -m makeitaquote
