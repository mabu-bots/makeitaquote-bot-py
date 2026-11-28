@echo off
rem makeitaquote-bot-py 一括ビルド: 依存解決 → テスト
setlocal
cd /d %~dp0
python -m pip install -r requirements.txt
if errorlevel 1 exit /b %errorlevel%
python -m pip install pytest
if errorlevel 1 exit /b %errorlevel%
python -m pytest
if errorlevel 1 exit /b %errorlevel%
echo ビルドとテストが完了しました。起動: python -m makeitaquote (.env が必要です)
endlocal
