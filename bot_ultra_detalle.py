import os
import json
import logging
import threading
from flask import Flask
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
import gspread
from google.oauth2.service_account import Credentials

# ================== 1. CONFIGURACIÓN DEL SERVIDOR FALSO (Flask) ==================
# Esto engaña a Render para que crea que somos una web y no nos apague.
web_app = Flask(__name__)

@web_app.route('/')
def health_check():
    return "¡El Bot está vivo y funcionando!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))  # Render nos da un puerto, lo usamos aquí
    web_app.run(host="0.0.0.0", port=port)

# ================== 2. LOGGING Y VARIABLES ==================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")

# ================== 3. GOOGLE SHEETS ==================
def conectar_sheets():
    # Verificamos que las credenciales existan para evitar errores si faltan
    if not GOOGLE_CREDS_JSON:
        print("⚠️ Error: No se encontró la variable GOOGLE_CREDS_JSON")
        return None
        
    creds_dict = json.loads(GOOGLE_CREDS_JSON)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(credentials)
    return client.open_by_key(SPREADSHEET_ID).sheet1

# Intentamos conectar al inicio
try:
    sheet = conectar_sheets()
except Exception as e:
    print(f"⚠️ Error conectando a Sheets: {e}")
    sheet = None

# ================== 4. COMANDOS DEL BOT ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Bot conectado correctamente.\nUsa /registrar Nombre Apellido"
    )

async def registrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if sheet is None:
        await update.message.reply_text("❌ Error: No hay conexión con la hoja de cálculo.")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ Uso correcto:\n/registrar Nombre Apellido")
        return

    nombre = context.args[0]
    apellido = context.args[1]

    try:
        sheet.append_row([nombre, apellido])
        await update.message.reply_text(f"✅ Guardado: {nombre} {apellido}")
    except Exception as e:
        await update.message.reply_text("❌ Error al guardar en Google Sheets.")
        print(f"Error escribiendo en Sheet: {e}")

# ================== 5. EJECUCIÓN PRINCIPAL ==================
def main():
    # A) Arrancar el servidor web en un hilo separado (segundo plano)
    print("🌍 Iniciando servidor web falso para Render...")
    threading.Thread(target=run_web_server, daemon=True).start()

    # B) Arrancar el Bot de Telegram
    if not TOKEN:
        print("❌ Error: No hay BOT_TOKEN definido en Render.")
        return

    print("🤖 Iniciando Bot de Telegram...")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("registrar", registrar))
    
    # Iniciar el polling (bucle infinito que escucha a Telegram)
    app.run_polling()
if __name__ == "__main__":
    main()
