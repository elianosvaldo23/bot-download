import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import NetworkError, TelegramError
from datetime import datetime
import pytz

# Configuración del logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuración del bot
TOKEN = "7551775190:AAFerA1RVjKl7L7CeD6kKZ3c5dAf9iK-ZJY"
CHANNEL_ID = -1002302159104
MAX_RETRIES = 3
RETRY_DELAY = 5

# Variables para el control de reintentos
last_error_time = None
error_count = 0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja el comando /start."""
    try:
        user = update.effective_user
        welcome_message = (
            f"👋 ¡Hola {user.first_name}!\n\n"
            "Bienvenido al Bot Buscador de Películas y Series\n\n"
            "Comandos disponibles:\n"
            "/buscar <nombre> - Buscar una película o serie\n"
            "/help - Mostrar esta ayuda\n"
            "/status - Ver estado del bot\n\n"
            "También puedes simplemente enviar el nombre de lo que quieres buscar."
        )
        await update.message.reply_text(welcome_message)
    except Exception as e:
        logger.error(f"Error en comando start: {e}")
        await handle_error(update, context, e)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja el comando /help."""
    try:
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
            "/status - Ver estado del bot"
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error en comando help: {e}")
        await handle_error(update, context, e)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el estado actual del bot."""
    try:
        utc_now = datetime.now(pytz.UTC)
        status_message = (
            "📊 *Estado del Bot*\n\n"
            f"🕒 Hora UTC: {utc_now.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"📡 Errores recientes: {error_count}\n"
            f"💾 Último error: {last_error_time.strftime('%Y-%m-%d %H:%M:%S') if last_error_time else 'Ninguno'}\n"
            f"🔄 Reintentos máximos: {MAX_RETRIES}\n"
            "✅ Bot en funcionamiento"
        )
        await update.message.reply_text(status_message, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error en comando status: {e}")
        await handle_error(update, context, e)

async def handle_error(update: Update, context: ContextTypes.DEFAULT_TYPE, error: Exception) -> None:
    """Maneja errores de forma centralizada."""
    global error_count, last_error_time
    
    error_count += 1
    last_error_time = datetime.now(pytz.UTC)
    
    error_message = (
        "❌ Ocurrió un error.\n"
        "Por favor, intenta nuevamente en unos momentos."
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
        if context.args:
            search_query = ' '.join(context.args)
        else:
            search_query = update.message.text

        progress_message = await update.message.reply_text(
            f"🔎 Buscando: '{search_query}'...\n"
            "Por favor espera..."
        )

        messages = []
        retry_count = 0

        while retry_count < MAX_RETRIES:
            try:
                # Intentar obtener mensajes del canal
                async for message in context.bot.get_chat_history(CHANNEL_ID, limit=100):
                    if message.text and search_query.lower() in message.text.lower():
                        messages.append(message)
                    elif message.caption and search_query.lower() in message.caption.lower():
                        messages.append(message)
                break
            except NetworkError as e:
                retry_count += 1
                if retry_count == MAX_RETRIES:
                    raise
                await asyncio.sleep(RETRY_DELAY)

        # Actualizar mensaje de progreso
        await progress_message.edit_text(
            f"🔍 Búsqueda completada para: '{search_query}'"
        )

        if not messages:
            await update.message.reply_text(
                "❌ No se encontraron resultados.\n"
                "Intenta con otro nombre o término más general."
            )
            return

        # Informar resultados
        results_message = f"🎯 Se encontraron {len(messages)} resultados:"
        await update.message.reply_text(results_message)

        # Enviar resultados
        sent_count = 0
        for msg in messages[:5]:  # Limitar a 5 resultados
            try:
                await context.bot.copy_message(
                    chat_id=update.effective_chat.id,
                    from_chat_id=CHANNEL_ID,
                    message_id=msg.message_id
                )
                sent_count += 1
                await asyncio.sleep(0.5)  # Pequeña pausa entre mensajes
            except TelegramError as e:
                logger.error(f"Error al copiar mensaje: {e}")
                continue

        if len(messages) > 5:
            await update.message.reply_text(
                f"ℹ️ Se mostraron {sent_count} de {len(messages)} resultados.\n"
                "Para ver más resultados, usa términos más específicos."
            )

    except Exception as e:
        logger.error(f"Error durante la búsqueda: {e}")
        await handle_error(update, context, e)

def main() -> None:
    """Inicia el bot."""
    try:
        # Crear la aplicación
        application = (
            Application.builder()
            .token(TOKEN)
            .connect_timeout(30.0)
            .read_timeout(30.0)
            .write_timeout(30.0)
            .build()
        )

        # Agregar manejadores
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("buscar", search_content))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            search_content
        ))

        # Iniciar el bot
        print("Bot iniciado. Presiona Ctrl+C para detener.")
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            pool_timeout=30.0
        )

    except Exception as e:
        logger.error(f"Error al iniciar el bot: {e}")
        raise

if __name__ == '__main__':
    main()
