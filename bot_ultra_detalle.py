import os
import json
import logging
import threading
from functools import wraps
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ReplyKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
import gspread
from google.oauth2.service_account import Credentials

# ================== 1. CONFIGURACIÓN DE SEGURIDAD ==================
# ¡NO OLVIDES PONER TU ID AQUÍ! (El mismo que pusiste antes)
USUARIOS_PERMITIDOS = [123456789] 

# ================== 2. LOGS Y VARIABLES ==================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")

# ================== 3. DECORADOR DE SEGURIDAD ==================
def restringido(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in USUARIOS_PERMITIDOS:
            print(f"⛔ Intento no autorizado: {user_id}")
            await update.message.reply_text("⛔ **ACCESO DENEGADO**", parse_mode=ParseMode.MARKDOWN)
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# ================== 4. SERVIDOR KEEP-ALIVE ==================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.wfile.write(b"Bot Con Botones Activo")

def run_simple_server():
    port = int(os.environ.get("PORT", 10000))
    httpd = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    httpd.serve_forever()

# ================== 5. CONEXIÓN GOOGLE SHEETS ==================
def conectar_sheets():
    if not GOOGLE_CREDS_JSON: return None
    try:
        creds = json.loads(GOOGLE_CREDS_JSON)
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        return gspread.authorize(Credentials.from_service_account_info(creds, scopes=scope)).open_by_key(SPREADSHEET_ID).sheet1
    except Exception as e:
        logger.error(f"Error Sheets: {e}")
        return None

sheet = conectar_sheets()

# ================== 6. COMANDOS Y BOTONES ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Definimos el diseño de los botones
    teclado = [
        ["🔍 Buscar", "📝 Registrar"],
        ["🆔 Ver mi ID", "❓ Ayuda"]
    ]
    markup = ReplyKeyboardMarkup(teclado, resize_keyboard=True) # resize=True hace que no ocupen media pantalla
    
    estado = "✅ AUTORIZADO" if user_id in USUARIOS_PERMITIDOS else "⛔ NO AUTORIZADO"
    
    await update.message.reply_text(
        f"🤖 **Sistema de Gestión**\n"
        f"👋 Hola, {update.effective_user.first_name}.\n"
        f"🔐 Estado: **{estado}**\n\n"
        "👇 **Usa los botones del menú abajo:**",
        reply_markup=markup,
        parse_mode=ParseMode.MARKDOWN
    )

# Función para manejar los clics en los botones (que envían texto)
@restringido
async def manejar_botones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    
    if texto == "🔍 Buscar":
        await update.message.reply_text("🔎 Para buscar, escribe el comando así:\n`/buscar [Nombre o DNI]`", parse_mode=ParseMode.MARKDOWN)
    
    elif texto == "📝 Registrar":
        await update.message.reply_text("✍️ Para registrar, escribe los datos así:\n`/registrar [Dato1] [Dato2] ...`", parse_mode=ParseMode.MARKDOWN)
        
    elif texto == "🆔 Ver mi ID":
        await update.message.reply_text(f"🆔 Tu ID de Telegram es: `{update.effective_user.id}`", parse_mode=ParseMode.MARKDOWN)
        
    elif texto == "❓ Ayuda":
        await update.message.reply_text("ℹ️ **Ayuda:**\nUsa /registrar para guardar datos en la hoja.\nUsa /buscar para encontrar información existente.", parse_mode=ParseMode.MARKDOWN)

@restringido
async def registrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global sheet
    if sheet is None: sheet = conectar_sheets()
    
    if not context.args:
        await update.message.reply_text("⚠️ **Faltan datos.**\nEscribe: `/registrar Juan Perez 123456`", parse_mode=ParseMode.MARKDOWN)
        return

    datos = [d.upper() for d in list(context.args)]
    try:
        sheet.append_row(datos)
        await update.message.reply_text(f"✅ **Guardado Exitosamente:**\n{' '.join(datos)}", parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await update.message.reply_text("❌ Error conectando con la hoja.")

@restringido
async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global sheet
    if sheet is None: sheet = conectar_sheets()

    if not context.args:
        await update.message.reply_text("⚠️ **Falta el nombre.**\nEscribe: `/buscar Juan`", parse_mode=ParseMode.MARKDOWN)
        return

    termino = " ".join(context.args).lower()
    await update.message.reply_text(f"🔍 Buscando '{termino}'...")

    try:
        vals = sheet.get_all_values()
        if not vals: 
            await update.message.reply_text("📂 La hoja está vacía.")
            return

        titulos, datos = vals[0], vals[1:]
        encontrados = []

        for fila in datos:
            if termino in " ".join(fila).lower():
                ficha = ""
                for i, dato in enumerate(fila):
                    if dato.strip():
                        t = titulos[i] if i < len(titulos) else f"Dato {i+1}"
                        ficha += f"🔹 *{t}:* {dato}\n"
                encontrados.append(ficha)

        if encontrados:
            res = f"✅ **Resultados ({len(encontrados)}):**\n\n" + "\n➖➖➖\n".join(encontrados[:5])
            await update.message.reply_text(res, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text("❌ No se encontraron coincidencias.")

    except Exception as e:
        logger.error(e)
        await update.message.reply_text("❌ Error técnico.")

# ================== 7. EJECUCIÓN ==================
def main():
    threading.Thread(target=run_simple_server, daemon=True).start()
    if not TOKEN: return

    app = Application.builder().token(TOKEN).build()
    
    # Comandos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("registrar", registrar))
    app.add_handler(CommandHandler("buscar", buscar))
    
    # Manejador para los botones de texto (Menú)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_botones))
    
    print("🤖 Bot con Botones Iniciado...")
    app.run_polling()

if __name__ == "__main__":
    main()
