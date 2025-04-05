import logging
import asyncio
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ApplicationBuilder
)
from telegram.error import NetworkError, TelegramError
from datetime import datetime
import pytz
from typing import Optional
import sys
import socket

# Configuración del logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuración del bot
TOKEN = "7551775190:AAFerA1RVjKl7L7CeD6kKZ3c5dAf9iK-ZJY"
CHANNEL_ID = -1002302159104
MAX_RETRIES = 5
RETRY_DELAY = 3

class BotStatus:
    def __init__(self):
        self.start_time = datetime.now(pytz.UTC)
        self.error_count = 0
        self.last_error_time: Optional[datetime] = None
        self.last_error_message: Optional[str] = None
        self.successful_searches = 0

bot_status = BotStatus()

async def check_internet_connection():
    """Verifica la conexión a Internet."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False

async def retry_operation(func, *args, max_retries=MAX_RETRIES, delay=RETRY_DELAY):
    """Función genérica para reintentar operaciones."""
    for attempt in range(max_retries):
        try:
            return await func(*args)
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            logger.warning(f"Intento {attempt + 1} fallido: {str(e)}, reintentando...")
            await asyncio.sleep(delay)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /start."""
    try:
        user = update.effective_user
        welcome_message = (
            f"👋 ¡Hola {user.first_name}!\n\n"
            "Bienvenido al Bot Buscador de Películas y Series\n\n"
            "Comandos disponibles:\n"
            "/buscar <nombre> - Buscar una película o serie\n"
            "/help - Mostrar esta ayuda\n"
            "/status - Ver estado del bot\n"
            "/ping - Verificar conexión\n\n"
            "También puedes simplemente enviar el nombre de lo que quieres buscar."
        )
        await update.message.reply_text(welcome_message)
    except Exception as e:
        await handle_error(update, context, e)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /help."""
    help_text = (
        "🎬 *Instrucciones de uso:*\n\n"
        "1. Usa el comando `/buscar` seguido del nombre de la película o serie\n"
        "   Ejemplo: `/buscar Matrix`\n\n"
        "2. O simplemente envía el nombre de lo que buscas\n"
        "   Ejemplo: `Avatar`\n\n"
        "3. El bot buscará en el canal y te enviará los resultados encontrados\n\n"
        "📌 *Comandos disponibles:*\n"
        "/start - Iniciar el bot\n"
        "/help - Mostrar esta ayuda\n"
        "/buscar - Buscar contenido\n"
        "/status - Ver estado del bot\n"
        "/ping - Verificar conexión"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /status."""
    try:
        uptime = datetime.now(pytz.UTC) - bot_status.start_time
        hours = uptime.total_seconds() // 3600
        minutes = (uptime.total_seconds() % 3600) // 60

        status_message = (
            "📊 *Estado del Bot*\n\n"
            f"⏱ Tiempo activo: {int(hours)}h {int(minutes)}m\n"
            f"🔍 Búsquedas exitosas: {bot_status.successful_searches}\n"
            f"⚠️ Errores totales: {bot_status.error_count}\n"
            f"🕒 Último error: {bot_status.last_error_time.strftime('%Y-%m-%d %H:%M:%S') if bot_status.last_error_time else 'Ninguno'}\n"
            f"📝 Mensaje de error: {bot_status.last_error_message if bot_status.last_error_message else 'Ninguno'}"
        )
        await update.message.reply_text(status_message, parse_mode='Markdown')
    except Exception as e:
        await handle_error(update, context, e)

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /ping."""
    try:
        start_time = datetime.now()
        message = await update.message.reply_text("Verificando conexión...")
        
        internet_available = await check_internet_connection()
        api_available = False
        
        try:
            await context.bot.get_me()
            api_available = True
        except:
            pass

        end_time = datetime.now()
        response_time = (end_time - start_time).total_seconds() * 1000

        status_text = (
            "📊 *Estado de conexión*\n\n"
            f"🌐 Internet: {'✅ Conectado' if internet_available else '❌ Sin conexión'}\n"
            f"🤖 API Telegram: {'✅ Disponible' if api_available else '❌ No disponible'}\n"
            f"⚡ Tiempo de respuesta: {response_time:.0f}ms"
        )
        
        await message.edit_text(status_text, parse_mode='Markdown')
    except Exception as e:
        await handle_error(update, context, e)

async def handle_error(update: Update, context: ContextTypes.DEFAULT_TYPE, error: Exception) -> None:
    """Maneja errores de forma centralizada."""
    bot_status.error_count += 1
    bot_status.last_error_time = datetime.now(pytz.UTC)
    bot_status.last_error_message = str(error)
    
    logger.error(f"Error: {error}")
    
    error_message = (
        "❌ Ocurrió un error.\n"
        "Por favor, intenta nuevamente en unos momentos.\n"
        "Usa /status para ver el estado del bot."
    )
    
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(error_message)
    except Exception as e:
        logger.error(f"Error al enviar mensaje de error: {e}")

async def search_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Busca contenido en el canal."""
    if not update.message:
        return

    try:
        # Obtener término de búsqueda
        search_query = ' '.join(context.args) if context.args else update.message.text
        
        progress_message = await update.message.reply_text(
            f"🔎 Buscando: '{search_query}'...\n"
            "Por favor espera..."
        )

        messages = []
        
        try:
            async for message in context.bot.get_chat_history(CHANNEL_ID, limit=100):
                if (message.text and search_query.lower() in message.text.lower()) or \
                   (message.caption and search_query.lower() in message.caption.lower()):
                    messages.append(message)
        except Exception as e:
            logger.error(f"Error al obtener mensajes: {e}")
            await progress_message.edit_text(
                "❌ Error al buscar mensajes.\n"
                "Por favor, intenta nuevamente."
            )
            return

        if not messages:
            await progress_message.edit_text(
                "❌ No se encontraron resultados.\n"
                "Intenta con otro nombre o término más general."
            )
            return

        await progress_message.edit_text(f"🎯 Se encontraron {len(messages)} resultados:")

        sent_count = 0
        for msg in messages[:5]:
            try:
                await context.bot.copy_message(
                    chat_id=update.effective_chat.id,
                    from_chat_id=CHANNEL_ID,
                    message_id=msg.message_id
                )
                sent_count += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Error al copiar mensaje: {e}")
                continue

        if len(messages) > 5:
            await update.message.reply_text(
                f"ℹ️ Se mostraron {sent_count} de {len(messages)} resultados.\n"
                "Para ver más resultados, usa términos más específicos."
            )

        bot_status.successful_searches += 1

    except Exception as e:
        await handle_error(update, context, e)

def main() -> None:
    """Inicia el bot."""
    try:
        # Crear la aplicación con configuración básica
        application = (
            ApplicationBuilder()
            .token(TOKEN)
            .connection_pool_size(8)
            .build()
        )

        # Agregar manejadores
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("buscar", search_content))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("ping", ping_command))
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            search_content
        ))

        # Iniciar el bot
        print("Bot iniciado. Presiona Ctrl+C para detener.")
        print(f"Python version: {sys.version}")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    except Exception as e:
        logger.error(f"Error al iniciar el bot: {e}")
        raise

if __name__ == '__main__':
    main()
