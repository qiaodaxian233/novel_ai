@echo off
chcp 65001 >nul
setlocal
title 盘古写作引擎 - 一键打包 EXE(文件夹版)
cd /d "%~dp0"

echo ============================================================
echo   盘古写作引擎 一键打包(文件夹模式,免环境运行)
echo ============================================================
echo.

:: ── 1. 检查 Python ─────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python。请先安装 Python 3.9+ 并勾选 "Add to PATH"
    echo        下载: https://www.python.org/downloads/
    pause & exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo [1/4] Python %%v 就绪

:: ── 2. 安装依赖(清华镜像优先,失败回退官方源) ─────────────
echo [2/4] 安装依赖与 PyInstaller(首次较慢,请耐心)...
python -m pip install -r requirements.txt pyinstaller -q ^
    -i https://pypi.tuna.tsinghua.edu.cn/simple 2>nul
if errorlevel 1 (
    echo       镜像失败,改用官方源重试...
    python -m pip install -r requirements.txt pyinstaller -q
    if errorlevel 1 (
        echo [错误] 依赖安装失败,请检查网络后重试
        pause & exit /b 1
    )
)

:: ── 3. 打包(文件夹模式) ──────────────────────────────────
echo [3/4] 开始打包(约 2~5 分钟)...
python -m PyInstaller -y --clean "盘古写作引擎.spec"
if errorlevel 1 (
    echo [错误] 打包失败,请把上方红字截图反馈
    pause & exit /b 1
)

:: ── 4. 收尾:把运行时需要的文件放到 exe 旁 ─────────────────
echo [4/4] 整理产物...
copy /y "pangu_full_spec.md" "dist\盘古写作引擎\" >nul 2>&1
(
    echo 盘古写作引擎 - 使用说明
    echo ==========================================
    echo 1. 双击 盘古写作引擎.exe 即可运行,无需安装 Python。
    echo 2. 整个文件夹是一个整体:发给别人请打包整个文件夹
    echo    ^(右键 - 发送到 - 压缩文件夹^),不要只拷 exe。
    echo 3. _internal 文件夹是程序依赖,不要删除或改名。
    echo 4. AI 网站对接功能需要电脑装有 Chrome 或 Edge 浏览器。
    echo 5. TTS 朗读默认使用微软在线语音,需联网。
    echo 6. 项目数据保存在 "文档\NovelAI_Projects",卸载不丢失。
) > "dist\盘古写作引擎\使用说明.txt"

echo.
echo ============================================================
echo   打包完成!产物: dist\盘古写作引擎\
echo   把整个文件夹压缩发给别人即可免环境运行。
echo ============================================================
explorer "dist\盘古写作引擎"
pause
