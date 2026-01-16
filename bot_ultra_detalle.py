import os
import csv
import json
import logging
import threading
import io
import asyncio
import requests # LIBRERÍA NUEVA PARA CONECTAR A GITHUB
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
# Configura aquí el repositorio que quieres usar (Usuario/Repositorio)
GITHUB_REPO = "jmcastagneto/datos-covid-19-peru" 

# ================== 2. LOGS Y VARIABLES ==================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON")

# ================== 3. CONEXIONES (GOOGLE & GITHUB) ==================
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
            await update.message.reply_text("⛔ No estás registrado.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# ================== 5. LÓGICA GITHUB (NUEVO) ==================
def buscar_en_github(termino):
    """Busca archivos en el repositorio público configurado"""
    url = f"https://api.github.com/search/code?q={termino}+repo:{GITHUB_REPO}"
    try:
        response = requests.get(url)
        data = response.json()
        
        archivos_encontrados = []
        if 'items' in data:
            for item in data['items']:
                nombre = item['name']
                link_descarga = item['html_url'].replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
                archivos_encontrados.append(f"🐙 **GitHub:** [{nombre}]({link_descarga})")
        return archivos_encontrados
    except Exception as e:
        logger.error(f"Error GitHub: {e}")
        return []

# ================== 6. COMANDOS ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rol = verificar_usuario(user_id)
    
    if not rol:
        await update.message.reply_text("⛔ Acceso Denegado. Pide al admin que te registre.")
        return

    teclado = [["🔍 Buscar", "📂 Mis Archivos"], ["❓ Ayuda", "🆔 Mi ID"]]
    if rol == 'Admin': teclado.insert(1, ["📢 Nuevo Anuncio"])
    
    markup = ReplyKeyboardMarkup(teclado, resize_keyboard=True)
    await update.message.reply_text(f"🤖 **Bot Conectado a GitHub**\nHola {update.effective_user.first_name}", reply_markup=markup)

@usuario_registrado
async def manejar_botones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if texto == "🔍 Buscar": await update.message.reply_text("🔎 Usa: `/buscar [nombre]`")
    elif texto == "📂 Mis Archivos": await update.message.reply_text("📂 Busca en Drive con `/buscar`")
    elif texto == "🆔 Mi ID": await update.message.reply_text(f"🆔 `{update.effective_user.id}`", parse_mode=ParseMode.MARKDOWN)
    elif texto == "📢 Nuevo Anuncio": await update.message.reply_text("📢 Usa: `/anuncio [mensaje]`")

@usuario_registrado
async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("⚠️ Ejemplo: `/buscar reporte`")
    
    termino = " ".join(context.args)
    await update.message.reply_text(f"🔍 Buscando '{termino}' en todas las bases de datos...")

    mensajes_respuesta = []

    # 1. BÚSQUEDA GOOGLE SHEETS
    wb = conectar_sheets()
    if wb:
        hoja = wb.get_worksheet(0)
        vals = hoja.get_all_values()
        encontrados_sheet = [f"📊 {' '.join(f)}" for f in vals if termino.lower() in " ".join(f).lower()]
        if encontrados_sheet:
            mensajes_respuesta.append("**Resultados en Excel:**\n" + "\n".join(encontrados_sheet[:3]))

    # 2. BÚSQUEDA GOOGLE DRIVE
    drive = conectar_drive()
    if drive:
        query = f"name contains '{termino}' and trashed = false"
        res = drive.files().list(q=query, pageSize=1, fields="files(id, name, webViewLink)").execute()
        files = res.get('files', [])
        if files:
            f = files[0]
            mensajes_respuesta.append(f"📎 **Google Drive:** [{f['name']}]({f['webViewLink']})")

    # 3. BÚSQUEDA GITHUB (NUEVO)
    resultados_github = buscar_en_github(termino)
    if resultados_github:
        mensajes_respuesta.append("\n".join(resultados_github[:3]))

    # ENVIAR RESULTADOS
    if mensajes_respuesta:
        await update.message.reply_text("\n\n".join(mensajes_respuesta), parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("❌ No encontré nada en Excel, Drive ni GitHub.")

# --- COMANDO ANUNCIO (Solo Admin) ---
async def anuncio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if verificar_usuario(user_id) != 'Admin': return
    
    msg = " ".join(context.args)
    wb = conectar_sheets()
    users = wb.worksheet(NOMBRE_HOJA_USUARIOS).get_all_records()
    
    for u in users:
        try: await context.bot.send_message(chat_id=u['ID_Telegram'], text=f"📢 **ANUNCIO:**\n{msg}", parse_mode=ParseMode.MARKDOWN)
        except: pass
    await update.message.reply_text("✅ Anuncio enviado.")

# ================== SERVER ==================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.wfile.write(b"Bot GitHub Activo")

def run_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(('0.0.0.0', port), HealthCheckHandler).serve_forever()

def main():
    threading.Thread(target=run_server, daemon=True).start()
    if not TOKEN: return
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("buscar", buscar))
    app.add_handler(CommandHandler("anuncio", anuncio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_botones))
    app.run_polling()

if __name__ == "__main__":
    main()
