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

# ================== 1. SERVIDOR FALSO (Para mantener vivo el Bot) ==================
web_app = Flask(__name__)

@web_app.route('/')
def health_check():
    return "¡Bot funcionando y listo para buscar!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

# ================== 2. CONFIGURACIÓN ==================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")

# ================== 3. CONEXIÓN A GOOGLE SHEETS ==================
def conectar_sheets():
    if not GOOGLE_CREDS_JSON:
        print("⚠️ Error: Falta la variable GOOGLE_CREDS_JSON")
        return None
        
    creds_dict = json.loads(GOOGLE_CREDS_JSON)
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(credentials)
    return client.open_by_key(SPREADSHEET_ID).sheet1

try:
    sheet = conectar_sheets()
except Exception as e:
    print(f"⚠️ Error inicial conectando a Sheets: {e}")
    sheet = None

# ================== 4. COMANDOS DEL BOT ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **Bot de Inventario/Registro**\n\n"
        "Comandos disponibles:\n"
        "📝 `/registrar [Dato1] [Dato2]` - Guarda información\n"
        "🔍 `/buscar [Texto]` - Busca en la hoja de cálculo"
    )

async def registrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if sheet is None:
        await update.message.reply_text("❌ Error: No hay conexión con la hoja.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Uso: `/registrar Juan Perez`")
        return

    # Unimos todo lo que escriba el usuario y lo guardamos
    datos = list(context.args)
    
    try:
        sheet.append_row(datos)
        await update.message.reply_text(f"✅ Guardado: {' '.join(datos)}")
    except Exception as e:
        await update.message.reply_text("❌ Error al guardar en Sheets (¿Permisos?).")
        print(f"Error Sheet: {e}")

async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if sheet is None:
        await update.message.reply_text("❌ Error: No hay conexión con la hoja.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Uso: `/buscar [Nombre o Dato]`")
        return

    busqueda = " ".join(context.args).lower()
    await update.message.reply_text(f"🔍 Buscando '{busqueda}'...")

    try:
        # Obtenemos TODOS los datos de la hoja
        registros = sheet.get_all_values()
        resultados = []

        # Buscamos fila por fila
        for fila in registros:
            texto_fila = " ".join(fila).lower()
            if busqueda in texto_fila:
                resultados.append(" | ".join(fila))

        if resultados:
            # Enviamos los resultados (máximo 10 para no saturar el chat)
            respuesta = "✅ **Encontrado:**\n\n" + "\n".join(resultados[:10])
            if len(resultados) > 10:
                respuesta += "\n\n(Mostrando solo los primeros 10 resultados)"
            await update.message.reply_text(respuesta)
        else:
            await update.message.reply_text("❌ No se encontraron coincidencias.")

    except Exception as e:
        await update.message.reply_text("❌ Error al leer la hoja.")
        print(f"Error leyendo: {e}")

# ================== 5. ARRANQUE ==================
def main():
    # Servidor Web (Segundo plano)
    threading.Thread(target=run_web_server, daemon=True).start()

    # Bot Telegram
    if not TOKEN:
        print("❌ Error: Falta BOT_TOKEN en Render.")
        return

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("registrar", registrar))
    app.add_handler(CommandHandler("buscar", buscar))
    
    print("🤖 Bot iniciado...")
    app.run_polling()
if __name__ == "__main__":
    main()
