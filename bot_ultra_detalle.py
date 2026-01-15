import os
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ================== CONFIG ==================
TOKEN = os.environ.get("TELEGRAM_TOKEN")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
LOG_SHEET_NAME = "Log_Busquedas"

# Validaciones claras
required_envs = [
    "TELEGRAM_TOKEN",
    "SPREADSHEET_ID",
    "GCP_PROJECT_ID",
    "GCP_PRIVATE_KEY_ID",
    "GCP_PRIVATE_KEY",
    "GCP_CLIENT_EMAIL",
    "GCP_CLIENT_ID",
    "GCP_CLIENT_CERT_URL",
]

for var in required_envs:
    if not os.environ.get(var):
        raise RuntimeError(f"❌ Falta variable de entorno: {var}")

# ================== GOOGLE SHEETS ==================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

creds_info = {
    "type": "service_account",
    "project_id": os.environ["GCP_PROJECT_ID"],
    "private_key_id": os.environ["GCP_PRIVATE_KEY_ID"],
    "private_key": os.environ["GCP_PRIVATE_KEY"].replace("\\n", "\n"),
    "client_email": os.environ["GCP_CLIENT_EMAIL"],
    "client_id": os.environ["GCP_CLIENT_ID"],
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": os.environ["GCP_CLIENT_CERT_URL"],
}

creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
client = gspread.authorize(creds)

spreadsheet = client.open_by_key(SPREADSHEET_ID)
sheet = spreadsheet.sheet1

# Crear hoja de log si no existe
try:
    log_sheet = spreadsheet.worksheet(LOG_SHEET_NAME)
except gspread.exceptions.WorksheetNotFound:
    log_sheet = spreadsheet.add_worksheet(
        title=LOG_SHEET_NAME, rows="1000", cols="6"
    )
    log_sheet.append_row(
        ["Fecha/Hora", "Telegram_ID", "Nombre", "Username", "Consulta", "Coincidencias"]
    )

# ================== COMANDOS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Bot activo 24/7.\n\n"
        "📌 Envía un DNI o código (parcial o completo)."
    )

async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip().lower()
    registros = sheet.get_all_records()

    resultados = []
    for fila in registros:
        if any(query in str(v).lower() for v in fila.values()):
            resultados.append(fila)

    user = update.effective_user
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_sheet.append_row([
        fecha,
        user.id,
        user.first_name,
        user.username or "",
        query,
        len(resultados),
    ])

    if resultados:
        await update.message.reply_text(
            f"🔍 Se encontraron {len(resultados)} coincidencias:"
        )
        for fila in resultados:
            texto = "\n".join(f"{k}: {v}" for k, v in fila.items())
            await update.message.reply_text(texto)
    else:
        await update.message.reply_text("❌ No se encontraron coincidencias.")

# ================== MAIN ==================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, buscar))

    print("🤖 Bot ejecutándose correctamente en Render (24/7)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
