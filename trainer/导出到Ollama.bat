@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
call ".venv\Scripts\activate.bat"
echo ============================================
echo  合并 LoRA 并注册到 Ollama
echo  (基座/LoRA/输出/模型名 可按需修改本 bat)
echo ============================================
python -m novel_trainer.export_ollama ^
    --base models/Qwen3-4B-Base ^
    --adapter outputs/novel_qwen_lora/final_adapter ^
    --out outputs/merged_novel ^
    --name novel-qwen
pause
endlocal
