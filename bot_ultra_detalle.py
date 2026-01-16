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

# 👇👇👇 TU CONFIGURACIÓN DE API (DNI Y RUC) 👇👇👇
API_URL_DNI = "https://dniruc.apisperu.com/api/v1/dni"
API_URL_RUC = "https://dniruc.apisperu.com/api/v1/ruc" # Nueva URL para RUC
API_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6ImRlbmlzc3VuY3BAZ21haWwuY29tIn0.34LKNuFfxwFk8EOudYPygH_LN1ptMKKwVfHoZA-5LJI"

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
    if not GOOGLE_CREDS_JSON: return None
    creds_dict = json.loads(GOOGLE_CREDS_JSON)
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    return Credentials.from_service_account_info(creds_dict, scopes=scope)

def conectar_sheets():
    creds = get_creds()
    if not creds: return None
    try:
        return gspread.authorize(creds).open_by_key(SPREADSHEET_ID)
    except: return None

# ================== 4. GESTIÓN DE PERMISOS ==================
def verificar_usuario(user_id):
    wb = conectar_sheets()
    if not wb: return None
    try:
        hoja = wb.worksheet(NOMBRE_HOJA_USUARIOS)
        registros = hoja.get_all_records()
        for reg in registros:
            if str(reg.get('ID_Telegram')) == str(user_id):
                return reg.get('Rol', 'Docente')
    except: return None
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

# ================== 5. LÓGICA GITHUB ==================
def buscar_en_github(termino):
    url = f"https://api.github.com/search/code?q={urllib.parse.quote(termino)}+repo:{GITHUB_REPO}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
        archivos = []
        if 'items' in data:
            for item in data['items']:
                nombre = item['name']
                link = item['html_url'].replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
                archivos.append(f"🐙 **GitHub:** [{nombre}]({link})")
        return archivos
    except: return []

# ================== 6. COMANDOS ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rol = verificar_usuario(user_id)
    
    if not rol:
        await update.message.reply_text("⛔ Acceso Denegado.")
        return

    # Menú Actualizado con RUC
    teclado = [
        ["🔍 Buscar Datos", "👤 DNI", "🏢 RUC"], 
        ["❓ Ayuda", "🆔 Mi ID"]
    ]
    if rol == 'Admin': teclado.insert(0, ["📢 Nuevo Anuncio"])
    
    markup = ReplyKeyboardMarkup(teclado, resize_keyboard=True)
    await update.message.reply_text(f"🤖 **Plataforma Integral**\nBienvenido {update.effective_user.first_name}", reply_markup=markup)

@usuario_registrado
async def manejar_botones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if texto == "🔍 Buscar Datos": await update.message.reply_text("🔎 Usa: `/buscar [nombre]`")
    elif texto == "👤 DNI": await update.message.reply_text("🆔 Usa: `/dni [numero]`")
    elif texto == "🏢 RUC": await update.message.reply_text("🏢 Usa: `/ruc [numero]`")
    elif texto == "📢 Nuevo Anuncio": await update.message.reply_text("📢 Usa: `/anuncio [mensaje]`")
    elif texto == "🆔 Mi ID": await update.message.reply_text(f"🆔 `{update.effective_user.id}`", parse_mode=ParseMode.MARKDOWN)
    elif texto == "❓ Ayuda": await update.message.reply_text("ℹ️ Comandos:\n/dni [8 dígitos]\n/ruc [11 dígitos]\n/buscar [texto]\n/anuncio [msg]")

