import os
import json
import logging
import threading
import urllib.request
import urllib.error
import urllib.parse
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

# ================== 1. CONFIGURACIÓN ==================

NOMBRE_HOJA_USUARIOS = "Usuarios"
GITHUB_REPO = "jmcastagneto/datos-covid-19-peru"

# 🔹 NUEVO PROVEEDOR PERUDEVS
API_URL_DNI = "https://api.perudevs.com/api/v1/dni/complete"
API_KEY = os.getenv("PERUDEVS_KEY")  # 👉 Coloca tu API KEY en Render

# ================== 2. LOGS Y VARIABLES ==================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")

# ================== 3. CONEXIONES ==================

def get_creds():
    if not GOOGLE_CREDS_JSON:
        return None
    creds_dict = json.loads(GOOGLE_CREDS_JSON)
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    return Credentials.from_service_account_info(creds_dict, scopes=scope)

def conectar_sheets():
    creds = get_creds()
    if not creds:
        return None
    try:
        return gspread.authorize(creds).open_by_key(SPREADSHEET_ID)
    except:
        return None

# ================== 4. GESTIÓN DE PERMISOS ==================

def verificar_usuario(user_id):
    wb = conectar_sheets()
    if not wb:
        return None
    try:
        hoja = wb.worksheet(NOMBRE_HOJA_USUARIOS)
        registros = hoja.get_all_records()
        for reg in registros:
            if str(reg.get('ID_Telegram')) == str(user_id):
                return reg.get('Rol', 'Docente')
    except:
        return None
    return None

def usuario_registrado(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if not verificar_usuario(user_id):
            await update.message.reply_text("⛔ No estás registrado. Pide acceso al Admin.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# ================== 5. COMANDOS ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rol = verificar_usuario(user_id)

    if not rol:
        await update.message.reply_text("⛔ Acceso Denegado.")
        return

    teclado = [
        ["👤 DNI"],
        ["❓ Ayuda", "🆔 Mi ID"]
    ]

    markup = ReplyKeyboardMarkup(teclado, resize_keyboard=True)

    await update.message.reply_text(
        f"🤖 **Plataforma Integral**\nBienvenido {update.effective_user.first_name}",
        reply_markup=markup,
        parse_mode=ParseMode.MARKDOWN
    )

# ================== CONSULTA DNI (PERUDEVS) ==================

@usuario_registrado
async def consulta_dni(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not context.args:
        return await update.message.reply_text("⚠️ Usa: `/dni 12345678`")

    dni = context.args[0]

    if not dni.isdigit() or len(dni) != 8:
        return await update.message.reply_text("❌ El DNI debe tener 8 dígitos numéricos.")

    if not API_KEY:
        return await update.message.reply_text("❌ API KEY no configurada en el servidor.")

    await update.message.reply_text(f"⏳ Consultando DNI: {dni}...")

    try:
        params = urllib.parse.urlencode({
            "document": dni,
            "key": API_KEY
        })

        url_final = f"{API_URL_DNI}?{params}"

        req = urllib.request.Request(url_final)
        req.add_header('User-Agent', 'Mozilla/5.0')

        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())

            # Validamos según tu estructura:
            # estado : verdadero
            # mensaje : "Encontrado"
            # resultado : { ... }

            if not data.get("estado"):
                return await update.message.reply_text("❌ DNI no encontrado.")

            resultado = data.get("resultado", {})

            nombres = resultado.get("nombres", "")
            apellido_p = resultado.get("apellido_paterno", "")
            apellido_m = resultado.get("apellido_materno", "")
            nombre_completo = resultado.get("nombre_completo", "")
            genero = resultado.get("género", "")
            fecha_nacimiento = resultado.get("fecha_nacimiento", "")
            codigo_verificacion = resultado.get("codigo_verificacion", "")

            mensaje = (
                f"✅ **DNI ENCONTRADO**\n\n"
                f"🆔 **DNI:** `{dni}`\n"
                f"👤 **Nombre:** {nombre_completo}\n"
                f"👥 **Nombres:** {nombres}\n"
                f"📛 **Apellido Paterno:** {apellido_p}\n"
                f"📛 **Apellido Materno:** {apellido_m}\n"
                f"🚻 **Género:** {genero}\n"
                f"🎂 **Fecha Nacimiento:** {fecha_nacimiento}\n"
                f"🔢 **Código Verificación:** {codigo_verificacion}"
            )

            await update.message.reply_text(mensaje, parse_mode=ParseMode.MARKDOWN)

    except urllib.error.HTTPError as e:
        logger.error(f"HTTP Error: {e.code}")
        await update.message.reply_text(f"❌ Error del servidor ({e.code}). Revisa tu API KEY.")

    except Exception as e:
        logger.error(f"Error técnico DNI: {e}")
        await update.message.reply_text("❌ Error de conexión con PeruDevs.")

# ================== MENÚ BOTONES ==================

@usuario_registrado
async def manejar_botones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text

    if texto == "👤 DNI":
        await update.message.reply_text("🆔 Usa: `/dni 12345678`")
    elif texto == "🆔 Mi ID":
        await update.message.reply_text(f"🆔 `{update.effective_user.id}`", parse_mode=ParseMode.MARKDOWN)
    elif texto == "❓ Ayuda":
        await update.message.reply_text("ℹ️ Comandos:\n/dni [8 dígitos]")

# ================== SERVER (RENDER / UPTIMEROBOT) ==================

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.wfile.write(b"Bot Activo")

    def do_HEAD(self):
        self.send_response(200)

def run_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(('0.0.0.0', port), HealthCheckHandler).serve_forever()

# ================== MAIN ==================

def main():
    threading.Thread(target=run_server, daemon=True).start()

    if not TOKEN:
        return

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dni", consulta_dni))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_botones))

    app.run_polling()

if __name__ == "__main__":
    main()
