import os
import csv
import json
import logging
import threading
import io
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

# ================== 1. CONFIGURACIÓN DE SEGURIDAD ==================
# ¡PON TU ID AQUÍ!
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
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in USUARIOS_PERMITIDOS:
            await update.message.reply_text("⛔ **ACCESO DENEGADO**", parse_mode=ParseMode.MARKDOWN)
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# ================== 4. SERVIDOR KEEP-ALIVE ==================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.wfile.write(b"Bot Drive Activo")

def run_simple_server():
    port = int(os.environ.get("PORT", 10000))
    httpd = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    httpd.serve_forever()

# ================== 5. CONEXIÓN GOOGLE SERVICES ==================
def get_creds():
    if not GOOGLE_CREDS_JSON: return None
    creds_dict = json.loads(GOOGLE_CREDS_JSON)
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    return Credentials.from_service_account_info(creds_dict, scopes=scope)

def conectar_sheets():
    creds = get_creds()
    if not creds: return None
    try:
        return gspread.authorize(creds).open_by_key(SPREADSHEET_ID).sheet1
    except Exception as e:
        logger.error(f"Error Sheets: {e}")
        return None

def conectar_drive():
    creds = get_creds()
    if not creds: return None
    try:
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        logger.error(f"Error Drive API: {e}")
        return None

sheet = conectar_sheets()
drive_service = conectar_drive()

# ================== 6. COMANDOS Y MENÚ ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    teclado = [["🔍 Buscar", "📝 Registrar"], ["📂 Exportar Todo", "🆔 Ver mi ID"], ["❓ Ayuda"]]
    markup = ReplyKeyboardMarkup(teclado, resize_keyboard=True)
    estado = "✅ AUTORIZADO" if user_id in USUARIOS_PERMITIDOS else "⛔ NO AUTORIZADO"
    
    await update.message.reply_text(
        f"🤖 **Bot Gestor + Archivos**\n👋 Hola, {update.effective_user.first_name}.\n🔐 Estado: **{estado}**",
        reply_markup=markup, parse_mode=ParseMode.MARKDOWN
    )

@restringido
async def manejar_botones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if texto == "🔍 Buscar": await update.message.reply_text("🔎 Escribe: `/buscar [Dato]`")
    elif texto == "📝 Registrar": await update.message.reply_text("✍️ Escribe: `/registrar [Datos...]`")
    elif texto == "📂 Exportar Todo": await exportar_archivo(update, context)
    elif texto == "🆔 Ver mi ID": await update.message.reply_text(f"🆔 ID: `{update.effective_user.id}`")
    elif texto == "❓ Ayuda": await update.message.reply_text("ℹ️ Busca archivos en Drive o datos en Excel.")

# --- EXPORTAR EXCEL ---
@restringido
async def exportar_archivo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global sheet
    if sheet is None: sheet = conectar_sheets()
    await update.message.reply_text("⏳ Generando reporte...")
    try:
        datos = sheet.get_all_values()
        if not datos: return await update.message.reply_text("📂 Hoja vacía.")
        
        with open("Reporte.csv", 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerows(datos)
        
        with open("Reporte.csv", 'rb') as f:
            await update.message.reply_document(document=f, caption="📊 Reporte CSV")
        os.remove("Reporte.csv")
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("❌ Error exportando.")

# --- REGISTRAR ---
@restringido
async def registrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global sheet
    if sheet is None: sheet = conectar_sheets()
    if not context.args: return await update.message.reply_text("⚠️ Faltan datos.")
    datos = [d.upper() for d in list(context.args)]
    try:
        sheet.append_row(datos)
        await update.message.reply_text(f"✅ Guardado: {' '.join(datos)}")
    except: await update.message.reply_text("❌ Error guardando.")

# --- NUEVO: BÚSQUEDA HÍBRIDA (EXCEL + DRIVE) ---
@restringido
async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global sheet, drive_service
    if sheet is None: sheet = conectar_sheets()
    if drive_service is None: drive_service = conectar_drive()

    if not context.args:
        await update.message.reply_text("⚠️ Ejemplo: `/buscar Factura`")
        return

    termino = " ".join(context.args) # Mantenemos mayúsculas/minúsculas originales para Drive
    termino_lower = termino.lower()
    
    await update.message.reply_text(f"🔍 Buscando '{termino}' en Base de Datos y Drive...")

    # 1. BÚSQUEDA EN GOOGLE SHEETS (TEXTO)
    encontrado_sheet = False
    try:
        vals = sheet.get_all_values()
        if vals:
            titulos, datos = vals[0], vals[1:]
            resultados = []
            for fila in datos:
                if termino_lower in " ".join(fila).lower():
                    ficha = " | ".join([f"{titulos[i]}: {d}" for i, d in enumerate(fila) if d.strip()])
                    resultados.append(ficha)
            
            if resultados:
                encontrado_sheet = True
                txt = "📄 **Datos en Excel:**\n" + "\n".join(resultados[:3])
                await update.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error Sheet: {e}")

    # 2. BÚSQUEDA EN GOOGLE DRIVE (ARCHIVOS)
    try:
        # Buscamos archivos que contengan el nombre y no estén en la papelera
        query = f"name contains '{termino}' and trashed = false"
        results = drive_service.files().list(q=query, pageSize=1, fields="files(id, name, mimeType)").execute()
        items = results.get('files', [])

        if not items:
            if not encontrado_sheet:
                await update.message.reply_text("❌ No encontré datos en Excel ni archivos en Drive.")
            else:
                await update.message.reply_text("📂 No se encontraron archivos adjuntos en Drive.")
            return

        # Si encontramos un archivo
        archivo = items[0]
        file_id = archivo['id']
        file_name = archivo['name']
        mime_type = archivo['mimeType']

        await update.message.reply_text(f"📎 **Archivo encontrado en Drive:**\n`{file_name}`\nDescargando y enviando...", parse_mode=ParseMode.MARKDOWN)

        # Lógica de Descarga
        request = drive_service.files().get_media(fileId=file_id)
        
        # Si es un Google Doc nativo (Doc, Sheet, Slide), hay que exportarlo a PDF
        if "application/vnd.google-apps" in mime_type:
            if "document" in mime_type:
                request = drive_service.files().export_media(fileId=file_id, mimeType='application/pdf')
                file_name += ".pdf"
            elif "spreadsheet" in mime_type:
                request = drive_service.files().export_media(fileId=file_id, mimeType='application/pdf')
                file_name += ".pdf"
            else:
                await update.message.reply_text("⚠️ Archivo de Google no soportado para descarga directa.")
                return

        # Descargar en memoria RAM (BytesIO) para no llenar el disco del servidor
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()

        fh.seek(0) # Volver al inicio del archivo en memoria
        
        # Enviar a Telegram
        await update.message.reply_document(document=fh, filename=file_name, caption=f"Aquí tienes el archivo: {file_name}")

    except Exception as e:
        logger.error(f"Error Drive: {e}")
        await update.message.reply_text("❌ Error al intentar descargar el archivo de Drive.")

# ================== 7. EJECUCIÓN ==================
def main():
    threading.Thread(target=run_simple_server, daemon=True).start()
    if not TOKEN: return
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("registrar", registrar))
    app.add_handler(CommandHandler("buscar", buscar))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_botones))
    app.run_polling()

if __name__ == "__main__":
    main()
