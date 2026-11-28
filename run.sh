#!/usr/bin/env bash
# Make It a Quote Bot (Python 版) の起動
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -m makeitaquote
