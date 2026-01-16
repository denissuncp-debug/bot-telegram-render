import os
import json
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
import gspread
from google.oauth2.service_account import Credentials

# ================== LOGGING ==================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ================== VARIABLES DE ENTORNO ==================
TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")

# ================== GOOGLE SHEETS ==================
def conectar_sheets():
    creds_dict = json.loads(GOOGLE_CREDS_JSON)

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    credentials = Credentials.from_service_account_info(
        creds_dict,
        scopes=scopes
    )

    client = gspread.authorize(credentials)
    sheet = client.open_by_key(SPREADSHEET_ID).sheet1
    return sheet

sheet = conectar_sheets()

# ================== COMANDOS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Bot conectado correctamente.\nUsa /registrar para guardar datos."
    )

async def registrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "Uso correcto:\n/registrar Nombre Apellido"
        )
        return

    nombre = context.args[0]
    apellido = context.args[1]

    sheet.append_row([nombre, apellido])
    await update.message.reply_text("✅ Datos guardados correctamente")

# ================== MAIN ==================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("registrar", registrar))

    print("🤖 Bot ejecutándose correctamente en Render")
    app.run_polling()

if __name__ == "__main__":
    main()