# --- CONSULTA DNI ---
@usuario_registrado
async def consulta_dni(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("⚠️ Escribe el DNI: `/dni 12345678`")
    dni = context.args[0]
    if len(dni) != 8: return await update.message.reply_text("❌ El DNI debe tener 8 dígitos.")

    await update.message.reply_text(f"⏳ Consultando DNI: {dni}...")
    try:
        url_final = f"{API_URL_DNI}/{dni}?token={API_TOKEN}"
        req = urllib.request.Request(url_final, headers={'User-Agent': 'PythonBot'})
        
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                nombre = data.get('nombres') or "No data"
                ap_p = data.get('apellidoPaterno') or ""
                ap_m = data.get('apellidoMaterno') or ""
                cod = data.get('codVerifica') or ""
                
                msg = f"✅ **DNI ENCONTRADO:**\n🆔 `{dni}`\n👤 {nombre} {ap_p} {ap_m}"
                if cod: msg += f"\n🔢 Cód: {cod}"
                await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            else: await update.message.reply_text("❌ DNI no encontrado.")
    except Exception as e:
        logger.error(f"Error API: {e}")
        await update.message.reply_text("❌ Error de conexión.")

# --- CONSULTA RUC (NUEVO) ---
@usuario_registrado
async def consulta_ruc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("⚠️ Escribe el RUC: `/ruc 20100000001`")
    ruc = context.args[0]
    if len(ruc) != 11: return await update.message.reply_text("❌ El RUC debe tener 11 dígitos.")

    await update.message.reply_text(f"⏳ Consultando SUNAT para RUC: {ruc}...")
    try:
        url_final = f"{API_URL_RUC}/{ruc}?token={API_TOKEN}"
        req = urllib.request.Request(url_final, headers={'User-Agent': 'PythonBot'})
        
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                
                razon = data.get('razonSocial') or "Sin Nombre"
                estado = data.get('estado') or "-"
                condicion = data.get('condicion') or "-"
                direccion = data.get('direccion') or "-"
                ubigeo = data.get('ubigeo') or "-"
                
                # Iconos según estado
                icon_estado = "✅" if estado == "ACTIVO" else "⚠️"
                icon_cond = "✅" if condicion == "HABIDO" else "🚫"

                msg = (
                    f"🏢 **RUC ENCONTRADO:**\n\n"
                    f"🆔 **RUC:** `{ruc}`\n"
                    f"📛 **Razón Social:** {razon}\n"
                    f"{icon_estado} **Estado:** {estado}\n"
                    f"{icon_cond} **Condición:** {condicion}\n"
                    f"📍 **Dirección:** {direccion}\n"
                    f"🗺️ **Ubigeo:** {ubigeo}"
                )
                await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            else: await update.message.reply_text("❌ RUC no encontrado.")
    except Exception as e:
        logger.error(f"Error API RUC: {e}")
        await update.message.reply_text("❌ Error de conexión con SUNAT.")

# --- BÚSQUEDA HÍBRIDA ---
@usuario_registrado
async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("⚠️ Ejemplo: `/buscar informe`")
    termino = " ".join(context.args)
    await update.message.reply_text(f"🔍 Buscando '{termino}'...")

    mensajes = []
    # 1. Excel
    wb = conectar_sheets()
    if wb:
        hoja = wb.get_worksheet(0)
        vals = hoja.get_all_values()
        encontrados = [f"📊 {' '.join(f)}" for f in vals if termino.lower() in " ".join(f).lower()]
        if encontrados: mensajes.append("**Base de Datos:**\n" + "\n".join(encontrados[:3]))

    # 2. GitHub
    github_files = buscar_en_github(termino)
    if github_files: mensajes.append("\n".join(github_files[:3]))

    if mensajes: await update.message.reply_text("\n\n".join(mensajes), parse_mode=ParseMode.MARKDOWN)
    else: await update.message.reply_text("❌ Sin resultados.")

# --- ANUNCIO ---
async def anuncio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if verificar_usuario(user_id) != 'Admin': return
    
    msg = " ".join(context.args)
    wb = conectar_sheets()
    users = wb.worksheet(NOMBRE_HOJA_USUARIOS).get_all_records()
    
    enviados = 0
    for u in users:
        try: 
            await context.bot.send_message(chat_id=u['ID_Telegram'], text=f"📢 **COMUNICADO:**\n{msg}")
            enviados += 1
        except: pass
    await update.message.reply_text(f"✅ Enviado a {enviados} personas.")

# ================== SERVER ==================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.wfile.write(b"Bot DNI+RUC Activo")

def run_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(('0.0.0.0', port), HealthCheckHandler).serve_forever()

def main():
    threading.Thread(target=run_server, daemon=True).start()
    if not TOKEN: return
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dni", consulta_dni))
    app.add_handler(CommandHandler("ruc", consulta_ruc)) # COMANDO RUC AGREGADO
    app.add_handler(CommandHandler("buscar", buscar))
    app.add_handler(CommandHandler("anuncio", anuncio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_botones))
    app.run_polling()

if __name__ == "__main__":
    main()
