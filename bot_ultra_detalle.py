import os
import json
from datetime import datetime

import gspread
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from google.oauth2.service_account import Credentials

# ================== VARIABLES DE ENTORNO ==================
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GOOGLE_CREDS = os.environ.get("GOOGLE_CREDENTIALS")

if not TOKEN:
    raise RuntimeError("❌ TELEGRAM_TOKEN no definido")

if not GOOGLE_CREDS:
    raise RuntimeError("❌ GOOGLE_CREDENTIALS no definido")

# ================== GOOGLE SHEETS ==================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = json.loads(GOOGLE_CREDS)
credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
client = gspread.authorize(credentials)

SPREADSHEET_NAME = "BD_Codigos_Bot"
LOG_SHEET_NAME = "Log_Busquedas"

sheet = client.open(SPREADSHEET_NAME).sheet1

try:
    log_sheet = client.open(SPREADSHEET_NAME).worksheet(LOG_SHEET_NAME)
except gspread.exceptions.WorksheetNotFound:
    log_sheet = client.open(SPREADSHEET_NAME).add_worksheet(
        title=LOG_SHEET_NAME, rows="1000", cols="6"
    )
    log_sheet.append_row(
        ["Fecha", "Telegram_ID", "Nombre", "Usuario", "Busqueda", "Coincidencias"]
    )

# ================== BOT ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Bot activo\n\n"
        "Envía un DNI o código (completo o parcial).\n"
        "Se mostrarán las coincidencias."
    )

async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip().lower()
    registros = sheet.get_all_records()

    resultados = []
    for fila in registros:
        for valor in fila.values():
            if texto in str(valor).lower():
                resultados.append(fila)
                break

    user = update.effective_user
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_sheet.append_row([
        fecha,
        user.id,
        user.first_name,
        user.username or "",
        texto,
        len(resultados)
    ])

    if resultados:
        await update.message.reply_text(f"🔍 {len(resultados)} coincidencia(s):")
        for fila in resultados:
            msg = "\n".join([f"{k}: {v}" for k, v in fila.items()])
            await update.message.reply_text(msg)
    else:
        await update.message.reply_text("❌ No se encontraron coincidencias")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, buscar))
    print("🤖 Bot iniciado")
    app.run_polling()

if __name__ == "__main__":
    main()

