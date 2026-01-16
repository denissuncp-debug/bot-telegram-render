import os
import csv
import json
import logging
import threading
import io
import asyncio
import requests # OBLIGATORIO: Asegúrate de tener 'requests' en requirements.txt
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
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ================== 1. CONFIGURACIÓN ==================
NOMBRE_HOJA_USUARIOS = "Usuarios" 
GITHUB_REPO = "jmcastagneto/datos-covid-19-peru" # Repositorio para búsquedas públicas

# 👇👇👇 CONFIGURACIÓN EXACTA DE TU CORREO 👇👇👇
API_URL_BASE = "https://dniruc.apisperu.com/api/v1/dni" 
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

def conectar_drive():
    creds = get_creds()
    if not creds: return None
    try:
        return build('drive', 'v3', credentials=creds)
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
    url = f"https://api.github.com/search/code?q={termino}+repo:{GITHUB_REPO}"
    try:
        response = requests.get(url)
        data = response.json()
        archivos = []
        if 'items' in data:
            for item in data['items']:
                nombre = item['name']
                # Convertimos enlace blob a raw para descarga directa
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

    teclado = [["🔍 Buscar Datos", "👤 Consultar DNI"], ["📂 Mis Archivos", "❓ Ayuda"]]
    if rol == 'Admin': teclado.insert(0, ["📢 Nuevo Anuncio"])
    
    markup = ReplyKeyboardMarkup(teclado, resize_keyboard=True)
    await update.message.reply_text(f"🤖 **Plataforma Integral**\nBienvenido {update.effective_user.first_name}", reply_markup=markup)

@usuario_registrado
async def manejar_botones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if texto == "🔍 Buscar Datos": await update.message.reply_text("🔎 Usa: `/buscar [nombre]`")
    elif texto == "👤 Consultar DNI": await update.message.reply_text("🆔 Usa: `/dni [numero]`")
    elif texto == "📂 Mis Archivos": await update.message.reply_text("📂 Usa: `/buscar [nombre archivo]`")
    elif texto == "📢 Nuevo Anuncio": await update.message.reply_text("📢 Usa: `/anuncio [mensaje]`")
    elif texto == "❓ Ayuda": await update.message.reply_text("ℹ️ Comandos:\n/dni [número] - Consulta RENIEC\n/buscar [texto] - Excel, Drive y GitHub\n/anuncio [msg] - Difusión")

# --- CONSULTA DNI (ADAPTADA A TU CORREO) ---
@usuario_registrado
async def consulta_dni(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Escribe el DNI. Ejemplo: `/dni 12345678`")
        return

    dni = context.args[0]
    if len(dni) != 8:
        await update.message.reply_text("❌ El DNI debe tener 8 dígitos.")
        return

    await update.message.reply_text(f"⏳ Consultando RENIEC para DNI: {dni}...")

    try:
        # Construimos la URL EXACTAMENTE como muestra tu correo: URL/DNI?token=TOKEN
        url_final = f"{API_URL_BASE}/{dni}?token={API_TOKEN}"

        # Hacemos la petición
        response = requests.get(url_final)

        if response.status_code == 200:
            data = response.json()
            
            # Extraemos los datos según la respuesta estándar de apisperu.com
            nombre = data.get('nombres') or "No data"
            apellido_p = data.get('apellidoPaterno') or ""
            apellido_m = data.get('apellidoMaterno') or ""
            cod_ver = data.get('codVerifica') or ""
            
            mensaje = (
                f"✅ **DNI ENCONTRADO:**\n\n"
                f"🆔 **Número:** `{dni}`\n"
                f"👤 **Nombres:** {nombre}\n"
                f"👪 **Apellidos:** {apellido_p} {apellido_m}\n"
            )
            if cod_ver: mensaje += f"🔢 **Cód. Verificación:** {cod_ver}"
            
            await update.message.reply_text(mensaje, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text("❌ No se encontraron datos o el Token expiró.")
            logger.error(f"Error API: {response.status_code}")
            
    except Exception as e:
        logger.error(f"Error técnico API: {e}")
        await update.message.reply_text("❌ Ocurrió un error de conexión con la API.")

# --- BÚSQUEDA HÍBRIDA (EXCEL + DRIVE + GITHUB) ---
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

    # 2. Drive
    drive = conectar_drive()
    if drive:
        q = f"name contains '{termino}' and trashed = false"
        res = drive.files().list(q=q, pageSize=1, fields="files(name, webViewLink)").execute()
        files = res.get('files', [])
        if files: mensajes.append(f"📎 **Drive:** [{files[0]['name']}]({files[0]['webViewLink']})")

    # 3. GitHub (COVID)
    github_files = buscar_en_github(termino)
    if github_files:
        mensajes.append("\n".join(github_files[:3]))

    if mensajes: await update.message.reply_text("\n\n".join(mensajes), parse_mode=ParseMode.MARKDOWN)
    else: await update.message.reply_text("❌ Sin resultados en ninguna base de datos.")

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
        self.wfile.write(b"Bot API DNI Full")

def run_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(('0.0.0.0', port), HealthCheckHandler).serve_forever()

def main():
    threading.Thread(target=run_server, daemon=True).start()
    if not TOKEN: return
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dni", consulta_dni))
    app.add_handler(CommandHandler("buscar", buscar))
    app.add_handler(CommandHandler("anuncio", anuncio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_botones))
    app.run_polling()

if __name__ == "__main__":
    main()
