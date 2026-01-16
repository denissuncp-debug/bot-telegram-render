import os
import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
import gspread
from google.oauth2.service_account import Credentials

# ================== 1. CONFIGURACIÓN DE LOGS ==================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================== 2. VARIABLES DE ENTORNO ==================
TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")

# ================== 3. SERVIDOR "KEEP-ALIVE" (SIMPLE) ==================
# Este servidor responde a Render inmediatamente para decir "Estoy vivo"
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot funcionando OK")

def run_simple_server():
    # Render asigna un puerto en la variable de entorno PORT. Por defecto 10000.
    port = int(os.environ.get("PORT", 10000))
    server_address = ('0.0.0.0', port)
    httpd = HTTPServer(server_address, HealthCheckHandler)
    logger.info(f"🌍 Servidor web escuchando en el puerto {port}")
    httpd.serve_forever()

# ================== 4. CONEXIÓN GOOGLE SHEETS ==================
def conectar_sheets():
    if not GOOGLE_CREDS_JSON:
        logger.error("⚠️ Falta la variable GOOGLE_CREDS_JSON")
        return None
        
    try:
        creds_dict = json.loads(GOOGLE_CREDS_JSON)
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(credentials)
        return client.open_by_key(SPREADSHEET_ID).sheet1
    except Exception as e:
        logger.error(f"⚠️ Error conectando a Sheets: {e}")
        return None

# Intentamos conectar una vez al inicio
sheet = conectar_sheets()

# ================== 5. COMANDOS DEL BOT ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **Bot Activo**\nUsa `/registrar [Datos]` o `/buscar [Nombre]`"
    )

async def registrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global sheet
    if sheet is None:
        sheet = conectar_sheets() # Reintentar conexión si falló antes
        if sheet is None:
            await update.message.reply_text("❌ Error de conexión con Google Sheets.")
            return

    if not context.args:
        await update.message.reply_text("⚠️ Escribe los datos. Ejemplo:\n`/registrar Juan Perez 30`")
        return

    datos = list(context.args)
    try:
        sheet.append_row(datos)
        await update.message.reply_text(f"✅ Guardado: {' '.join(datos)}")
    except Exception as e:
        await update.message.reply_text("❌ Error guardando datos.")
        logger.error(f"Error append_row: {e}")

async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global sheet
    if sheet is None:
        sheet = conectar_sheets()
        if sheet is None:
            await update.message.reply_text("❌ Error de conexión con Google Sheets.")
            return

    if not context.args:
        await update.message.reply_text("⚠️ Escribe qué buscar. Ejemplo:\n`/buscar Juan`")
        return

    termino = " ".join(context.args).lower()
    await update.message.reply_text(f"🔍 Buscando '{termino}'...")

    try:
        valores = sheet.get_all_values()
        encontrados = []
        for fila in valores:
            if termino in " ".join(fila).lower():
                encontrados.append(" | ".join(fila))
        
        if encontrados:
            msg = "✅ **Resultados:**\n" + "\n".join(encontrados[:8])
            await update.message.reply_text(msg)
        else:
            await update.message.reply_text("❌ No se encontraron coincidencias.")
    except Exception as e:
        await update.message.reply_text("❌ Error leyendo la hoja.")
        logger.error(f"Error búsqueda: {e}")

# ================== 6. EJECUCIÓN PRINCIPAL ==================
def main():
    # 1. Arrancar el servidor web en un hilo aparte (NO BLOQUEANTE)
    hilo_server = threading.Thread(target=run_simple_server, daemon=True)
    hilo_server.start()

    # 2. Verificar Token
    if not TOKEN:
        logger.critical("❌ NO HAY TOKEN. Configura BOT_TOKEN en Render.")
        return

    # 3. Arrancar el Bot
    logger.info("🤖 Iniciando polling de Telegram...")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("registrar", registrar))
    app.add_handler(CommandHandler("buscar", buscar))
    
    app.run_polling()

if __name__ == "__main__":
    main()
