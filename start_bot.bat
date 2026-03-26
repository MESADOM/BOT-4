@echo off
setlocal

if not exist .env (
  echo [INFO] No se encontro .env. Copiando desde .env.example...
  copy /Y .env.example .env >nul
)

python -m pip install -r requirements.txt
python run_paper_bot.py

endlocal
