@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo =============================================
echo  Novel AI Trainer - 首次安装 + 启动
echo  建议: Windows 10/11, Python 3.11, NVIDIA GPU
echo =============================================

where python >nul 2>nul
if errorlevel 1 (
  echo [错误] 没找到 Python。请先安装 Python 3.11 x64，并勾选 Add Python to PATH。
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] 创建虚拟环境...
  python -m venv .venv || goto :fail
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip setuptools wheel || goto :fail

echo [2/4] 安装 PyTorch 2.10 CUDA 12.6...
python -m pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cu126 || goto :fail

echo [3/4] 安装训练依赖...
python -m pip install -r requirements.txt || goto :fail

echo [4/4] 检查环境...
python -m novel_trainer.check_env

echo.
echo 启动 GUI...
python app.py
goto :end

:fail
echo.
echo [安装失败] 请复制上面的错误信息。
pause
exit /b 1

:end
endlocal
