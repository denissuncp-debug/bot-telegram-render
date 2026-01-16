import os
import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.constants import ParseMode
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
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot funcionando OK")

def run_simple_server():
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

sheet = conectar_sheets()

# ================== 5. COMANDOS DEL BOT ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **Bot Activo**\nUsa `/registrar [Datos]` o `/buscar [Nombre]`",
        parse_mode=ParseMode.MARKDOWN
    )

async def registrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global sheet
    if sheet is None:
        sheet = conectar_sheets()
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
        # Obtenemos TODOS los valores de la hoja
        valores = sheet.get_all_values()
        
        if not valores:
            await update.message.reply_text("⚠️ La hoja está vacía.")
            return

        # SEPARAR CABECERAS Y DATOS
        # La fila 0 son los títulos (DNI, Nombre, Cargo...)
        titulos = valores[0] 
        # El resto son los datos de las personas
        filas_datos = valores[1:] 

        encontrados = []
        
        for fila in filas_datos:
            # Convertimos la fila a texto para buscar la palabra clave
            contenido_fila = " ".join(fila).lower()
            
            if termino in contenido_fila:
                # ¡Encontrado! Ahora formateamos "Titulo: Valor"
                ficha = ""
                for i, dato in enumerate(fila):
                    # Solo mostramos si hay dato en esa celda
                    if dato.strip():
                        # Si existe titulo para esa columna lo usamos, si no ponemos "Dato"
                        nombre_titulo = titulos[i] if i < len(titulos) else f"Dato {i+1}"
                        ficha += f"🔹 *{nombre_titulo}:* {dato}\n"
                
                encontrados.append(ficha)

        if encontrados:
            # Enviamos los resultados (máximo 5 fichas para no llenar la pantalla)
            respuesta = f"✅ **Resultados encontrados ({len(encontrados)}):**\n\n"
            respuesta += "\n➖➖➖➖➖➖➖➖\n".join(encontrados[:5])
            
            if len(encontrados) > 5:
                respuesta += f"\n\n⚠️ _...y {len(encontrados)-5} resultados más. Sé más específico._"
            
            await update.message.reply_text(respuesta, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text("❌ No se encontraron coincidencias.")

    except Exception as e:
        await update.message.reply_text("❌ Error leyendo la hoja.")
        logger.error(f"Error búsqueda: {e}")

# ================== 6. EJECUCIÓN PRINCIPAL ==================
def main():
    hilo_server = threading.Thread(target=run_simple_server, daemon=True)
    hilo_server.start()

    if not TOKEN:
        logger.critical("❌ NO HAY TOKEN. Configura BOT_TOKEN en Render.")
        return

    logger.info("🤖 Iniciando polling de Telegram...")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("registrar", registrar))
    app.add_handler(CommandHandler("buscar", buscar))
    
    app.run_polling()

if __name__ == "__main__":
    main()
