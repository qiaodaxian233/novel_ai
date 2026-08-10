@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo 尚未安装环境，请先双击“安装并启动.bat”。
  pause
  exit /b 1
)
call ".venv\Scripts\activate.bat"
python -m novel_trainer.check_env
pause
