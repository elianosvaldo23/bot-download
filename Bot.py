import logging
import asyncio
import re
import time
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode, ChatAction
from telegram.error import TelegramError

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
TOKEN = "7551775190:AAFQTB-apYbboDNq-sYwYQaZXrmmxIoNuRo"
CHANNEL_ID = -1002302159104

# Store the latest message ID
last_message_id = 0

# Cache for message content to avoid repeated requests
message_cache = {}

# Cache for search results to speed up repeated searches
search_cache = {}

# Cache expiration time (in seconds)
CACHE_EXPIRATION = 3600  # 1 hour

# Maximum number of messages to search
MAX_SEARCH_MESSAGES = 1000

# Maximum number of results to show
MAX_RESULTS = 10

# User preferences (store user settings)
user_preferences = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    await update.message.reply_text(
        "¡Hola! Soy un bot de búsqueda de películas y series. "
        "Envíame el nombre de lo que estás buscando y te enviaré los resultados directamente.\n\n"
        "Comandos disponibles:\n"
        "/start - Iniciar el bot\n"
        "/help - Mostrar ayuda\n"
        "/config - Configurar preferencias\n"
        "/recientes - Ver contenido reciente"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "🎬 *Bot de Búsqueda de Películas y Series* 🎬\n\n"
        "*Comandos disponibles:*\n"
        "/start - Iniciar el bot\n"
        "/help - Mostrar esta ayuda\n"
        "/config - Configurar preferencias\n"
        "/recientes - Ver contenido reciente\n\n"
        "*Búsqueda:*\n"
        "- Simplemente envía el nombre de la película o serie\n"
        "- Puedes usar '#película' o '#serie' para filtrar\n"
        "- Usa '+año' para buscar por año (ej: 'Avatar +2009')\n\n"
        "*Consejos:*\n"
        "- Sé específico en tus búsquedas\n"
        "- Los resultados se ordenan por relevancia\n"
        "- El contenido está protegido contra reenvío",
        parse_mode=ParseMode.MARKDOWN
    )

