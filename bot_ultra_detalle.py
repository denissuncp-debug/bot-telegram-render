import os
import json
import logging
import threading
from functools import wraps
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

# ================== 1. CONFIGURACIÓN DE SEGURIDAD (¡EDITAR ESTO!) ==================
# Poner aquí los IDs numéricos de las personas autorizadas.
# Ejemplo: [123456789, 987654321]
# El bot te dirá tu ID al usar /start si no lo sabes.
USUARIOS_PERMITIDOS = [964487835] 

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
    """Este 'portero' verifica si el usuario tiene permiso antes de dejarlo pasar."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in USUARIOS_PERMITIDOS:
            print(f"⛔ Intento de acceso no autorizado: {user_id} ({update.effective_user.first_name})")
            await update.message.reply_text(
                f"⛔ **ACCESO DENEGADO**\nNo tienes permiso para usar este bot.\n"
                f"Tu ID es: `{user_id}`\n(Envía este ID al administrador para solicitar acceso).",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# ================== 4. SERVIDOR KEEP-ALIVE ==================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.wfile.write(b"Bot Seguro Activo")

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

# ================== 6. COMANDOS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Este comando es público para que el usuario pueda averiguar su ID
    user_id = update.effective_user.id
    estado = "✅ AUTORIZADO" if user_id in USUARIOS_PERMITIDOS else "⛔ NO AUTORIZADO"
    
    await update.message.reply_text(
        f"🤖 **Bot de Gestión Seguro**\n\n"
        f"👋 Hola, {update.effective_user.first_name}.\n"
        f"🆔 Tu ID: `{user_id}`\n"
        f"🔐 Estado: **{estado}**\n\n"
        "Comandos (Solo autorizados):\n"
        "📝 `/registrar [Datos]`\n"
        "🔍 `/buscar [Nombre]`",
        parse_mode=ParseMode.MARKDOWN
    )

@restringido
async def registrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global sheet
    if sheet is None: sheet = conectar_sheets()
    
    if not context.args:
        await update.message.reply_text("⚠️ Uso: `/registrar Dato1 Dato2...`")
        return

    # Convertimos a MAYÚSCULAS para mantener orden
    datos = [d.upper() for d in list(context.args)]
    
    try:
        sheet.append_row(datos)
        await update.message.reply_text(f"✅ **Guardado:** {' '.join(datos)}", parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await update.message.reply_text("❌ Error guardando datos.")

@restringido
async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global sheet
    if sheet is None: sheet = conectar_sheets()

    if not context.args:
        await update.message.reply_text("⚠️ Uso: `/buscar Nombre`")
        return

    termino = " ".join(context.args).lower()
    await update.message.reply_text(f"🔍 Buscando '{termino}'...")

    try:
        vals = sheet.get_all_values()
        if not vals: 
            await update.message.reply_text("La hoja está vacía.")
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
            await update.message.reply_text("❌ No encontrado.")

    except Exception as e:
        logger.error(e)
        await update.message.reply_text("❌ Error técnico.")

# ================== 7. EJECUCIÓN ==================
def main():
    threading.Thread(target=run_simple_server, daemon=True).start()
    if not TOKEN: return

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("registrar", registrar))
    app.add_handler(CommandHandler("buscar", buscar))
    
    print("🤖 Bot Seguro Iniciado...")
    app.run_polling()
if __name__ == "__main__":
    main()