async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Configure user preferences."""
    user_id = update.effective_user.id
    
    # Initialize user preferences if not exist
    if user_id not in user_preferences:
        user_preferences[user_id] = {
            "max_results": 5,
            "show_previews": True,
            "sort_by_date": True
        }
    
    # Create configuration keyboard
    keyboard = [
        [
            InlineKeyboardButton(
                f"Resultados: {user_preferences[user_id]['max_results']}",
                callback_data="config_results"
            )
        ],
        [
            InlineKeyboardButton(
                f"Previsualizaciones: {'Sí' if user_preferences[user_id]['show_previews'] else 'No'}",
                callback_data="config_previews"
            )
        ],
        [
            InlineKeyboardButton(
                f"Ordenar por: {'Fecha' if user_preferences[user_id]['sort_by_date'] else 'Relevancia'}",
                callback_data="config_sort"
            )
        ],
        [
            InlineKeyboardButton("Guardar", callback_data="config_save")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "⚙️ *Configuración* ⚙️\n\n"
        "Personaliza cómo quieres que funcione el bot:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def recent_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show recent content from the channel."""
    # Show typing action
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )
    
    # Get the latest message ID if we don't have it
    if not last_message_id:
        latest_id = await get_latest_message_id(context)
    else:
        latest_id = last_message_id
    
    # We'll get the 10 most recent messages
    start_msg_id = latest_id - 10
    if start_msg_id < 1:
        start_msg_id = 1
    
    # Create a list of message IDs to check
    message_ids = list(range(start_msg_id, latest_id + 1))
    message_ids.reverse()  # Check newest messages first
    
    # Keep track of results
    results = []
    
    # Status message
    status_message = await update.message.reply_text(
        "🔍 Buscando contenido reciente..."
    )
    
    # Search through messages
    for msg_id in message_ids[:10]:  # Limit to 10 recent messages
        try:
            # Try to get message content
            message_content = await get_message_content(context, update.effective_chat.id, msg_id)
            
            if message_content:
                # Add to results
                results.append({
                    'id': msg_id,
                    'preview': message_content.get('preview', ''),
                    'has_media': message_content.get('has_media', False)
                })
        except Exception as e:
            logger.error(f"Error getting recent content for message {msg_id}: {e}")
            continue
        
        # Small delay to avoid rate limits
        await asyncio.sleep(0.01)
    
    # Now show the results
    if results:
        # Create a message with buttons for each result
        keyboard = []
        for i, result in enumerate(results):
            media_icon = "🎬" if result['has_media'] else "📝"
            keyboard.append([
                InlineKeyboardButton(
                    f"{i+1}. {media_icon} {result['preview']}",
                    callback_data=f"send_{result['id']}"
                )
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await status_message.edit_text(
            f"✅ Contenido reciente del canal (últimos {len(results)} mensajes):\n\n"
            "Selecciona uno para verlo:",
            reply_markup=reply_markup
        )
    else:
        await status_message.edit_text(
            "❌ No se pudo obtener el contenido reciente. Intenta más tarde."
        )

async def get_latest_message_id(context: ContextTypes.DEFAULT_TYPE) -> int:
    """Get the latest message ID from the channel."""
    global last_message_id

    try:
        # Send a temporary message to get the latest message ID
        temp_msg = await context.bot.send_message(chat_id=CHANNEL_ID, text=".")
        latest_id = temp_msg.message_id
        await context.bot.delete_message(chat_id=CHANNEL_ID, message_id=latest_id)
        
        last_message_id = latest_id
        return latest_id
    except Exception as e:
        logger.error(f"Error getting latest message ID: {e}")
        return last_message_id or 1

async def get_message_content(context: ContextTypes.DEFAULT_TYPE, user_chat_id: int, msg_id: int) -> dict:
    """Get message content efficiently with caching."""
    # Check if we have this message in cache
    if msg_id in message_cache:
        return message_cache[msg_id]
    
    # Try to get message content
    try:
        # Use getMessages API method if available (faster)
        try:
            message = await context.bot.forward_message(
                chat_id=user_chat_id,
                from_chat_id=CHANNEL_ID,
                message_id=msg_id,
                disable_notification=True
            )
            
            # Extract content
            text = message.text if hasattr(message, 'text') and message.text else ""
            caption = message.caption if hasattr(message, 'caption') and message.caption else ""
            has_media = hasattr(message, 'photo') or hasattr(message, 'video') or hasattr(message, 'document')
            
            # Create preview
            full_content = (text + " " + caption).strip()
            preview = full_content[:50] + "..." if len(full_content) > 50 else full_content
            
            # Delete the forwarded message
            await context.bot.delete_message(
                chat_id=user_chat_id,
                message_id=message.message_id
            )
            
            # Create content object
            message_content = {
                'text': text,
                'caption': caption,
                'has_media': has_media,
                'preview': preview,
                'full_content': full_content
            }
            
            # Cache the content
            message_cache[msg_id] = message_content
            
            return message_content
            
        except Exception as e:
            # If forwarding fails, try copying
            try:
                message = await context.bot.copy_message(
                    chat_id=user_chat_id,
                    from_chat_id=CHANNEL_ID,
                    message_id=msg_id,
                    disable_notification=True
                )
                
                # Extract content
                text = message.text if hasattr(message, 'text') and message.text else ""
                caption = message.caption if hasattr(message, 'caption') and message.caption else ""
                has_media = hasattr(message, 'photo') or hasattr(message, 'video') or hasattr(message, 'document')
                
                # Create preview
                full_content = (text + " " + caption).strip()
                preview = full_content[:50] + "..." if len(full_content) > 50 else full_content
                
                # Delete the copied message
                await context.bot.delete_message(
                    chat_id=user_chat_id,
                    message_id=message.message_id
                )
                
                # Create content object
                message_content = {
                    'text': text,
                    'caption': caption,
                    'has_media': has_media,
                    'preview': preview,
                    'full_content': full_content
                }
                
                # Cache the content
                message_cache[msg_id] = message_content
                
                return message_content
                
            except Exception as inner_e:
                # If both methods fail, return None
                logger.error(f"Error getting content for message {msg_id}: {inner_e}")
                return None
    
    except Exception as e:
        logger.error(f"Error processing message {msg_id}: {e}")
        return None

async def search_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Search for content in the channel based on user query."""
    if not update.message:
        return
        
    query = update.message.text.lower()
    user_id = update.effective_user.id
    
    # Initialize user preferences if not exist
    if user_id not in user_preferences:
        user_preferences[user_id] = {
            "max_results": 5,
            "show_previews": True,
            "sort_by_date": True
        }
    
    # Get user preferences
    max_results = user_preferences[user_id]["max_results"]
    
    # Check if we have cached results for this query
    cache_key = f"{query}_{user_id}"
    if cache_key in search_cache:
        cache_time, results = search_cache[cache_key]
        # Check if cache is still valid
        if (datetime.now() - cache_time).total_seconds() < CACHE_EXPIRATION:
            # Use cached results
            await send_search_results(update, context, query, results)
            return
    
    # Send initial message
    status_message = await update.message.reply_text(
        f"🔍 Buscando '{query}' en el canal... Por favor espera."
    )
    
    try:
        # Show typing action
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=ChatAction.TYPING
        )
        
        # Get the latest message ID if we don't have it
        if not last_message_id:
            latest_id = await get_latest_message_id(context)
        else:
            latest_id = last_message_id
        
        # We'll search through messages more efficiently
        num_messages = min(latest_id, MAX_SEARCH_MESSAGES)
        
        # Create a list of message IDs to check
        # We'll prioritize recent messages and use a smarter search pattern
        message_ids = []
        
        # First, check the most recent 100 messages
        recent_start = max(1, latest_id - 100)
        message_ids.extend(range(latest_id, recent_start - 1, -1))
        
        # Then, check older messages with a larger step to cover more ground quickly
        if recent_start > 1:
            # Calculate how many more messages we can check
            remaining = MAX_SEARCH_MESSAGES - len(message_ids)
            if remaining > 0:
                # Determine step size based on remaining messages
                step = max(1, (recent_start - 1) // remaining)
                older_ids = list(range(recent_start - 1, 0, -step))[:remaining]
                message_ids.extend(older_ids)
        
        # Keep track of potential matches
        potential_matches = []
        
        # Update status message
        await status_message.edit_text(
            f"🔍 Buscando '{query}'... 0% completado"
        )
        
        # Parse special search filters
        movie_filter = "#película" in query or "#pelicula" in query
        series_filter = "#serie" in query or "#series" in query
        
        # Extract year filter if present
        year_match = re.search(r'\+(\d{4})', query)
        year_filter = int(year_match.group(1)) if year_match else None
        
        # Clean query from filters
        clean_query = query
        if movie_filter:
            clean_query = clean_query.replace("#película", "").replace("#pelicula", "")
        if series_filter:
            clean_query = clean_query.replace("#serie", "").replace("#series", "")
        if year_filter:
            clean_query = re.sub(r'\+\d{4}', "", clean_query)
        
        clean_query = clean_query.strip()
        
        # Search through messages in batches to update progress
        batch_size = 20
        total_batches = (len(message_ids) + batch_size - 1) // batch_size
        
        for batch_index in range(0, len(message_ids), batch_size):
            batch = message_ids[batch_index:batch_index + batch_size]
            
            # Process batch in parallel for speed
            tasks = []
            for msg_id in batch:
                task = asyncio.create_task(get_message_content(context, update.effective_chat.id, msg_id))
                tasks.append((msg_id, task))
            
            # Wait for all tasks to complete
            for msg_id, task in tasks:
                try:
                    message_content = await task
                    
                    if message_content:
                        # Check if the message contains the query
                        full_content = message_content['full_content'].lower()
                        
                        # Apply filters
                        if movie_filter and "#serie" in full_content:
                            continue
                        if series_filter and "#película" in full_content:
                            continue
                        
                        # Apply year filter
                        if year_filter and not re.search(r'\b' + str(year_filter) + r'\b', full_content):
                            continue
                        
                        # Check if message matches the query
                        if clean_query in full_content:
                            # Calculate relevance score
                            relevance = 0
                            
                            # Exact match gets higher score
                            if clean_query == full_content:
                                relevance += 100
                            # Title match gets higher score
                            elif re.search(r'^' + re.escape(clean_query), full_content):
                                relevance += 50
                            # Word boundary match gets higher score
                            elif re.search(r'\b' + re.escape(clean_query) + r'\b', full_content):
                                relevance += 25
                            # Otherwise, just a substring match
                            else:
                                relevance += 10
                                
                            # Media content gets higher score
                            if message_content['has_media']:
                                relevance += 15
                                
                            # Recent messages get higher score
                            recency_score = min(10, (msg_id / latest_id) * 10)
                            relevance += recency_score
                            
                            # Add to potential matches
                            potential_matches.append({
                                'id': msg_id,
                                'preview': message_content['preview'],
                                'has_media': message_content['has_media'],
                                'relevance': relevance
                            })
                            
                            # If we have enough matches, we can stop searching
                            if len(potential_matches) >= max_results * 3:  # Get more than needed to sort by relevance
                                break
                
                except Exception as e:
                    logger.error(f"Error processing message {msg_id}: {e}")
                    continue
            
            # Update progress
            progress = min(100, int((batch_index + len(batch)) / len(message_ids) * 100))
            if progress % 10 == 0:  # Update every 10%
                await status_message.edit_text(
                    f"🔍 Buscando '{query}'... {progress}% completado"
                )
            
            # If we have enough matches, stop searching
            if len(potential_matches) >= max_results * 3:
                break
            
            # Avoid hitting rate limits
            await asyncio.sleep(0.01)
        
        # Sort matches by relevance
        if user_preferences[user_id]["sort_by_date"]:
            # Sort by message ID (date) if user prefers
            potential_matches.sort(key=lambda x: x['id'], reverse=True)
        else:
            # Sort by relevance score
            potential_matches.sort(key=lambda x: x['relevance'], reverse=True)
        
        # Limit to max results
        potential_matches = potential_matches[:max_results]
        
        # Cache the results
        search_cache[cache_key] = (datetime.now(), potential_matches)
        
        # Send results to user
        await send_search_results(update, context, query, potential_matches, status_message)
    
    except Exception as e:
        logger.error(f"Error searching content: {e}")
        await status_message.edit_text(
            f"❌ Ocurrió un error al buscar: {str(e)[:100]}\n\nPor favor intenta más tarde."
        )

async def send_search_results(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str, results: list, status_message=None):
    """Send search results to the user."""
    if not status_message:
        status_message = await update.message.reply_text(
            f"🔍 Procesando resultados para '{query}'..."
        )
    
    if results:
        # Create a message with buttons for each match
        keyboard = []
        for i, match in enumerate(results):
            media_icon = "🎬" if match['has_media'] else "📝"
            keyboard.append([
                InlineKeyboardButton(
                    f"{i+1}. {media_icon} {match['preview']}",
                    callback_data=f"send_{match['id']}"
                )
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await status_message.edit_text(
            f"✅ Encontré {len(results)} resultados para '{query}'.\n\n"
            "Selecciona uno para verlo:",
            reply_markup=reply_markup
        )
    else:
        await status_message.edit_text(
            f"❌ No encontré resultados para '{query}'. Intenta con otro término."
        )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback queries from inline buttons."""
    query = update.callback_query
    
    if query.data.startswith("send_"):
        # Get the message ID from the callback data
        action, msg_id = query.data.split('_')
        msg_id = int(msg_id)
        
        await handle_send_callback(query, context, msg_id)
    elif query.data.startswith("config_"):
        # Handle configuration callbacks
        action = query.data.split('_')[1]
        await handle_config_callback(query, context, action)

async def handle_send_callback(query, context, msg_id):
    """Handle send content callback."""
    try:
        # Show typing action
        await context.bot.send_chat_action(
            chat_id=query.message.chat_id,
            action=ChatAction.TYPING
        )
        
        # Copy the message to the user
        await context.bot.copy_message(
            chat_id=query.message.chat_id,
            from_chat_id=CHANNEL_ID,
            message_id=msg_id,
            protect_content=True  # Prevent forwarding/saving
        )
        
        # Answer the callback query
        await query.answer("Contenido enviado")
        
        # Update the original message to show which content was selected
        # Get the current keyboard
        keyboard = query.message.reply_markup.inline_keyboard
        
        # Find the button that was clicked and mark it as selected
        new_keyboard = []
        for row in keyboard:
            new_row = []
            for button in row:
                if button.callback_data == query.data:
                    # Mark this button as selected
                    new_row.append(InlineKeyboardButton(
                        f"✅ {button.text}",
                        callback_data=button.callback_data
                    ))
                else:
                    new_row.append(button)
            new_keyboard.append(new_row)
        
        # Update the message with the new keyboard
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(new_keyboard)
        )
    
    except Exception as e:
        logger.error(f"Error handling send callback: {e}")
        await query.answer(f"Error: {str(e)[:200]}")

async def handle_config_callback(query, context, action):
    """Handle configuration callbacks."""
    user_id = query.from_user.id
    
    # Initialize user preferences if not exist
    if user_id not in user_preferences:
        user_preferences[user_id] = {
            "max_results": 5,
            "show_previews": True,
            "sort_by_date": True
        }
    
    # Handle different configuration actions
    if action == "results":
        # Cycle through result count options
        current = user_preferences[user_id]["max_results"]
        options = [5, 10, 15, 20]
        next_index = (options.index(current) + 1) % len(options) if current in options else 0
        user_preferences[user_id]["max_results"] = options[next_index]
    
    elif action == "previews":
        # Toggle previews
        user_preferences[user_id]["show_previews"] = not user_preferences[user_id]["show_previews"]
    
    elif action == "sort":
        # Toggle sort order
        user_preferences[user_id]["sort_by_date"] = not user_preferences[user_id]["sort_by_date"]
    
    elif action == "save":
        # Save configuration
        await query.answer("Configuración guardada")
        await query.edit_message_text(
            "✅ Configuración guardada correctamente.\n\n"
            f"• Resultados por búsqueda: {user_preferences[user_id]['max_results']}\n"
            f"• Mostrar previsualizaciones: {'Sí' if user_preferences[user_id]['show_previews'] else 'No'}\n"
            f"• Ordenar por: {'Fecha' if user_preferences[user_id]['sort_by_date'] else 'Relevancia'}"
        )
        return
    
    # Update configuration keyboard
    keyboard = [
        [
            InlineKeyboardButton(
                f"Resultados: {user_preferences[user_id]['max_results']}",
                callback_data="config_results"
            )
        ],
        [
            InlineKeyboardButton(
                f"Previsualizaciones: {'Sí' if user_preferences[user_id]['show_previews'] else 'No'}",
                callback_data="config_previews"
            )
        ],
        [
            InlineKeyboardButton(
                f"Ordenar por: {'Fecha' if user_preferences[user_id]['sort_by_date'] else 'Relevancia'}",
                callback_data="config_sort"
            )
        ],
        [
            InlineKeyboardButton("Guardar", callback_data="config_save")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Answer the callback query
    await query.answer("Opción actualizada")
    
    # Update the message with the new keyboard
    await query.edit_message_reply_markup(
        reply_markup=reply_markup
    )

async def init_bot(application: Application) -> None:
    """Initialize the bot."""
    logger.info("Initializing bot...")

    # Get the latest message ID
    await get_latest_message_id(application)

    logger.info(f"Bot initialized successfully! Latest message ID: {last_message_id}")

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("config", config_command))
    application.add_handler(CommandHandler("recientes", recent_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_content))
    application.add_handler(CallbackQueryHandler(handle_callback))

    # Initialize the bot
    application.job_queue.run_once(lambda context: init_bot(application), 0)

    # Run the bot until the user presses Ctrl-C
    print("Bot started!")
    application.run_polling()

if __name__ == "__main__":
    main()
