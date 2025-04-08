import logging
import asyncio
import re
import time
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode, ChatAction
from telegram.error import TelegramError
import aiohttp
import aiofiles
import concurrent.futures
from functools import lru_cache

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
TOKEN = "7551775190:AAFerA1RVjKl7L7CeD6kKZ3c5dAf9iK-ZJY"
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
MAX_SEARCH_MESSAGES = 2000

# Maximum number of results to show
MAX_RESULTS = 10

# User preferences (store user settings)
user_preferences = {}

# User search history
user_history = defaultdict(list)

# Content index for faster searching
content_index = {}

# Genre/category mapping
genre_mapping = {
    "acción": ["acción", "action", "aventura", "adventure"],
    "comedia": ["comedia", "comedy", "humor"],
    "drama": ["drama", "dramático"],
    "terror": ["terror", "horror", "miedo", "scary"],
    "ciencia ficción": ["ciencia ficción", "sci-fi", "scifi", "sci fi"],
    "fantasía": ["fantasía", "fantasy", "magia"],
    "romance": ["romance", "romántica", "love"],
    "animación": ["animación", "animation", "animated", "anime"],
    "documental": ["documental", "documentary", "docu"],
    "thriller": ["thriller", "suspense", "suspenso"],
    "crimen": ["crimen", "crime", "criminal"],
    "misterio": ["misterio", "mystery"],
    "familiar": ["familiar", "family", "niños", "kids"],
    "histórico": ["histórico", "historical", "history", "historia"],
    "bélico": ["bélico", "guerra", "war"],
    "musical": ["musical", "música", "music"],
    "western": ["western", "oeste"],
    "deportes": ["deportes", "sports", "deporte", "sport"],
    "biografía": ["biografía", "biography", "biopic"],
}

# Data file paths
DATA_DIR = "data"
INDEX_FILE = os.path.join(DATA_DIR, "content_index.json")
HISTORY_FILE = os.path.join(DATA_DIR, "user_history.json")
PREFERENCES_FILE = os.path.join(DATA_DIR, "user_preferences.json")
STATS_FILE = os.path.join(DATA_DIR, "usage_stats.json")

# Usage statistics
usage_stats = {
    "total_searches": 0,
    "popular_queries": Counter(),
    "active_users": Counter(),
    "last_updated": datetime.now().isoformat()
}

# Initialize executor for CPU-bound tasks
executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

# Initialize aiohttp session
session = None

async def initialize_session():
    """Initialize aiohttp session."""
    global session
    if session is None or session.closed:
        session = aiohttp.ClientSession()

async def close_session():
    """Close aiohttp session."""
    global session
    if session and not session.closed:
        await session.close()

async def ensure_data_dir():
    """Ensure data directory exists."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

async def load_data():
    """Load data from files."""
    global content_index, user_history, user_preferences, usage_stats
    
    await ensure_data_dir()
    
    # Load content index
    if os.path.exists(INDEX_FILE):
        try:
            async with aiofiles.open(INDEX_FILE, 'r', encoding='utf-8') as f:
                content_index = json.loads(await f.read())
        except Exception as e:
            logger.error(f"Error loading content index: {e}")
    
    # Load user history
    if os.path.exists(HISTORY_FILE):
        try:
            async with aiofiles.open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                user_history = defaultdict(list, json.loads(await f.read()))
        except Exception as e:
            logger.error(f"Error loading user history: {e}")
    
    # Load user preferences
    if os.path.exists(PREFERENCES_FILE):
        try:
            async with aiofiles.open(PREFERENCES_FILE, 'r', encoding='utf-8') as f:
                user_preferences = json.loads(await f.read())
        except Exception as e:
            logger.error(f"Error loading user preferences: {e}")
    
    # Load usage stats
    if os.path.exists(STATS_FILE):
        try:
            async with aiofiles.open(STATS_FILE, 'r', encoding='utf-8') as f:
                usage_stats = json.loads(await f.read())
                usage_stats["popular_queries"] = Counter(usage_stats["popular_queries"])
                usage_stats["active_users"] = Counter(usage_stats["active_users"])
        except Exception as e:
            logger.error(f"Error loading usage stats: {e}")

async def save_data():
    """Save data to files."""
    await ensure_data_dir()
    
    # Save content index
    try:
        async with aiofiles.open(INDEX_FILE, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(content_index))
    except Exception as e:
        logger.error(f"Error saving content index: {e}")
    
    # Save user history
    try:
        async with aiofiles.open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(user_history))
    except Exception as e:
        logger.error(f"Error saving user history: {e}")
    
    # Save user preferences
    try:
        async with aiofiles.open(PREFERENCES_FILE, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(user_preferences))
    except Exception as e:
        logger.error(f"Error saving user preferences: {e}")
    
    # Save usage stats
    try:
        usage_stats["last_updated"] = datetime.now().isoformat()
        async with aiofiles.open(STATS_FILE, 'w', encoding='utf-8') as f:
            # Convert Counter objects to dictionaries
            stats_copy = usage_stats.copy()
            stats_copy["popular_queries"] = dict(stats_copy["popular_queries"])
            stats_copy["active_users"] = dict(stats_copy["active_users"])
            await f.write(json.dumps(stats_copy))
    except Exception as e:
        logger.error(f"Error saving usage stats: {e}")

async def update_usage_stats(user_id, query):
    """Update usage statistics."""
    global usage_stats
    
    # Update total searches
    usage_stats["total_searches"] += 1
    
    # Update popular queries
    usage_stats["popular_queries"][query] += 1
    
    # Update active users
    user_id_str = str(user_id)
    usage_stats["active_users"][user_id_str] += 1
    
    # Save stats periodically (every 10 searches)
    if usage_stats["total_searches"] % 10 == 0:
        await save_data()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    await update.message.reply_text(
        "¡Hola! Soy un bot de búsqueda de películas y series. "
        "Envíame el nombre de lo que estás buscando y te enviaré los resultados directamente.\n\n"
        "Comandos disponibles:\n"
        "/start - Iniciar el bot\n"
        "/help - Mostrar ayuda\n"
        "/config - Configurar preferencias\n"
        "/recientes - Ver contenido reciente\n"
        "/historial - Ver tu historial de búsquedas\n"
        "/generos - Ver categorías disponibles\n"
        "/stats - Ver estadísticas de uso\n"
        "/notificar - Activar/desactivar notificaciones"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        "🎬 *Bot de Búsqueda de Películas y Series* 🎬\n\n"
        "*Comandos disponibles:*\n"
        "/start - Iniciar el bot\n"
        "/help - Mostrar esta ayuda\n"
        "/config - Configurar preferencias\n"
        "/recientes - Ver contenido reciente\n"
        "/historial - Ver tu historial de búsquedas\n"
        "/generos - Ver categorías disponibles\n"
        "/stats - Ver estadísticas de uso\n"
        "/notificar - Activar/desactivar notificaciones\n"
        "/limpiar - Limpiar historial de búsquedas\n\n"
        "*Búsqueda Avanzada:*\n"
        "- Simplemente envía el nombre de la película o serie\n"
        "- Usa '#película' o '#serie' para filtrar por tipo\n"
        "- Usa '+año' para buscar por año (ej: 'Avatar +2009')\n"
        "- Usa '@género' para buscar por género (ej: 'Matrix @acción')\n"
        "- Usa '!' para búsqueda exacta (ej: '!Titanic')\n"
        "- Usa '&' para combinar términos (ej: 'guerra & espacio')\n"
        "- Usa '|' para alternativas (ej: 'batman | superman')\n\n"
        "*Consejos:*\n"
        "- Sé específico en tus búsquedas\n"
        "- Los resultados se ordenan por relevancia\n"
        "- El contenido está protegido contra reenvío\n"
        "- Usa el modo de ahorro de datos si tienes conexión lenta",
        parse_mode=ParseMode.MARKDOWN
    )

async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Configure user preferences."""
    user_id = update.effective_user.id
    
    # Initialize user preferences if not exist
    if str(user_id) not in user_preferences:
        user_preferences[str(user_id)] = {
            "max_results": 5,
            "show_previews": True,
            "sort_by_date": True,
            "data_saver": False,
            "notifications": False,
            "adult_content": False,
            "language": "es"
        }
    
    # Create configuration keyboard
    keyboard = [
        [
            InlineKeyboardButton(
                f"Resultados: {user_preferences[str(user_id)]['max_results']}",
                callback_data="config_results"
            )
        ],
        [
            InlineKeyboardButton(
                f"Previsualizaciones: {'Sí' if user_preferences[str(user_id)]['show_previews'] else 'No'}",
                callback_data="config_previews"
            )
        ],
        [
            InlineKeyboardButton(
                f"Ordenar por: {'Fecha' if user_preferences[str(user_id)]['sort_by_date'] else 'Relevancia'}",
                callback_data="config_sort"
            )
        ],
        [
            InlineKeyboardButton(
                f"Ahorro de datos: {'Activado' if user_preferences[str(user_id)]['data_saver'] else 'Desactivado'}",
                callback_data="config_data_saver"
            )
        ],
        [
            InlineKeyboardButton(
                f"Notificaciones: {'Activadas' if user_preferences[str(user_id)]['notifications'] else 'Desactivadas'}",
                callback_data="config_notifications"
            )
        ],
        [
            InlineKeyboardButton(
                f"Contenido adulto: {'Permitir' if user_preferences[str(user_id)]['adult_content'] else 'Filtrar'}",
                callback_data="config_adult"
            )
        ],
        [
            InlineKeyboardButton(
                f"Idioma: {user_preferences[str(user_id)]['language'].upper()}",
                callback_data="config_language"
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
    
    # We'll get the 15 most recent messages
    start_msg_id = latest_id - 15
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
    
    # Process messages in parallel
    tasks = []
    for msg_id in message_ids[:15]:  # Limit to 15 recent messages
        task = asyncio.create_task(get_message_content(context, update.effective_chat.id, msg_id))
        tasks.append((msg_id, task))
    
    # Wait for all tasks to complete
    for msg_id, task in tasks:
        try:
            message_content = await task
            
            if message_content:
                # Add to results
                results.append({
                    'id': msg_id,
                    'preview': message_content.get('preview', ''),
                    'has_media': message_content.get('has_media', False),
                    'type': message_content.get('type', 'unknown')
                })
        except Exception as e:
            logger.error(f"Error getting recent content for message {msg_id}: {e}")
            continue
    
    # Now show the results
    if results:
        # Create a message with buttons for each result
        keyboard = []
        for i, result in enumerate(results):
            # Choose icon based on content type
            icon = "🎬"
            if result['type'] == 'photo':
                icon = "📷"
            elif result['type'] == 'video':
                icon = "🎥"
            elif result['type'] == 'document':
                icon = "📁"
            elif result['type'] == 'audio':
                icon = "🎵"
            elif not result['has_media']:
                icon = "📝"
            
            keyboard.append([
                InlineKeyboardButton(
                    f"{i+1}. {icon} {result['preview']}",
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

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user search history."""
    user_id = str(update.effective_user.id)
    
    if user_id not in user_history or not user_history[user_id]:
        await update.message.reply_text(
            "No tienes búsquedas recientes. Realiza algunas búsquedas primero."
        )
        return
    
    # Get the 10 most recent searches
    recent_searches = user_history[user_id][-10:]
    recent_searches.reverse()  # Show newest first
    
    # Create keyboard with search history
    keyboard = []
    for i, search in enumerate(recent_searches):
        keyboard.append([
            InlineKeyboardButton(
                f"{i+1}. {search['query']} ({search['date']})",
                callback_data=f"history_{i}"
            )
        ])
    
    # Add clear history button
    keyboard.append([
        InlineKeyboardButton(
            "🗑️ Limpiar historial",
            callback_data="history_clear"
        )
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📚 *Tu historial de búsquedas* 📚\n\n"
        "Selecciona una búsqueda para repetirla:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def genres_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show available genres/categories."""
    # Create keyboard with genres
    keyboard = []
    row = []
    
    for i, (genre, _) in enumerate(genre_mapping.items()):
        # Create rows with 2 genres each
        if i % 2 == 0 and i > 0:
            keyboard.append(row)
            row = []
        
        row.append(
            InlineKeyboardButton(
                genre.title(),
                callback_data=f"genre_{genre}"
            )
        )
    
    # Add the last row if not empty
    if row:
        keyboard.append(row)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎭 *Categorías y Géneros* 🎭\n\n"
        "Selecciona un género para ver contenido relacionado:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show usage statistics."""
    # Get top 5 popular queries
    popular_queries = usage_stats["popular_queries"].most_common(5)
    
    # Format statistics message
    stats_message = (
        "📊 *Estadísticas de Uso* 📊\n\n"
        f"Total de búsquedas: {usage_stats['total_searches']}\n"
        f"Usuarios activos: {len(usage_stats['active_users'])}\n\n"
        "*Búsquedas populares:*\n"
    )
    
    if popular_queries:
        for i, (query, count) in enumerate(popular_queries):
            stats_message += f"{i+1}. '{query}' - {count} búsquedas\n"
    else:
        stats_message += "No hay búsquedas populares aún.\n"
    
    # Add user's personal stats
    user_id = str(update.effective_user.id)
    user_searches = usage_stats["active_users"].get(user_id, 0)
    
    stats_message += f"\n*Tus estadísticas:*\n"
    stats_message += f"Búsquedas realizadas: {user_searches}\n"
    
    if user_id in user_history:
        stats_message += f"Historial guardado: {len(user_history[user_id])} búsquedas\n"
    
    # Add last updated timestamp
    if "last_updated" in usage_stats:
        try:
            last_updated = datetime.fromisoformat(usage_stats["last_updated"])
            stats_message += f"\nÚltima actualización: {last_updated.strftime('%d/%m/%Y %H:%M')}"
        except:
            pass
    
    await update.message.reply_text(
        stats_message,
        parse_mode=ParseMode.MARKDOWN
    )

async def notify_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle notifications for new content."""
    user_id = str(update.effective_user.id)
    
    # Initialize user preferences if not exist
    if user_id not in user_preferences:
        user_preferences[user_id] = {
            "max_results": 5,
            "show_previews": True,
            "sort_by_date": True,
            "data_saver": False,
            "notifications": False,
            "adult_content": False,
            "language": "es"
        }
    
    # Toggle notifications
    user_preferences[user_id]["notifications"] = not user_preferences[user_id]["notifications"]
    
    # Save preferences
    await save_data()
    
    if user_preferences[user_id]["notifications"]:
        await update.message.reply_text(
            "🔔 Notificaciones activadas. Recibirás alertas cuando se añada nuevo contenido relacionado con tus búsquedas recientes."
        )
    else:
        await update.message.reply_text(
            "🔕 Notificaciones desactivadas. Ya no recibirás alertas de nuevo contenido."
        )

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear user search history."""
    user_id = str(update.effective_user.id)
    
    if user_id in user_history:
        user_history[user_id] = []
        await save_data()
        
        await update.message.reply_text(
            "🗑️ Tu historial de búsquedas ha sido eliminado."
        )
    else:
        await update.message.reply_text(
            "No tienes historial de búsquedas para eliminar."
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

@lru_cache(maxsize=1000)
def extract_keywords(text):
    """Extract keywords from text for indexing."""
    # Convert to lowercase
    text = text.lower()
    
    # Remove special characters
    text = re.sub(r'[^\w\s]', ' ', text)
    
    # Split into words
    words = text.split()
    
    # Remove common stop words (Spanish)
    stop_words = {'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 'y', 'o', 'a', 'ante', 'bajo', 'con', 'de', 'desde', 'en', 'entre', 'hacia', 'hasta', 'para', 'por', 'según', 'sin', 'sobre', 'tras', 'que', 'como', 'cuando', 'donde', 'si', 'no', 'al', 'del', 'lo', 'su', 'sus', 'este', 'esta', 'estos', 'estas', 'ese', 'esa', 'esos', 'esas', 'aquel', 'aquella', 'aquellos', 'aquellas'}
    
    # Filter out stop words and words less than 3 characters
    keywords = [word for word in words if word not in stop_words and len(word) >= 3]
    
    return keywords

def calculate_relevance(query_terms, message_content, msg_id, latest_id):
    """Calculate relevance score for a message based on query terms."""
    full_content = message_content['full_content'].lower()
    
    # Base relevance score
    relevance = 0
    
    # Check each query term
    for term in query_terms:
        # Exact match gets higher score
        if term == full_content:
            relevance += 100
        # Title match gets higher score
        elif re.search(r'^' + re.escape(term), full_content):
            relevance += 50
        # Word boundary match gets higher score
        elif re.search(r'\b' + re.escape(term) + r'\b', full_content):
            relevance += 25
        # Otherwise, just a substring match
        elif term in full_content:
            relevance += 10
    
    # Media content gets higher score
    if message_content['has_media']:
        relevance += 15
    
    # Recent messages get higher score
    recency_score = min(10, (msg_id / latest_id) * 10)
    relevance += recency_score
    
    # Longer content might be more relevant (but not too much)
    length_score = min(5, len(full_content) / 200)
    relevance += length_score
    
    return relevance

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
            
            # Determine content type
            content_type = "text"
            if hasattr(message, 'photo') and message.photo:
                content_type = "photo"
                has_media = True
            elif hasattr(message, 'video') and message.video:
                content_type = "video"
                has_media = True
            elif hasattr(message, 'document') and message.document:
                content_type = "document"
                has_media = True
            elif hasattr(message, 'audio') and message.audio:
                content_type = "audio"
                has_media = True
            else:
                has_media = False
            
            # Create preview
            full_content = (text + " " + caption).strip()
            preview = full_content[:50] + "..." if len(full_content) > 50 else full_content
            
            # Delete the forwarded message
            await context.bot.delete_message(
                chat_id=user_chat_id,
                message_id=message.message_id
            )
            
            # Extract genres if possible
            genres = []
            for genre, keywords in genre_mapping.items():
                if any(keyword in full_content.lower() for keyword in keywords):
                    genres.append(genre)
            
            # Try to extract year
            year_match = re.search(r'\b(19\d{2}|20\d{2})\b', full_content)
            year = year_match.group(1) if year_match else None
            
            # Determine if it's a movie or series
            is_movie = any(keyword in full_content.lower() for keyword in ["película", "pelicula", "film", "movie"])
            is_series = any(keyword in full_content.lower() for keyword in ["serie", "series", "temporada", "season", "episodio", "episode"])
            
            content_category = "movie" if is_movie else "series" if is_series else "unknown"
            
            # Create content object
            message_content = {
                'text': text,
                'caption': caption,
                'has_media': has_media,
                'preview': preview,
                'full_content': full_content,
                'type': content_type,
                'genres': genres,
                'year': year,
                'category': content_category,
                'keywords': extract_keywords(full_content)
            }
            
            # Cache the content
            message_cache[msg_id] = message_content
            
            # Update content index
            for keyword in message_content['keywords']:
                if keyword not in content_index:
                    content_index[keyword] = []
                if msg_id not in content_index[keyword]:
                    content_index[keyword].append(msg_id)
            
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
                
                # Determine content type
                content_type = "text"
                if hasattr(message, 'photo') and message.photo:
                    content_type = "photo"
                    has_media = True
                elif hasattr(message, 'video') and message.video:
                    content_type = "video"
                    has_media = True
                elif hasattr(message, 'document') and message.document:
                    content_type = "document"
                    has_media = True
                elif hasattr(message, 'audio') and message.audio:
                    content_type = "audio"
                    has_media = True
                else:
                    has_media = False
                
                # Create preview
                full_content = (text + " " + caption).strip()
                preview = full_content[:50] + "..." if len(full_content) > 50 else full_content
                
                # Delete the copied message
                await context.bot.delete_message(
                    chat_id=user_chat_id,
                    message_id=message.message_id
                )
                
                # Extract genres if possible
                genres = []
                for genre, keywords in genre_mapping.items():
                    if any(keyword in full_content.lower() for keyword in keywords):
                        genres.append(genre)
                
                # Try to extract year
                year_match = re.search(r'\b(19\d{2}|20\d{2})\b', full_content)
                year = year_match.group(1) if year_match else None
                
                # Determine if it's a movie or series
                is_movie = any(keyword in full_content.lower() for keyword in ["película", "pelicula", "film", "movie"])
                is_series = any(keyword in full_content.lower() for keyword in ["serie", "series", "temporada", "season", "episodio", "episode"])
                
                content_category = "movie" if is_movie else "series" if is_series else "unknown"
                
                # Create content object
                message_content = {
                    'text': text,
                    'caption': caption,
                    'has_media': has_media,
                    'preview': preview,
                    'full_content': full_content,
                    'type': content_type,
                    'genres': genres,
                    'year': year,
                    'category': content_category,
                    'keywords': extract_keywords(full_content)
                }
                
                # Cache the content
                message_cache[msg_id] = message_content
                
                # Update content index
                for keyword in message_content['keywords']:
                    if keyword not in content_index:
                        content_index[keyword] = []
                    if msg_id not in content_index[keyword]:
                        content_index[keyword].append(msg_id)
                
                return message_content
                
            except Exception as inner_e:
                # If both methods fail, return None
                logger.error(f"Error getting content for message {msg_id}: {inner_e}")
                return None
    
    except Exception as e:
        logger.error(f"Error processing message {msg_id}: {e}")
        return None

async def parse_query(query):
    """Parse advanced query with operators."""
    query = query.lower()
    
    # Extract special filters
    movie_filter = "#película" in query or "#pelicula" in query
    series_filter = "#serie" in query or "#series" in query
    
    # Extract year filter if present
    year_match = re.search(r'\+(\d{4})', query)
    year_filter = int(year_match.group(1)) if year_match else None
    
    # Extract genre filter if present
    genre_match = re.search(r'@(\w+)', query)
    genre_filter = genre_match.group(1) if genre_match else None
    
    # Check for exact match
    exact_match = False
    if query.startswith('!'):
        exact_match = True
        query = query[1:]
    
    # Clean query from filters
    clean_query = query
    if movie_filter:
        clean_query = clean_query.replace("#película", "").replace("#pelicula", "")
    if series_filter:
        clean_query = clean_query.replace("#serie", "").replace("#series", "")
    if year_filter:
        clean_query = re.sub(r'\+\d{4}', "", clean_query)
    if genre_filter:
        clean_query = re.sub(r'@\w+', "", clean_query)
    
    # Handle AND operator
    and_terms = []
    if '&' in clean_query:
        and_terms = [term.strip() for term in clean_query.split('&')]
        clean_query = and_terms[0]  # Use first term as base
    
    # Handle OR operator
    or_terms = []
    if '|' in clean_query:
        or_terms = [term.strip() for term in clean_query.split('|')]
        clean_query = or_terms[0]  # Use first term as base
    
    # Final cleanup
    clean_query = clean_query.strip()
    
    return {
        'clean_query': clean_query,
        'movie_filter': movie_filter,
        'series_filter': series_filter,
        'year_filter': year_filter,
        'genre_filter': genre_filter,
        'exact_match': exact_match,
        'and_terms': and_terms,
        'or_terms': or_terms
    }

async def search_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Search for content in the channel based on user query."""
    if not update.message:
        return
        
    query = update.message.text.lower()
    user_id = str(update.effective_user.id)
    
    # Initialize user preferences if not exist
    if user_id not in user_preferences:
        user_preferences[user_id] = {
            "max_results": 5,
            "show_previews": True,
            "sort_by_date": True,
            "data_saver": False,
            "notifications": False,
            "adult_content": False,
            "language": "es"
        }
    
    # Get user preferences
    max_results = user_preferences[user_id]["max_results"]
    data_saver = user_preferences[user_id]["data_saver"]
    
    # Update usage statistics
    await update_usage_stats(user_id, query)
    
    # Add to user history
    user_history[user_id].append({
        'query': query,
        'date': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'results': 0  # Will update later
    })
    
    # Limit history size
    if len(user_history[user_id]) > 50:
        user_history[user_id] = user_history[user_id][-50:]
    
    # Check if we have cached results for this query
    cache_key = f"{query}_{user_id}"
    if cache_key in search_cache:
        cache_time, results = search_cache[cache_key]
        # Check if cache is still valid
        if (datetime.now() - cache_time).total_seconds() < CACHE_EXPIRATION:
            # Use cached results
            await send_search_results(update, context, query, results)
            # Update history with result count
            if user_history[user_id]:
                user_history[user_id][-1]['results'] = len(results)
            await save_data()
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
        
        # Parse the query
        parsed_query = await parse_query(query)
        
        # Get the latest message ID if we don't have it
        if not last_message_id:
            latest_id = await get_latest_message_id(context)
        else:
            latest_id = last_message_id
        
        # Use indexed search if possible
        potential_matches = []
        
        # Check if we have an index for any of the query terms
        query_terms = []
        
        # Add main query
        if parsed_query['clean_query']:
            query_terms.append(parsed_query['clean_query'])
        
        # Add AND terms
        if parsed_query['and_terms']:
            query_terms.extend(parsed_query['and_terms'])
        
        # Add OR terms
        if parsed_query['or_terms']:
            query_terms.extend(parsed_query['or_terms'])
        
        # Extract keywords from query terms
        all_keywords = []
        for term in query_terms:
            all_keywords.extend(extract_keywords(term))
        
        # Get unique keywords
        unique_keywords = set(all_keywords)
        
        # Check if we have any of these keywords in our index
        indexed_msg_ids = set()
        for keyword in unique_keywords:
            if keyword in content_index:
                indexed_msg_ids.update(content_index[keyword])
        
        # If we have indexed messages, use them
        if indexed_msg_ids:
            # Update status
            await status_message.edit_text(
                f"🔍 Buscando '{query}'... Usando índice de contenido."
            )
            
            # Process indexed messages in parallel
            tasks = []
            for msg_id in indexed_msg_ids:
                task = asyncio.create_task(get_message_content(context, update.effective_chat.id, msg_id))
                tasks.append((msg_id, task))
            
            # Wait for all tasks to complete
            for msg_id, task in tasks:
                try:
                    message_content = await task
                    
                    if message_content:
                        # Apply filters
                        if parsed_query['movie_filter'] and message_content['category'] != 'movie':
                            continue
                        if parsed_query['series_filter'] and message_content['category'] != 'series':
                            continue
                        if parsed_query['year_filter'] and message_content['year'] != str(parsed_query['year_filter']):
                            continue
                        if parsed_query['genre_filter'] and parsed_query['genre_filter'] not in message_content['genres']:
                            continue
                        
                        # Check for exact match if requested
                        if parsed_query['exact_match']:
                            if parsed_query['clean_query'] != message_content['full_content'].lower():
                                continue
                        
                        # Check AND terms
                        if parsed_query['and_terms']:
                            if not all(term in message_content['full_content'].lower() for term in parsed_query['and_terms']):
                                continue
                        
                        # Check OR terms
                        if parsed_query['or_terms']:
                            if not any(term in message_content['full_content'].lower() for term in parsed_query['or_terms']):
                                continue
                        
                        # Calculate relevance
                        relevance = calculate_relevance(query_terms, message_content, msg_id, latest_id)
                        
                        # Add to potential matches
                        potential_matches.append({
                            'id': msg_id,
                            'preview': message_content['preview'],
                            'has_media': message_content['has_media'],
                            'type': message_content['type'],
                            'relevance': relevance
                        })
                
                except Exception as e:
                    logger.error(f"Error processing indexed message {msg_id}: {e}")
                    continue
        
        # If we don't have enough matches from the index, do a regular search
        if len(potential_matches) < max_results:
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
            
            # Filter out messages we've already checked
            message_ids = [msg_id for msg_id in message_ids if msg_id not in indexed_msg_ids]
            
            # Update status message
            await status_message.edit_text(
                f"🔍 Buscando '{query}'... 0% completado"
            )
            
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
                            # Apply filters
                            if parsed_query['movie_filter'] and message_content['category'] != 'movie':
                                continue
                            if parsed_query['series_filter'] and message_content['category'] != 'series':
                                continue
                            if parsed_query['year_filter'] and message_content['year'] != str(parsed_query['year_filter']):
                                continue
                            if parsed_query['genre_filter'] and parsed_query['genre_filter'] not in message_content['genres']:
                                continue
                            
                            # Check for exact match if requested
                            if parsed_query['exact_match']:
                                if parsed_query['clean_query'] != message_content['full_content'].lower():
                                    continue
                            
                            # Check AND terms
                            if parsed_query['and_terms']:
                                if not all(term in message_content['full_content'].lower() for term in parsed_query['and_terms']):
                                    continue
                            
                            # Check OR terms
                            if parsed_query['or_terms']:
                                if not any(term in message_content['full_content'].lower() for term in parsed_query['or_terms']):
                                    continue
                            
                            # Check if message matches any query term
                            matches_query = False
                            for term in query_terms:
                                if term in message_content['full_content'].lower():
                                    matches_query = True
                                    break
                            
                            if matches_query:
                                # Calculate relevance
                                relevance = calculate_relevance(query_terms, message_content, msg_id, latest_id)
                                
                                # Add to potential matches
                                potential_matches.append({
                                    'id': msg_id,
                                    'preview': message_content['preview'],
                                    'has_media': message_content['has_media'],
                                    'type': message_content['type'],
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
        
        # Sort matches by relevance or date
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
        
        # Update history with result count
        if user_history[user_id]:
            user_history[user_id][-1]['results'] = len(potential_matches)
        
        # Save data
        await save_data()
        
        # Send results to user
        await send_search_results(update, context, query, potential_matches, status_message)
    
    except Exception as e:
        logger.error(f"Error searching content: {e}")
        await status_message.edit_text(
            f"❌ Ocurrió un error al buscar: {str(e)[:100]}\n\nPor favor intenta más tarde."
        )

async def send_search_results(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str, results: list, status_message=None):
    """Send search results to the user."""
    user_id = str(update.effective_user.id)
    data_saver = user_preferences.get(user_id, {}).get("data_saver", False)
    
    if not status_message:
        status_message = await update.message.reply_text(
            f"🔍 Procesando resultados para '{query}'..."
        )
    
    if results:
        # Create a message with buttons for each match
        keyboard = []
        for i, match in enumerate(results):
            # Choose icon based on content type
            icon = "🎬"
            if match.get('type') == 'photo':
                icon = "📷"
            elif match.get('type') == 'video':
                icon = "🎥"
            elif match.get('type') == 'document':
                icon = "📁"
            elif match.get('type') == 'audio':
                icon = "🎵"
            elif not match.get('has_media', False):
                icon = "📝"
            
            # Create button text
            button_text = f"{i+1}. {icon} {match['preview']}"
            
            # In data saver mode, make preview shorter
            if data_saver and len(button_text) > 30:
                button_text = f"{i+1}. {icon} {match['preview'][:27]}..."
            
            keyboard.append([
                InlineKeyboardButton(
                    button_text,
                    callback_data=f"send_{match['id']}"
                )
            ])
        
        # Add share button
        keyboard.append([
            InlineKeyboardButton(
                "📤 Compartir resultados",
                callback_data=f"share_{query}"
            )
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Create results message
        results_message = f"✅ Encontré {len(results)} resultados para '{query}'.\n\n"
        
        # Add search tips if few results
        if len(results) < 3:
            results_message += "💡 *Consejos de búsqueda:*\n"
            results_message += "- Intenta con términos más generales\n"
            results_message += "- Revisa si hay errores ortográficos\n"
            results_message += "- Prueba con sinónimos\n\n"
        
        results_message += "Selecciona uno para verlo:"
        
        await status_message.edit_text(
            results_message,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        # No results found
        keyboard = [
            [
                InlineKeyboardButton(
                    "🔄 Buscar contenido reciente",
                    callback_data="action_recent"
                )
            ],
            [
                InlineKeyboardButton(
                    "📚 Ver categorías",
                    callback_data="action_genres"
                )
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await status_message.edit_text(
            f"❌ No encontré resultados para '{query}'.\n\n"
            "💡 *Sugerencias:*\n"
            "- Intenta con términos más generales\n"
            "- Revisa si hay errores ortográficos\n"
            "- Prueba con sinónimos\n"
            "- Explora el contenido reciente o por categorías",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
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
    
    elif query.data.startswith("history_"):
        # Handle history callbacks
        action = query.data.split('_')[1]
        await handle_history_callback(query, context, action)
    
    elif query.data.startswith("genre_"):
        # Handle genre callbacks
        genre = query.data.split('_')[1]
        await handle_genre_callback(query, context, genre)
    
    elif query.data.startswith("share_"):
        # Handle share callbacks
        query_text = query.data[6:]  # Remove "share_" prefix
        await handle_share_callback(query, context, query_text)
    
    elif query.data.startswith("action_"):
        # Handle action callbacks
        action = query.data.split('_')[1]
        await handle_action_callback(query, context, action)

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
    user_id = str(query.from_user.id)
    
    # Initialize user preferences if not exist
    if user_id not in user_preferences:
        user_preferences[user_id] = {
            "max_results": 5,
            "show_previews": True,
            "sort_by_date": True,
            "data_saver": False,
            "notifications": False,
            "adult_content": False,
            "language": "es"
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
    
    elif action == "data_saver":
        # Toggle data saver mode
        user_preferences[user_id]["data_saver"] = not user_preferences[user_id]["data_saver"]
    
    elif action == "notifications":
        # Toggle notifications
        user_preferences[user_id]["notifications"] = not user_preferences[user_id]["notifications"]
    
    elif action == "adult":
        # Toggle adult content filter
        user_preferences[user_id]["adult_content"] = not user_preferences[user_id]["adult_content"]
    
    elif action == "language":
        # Cycle through language options
        current = user_preferences[user_id]["language"]
        options = ["es", "en"]
        next_index = (options.index(current) + 1) % len(options) if current in options else 0
        user_preferences[user_id]["language"] = options[next_index]
    
    elif action == "save":
        # Save configuration
        await save_data()
        await query.answer("Configuración guardada")
        await query.edit_message_text(
            "✅ Configuración guardada correctamente.\n\n"
            f"• Resultados por búsqueda: {user_preferences[user_id]['max_results']}\n"
            f"• Mostrar previsualizaciones: {'Sí' if user_preferences[user_id]['show_previews'] else 'No'}\n"
            f"• Ordenar por: {'Fecha' if user_preferences[user_id]['sort_by_date'] else 'Relevancia'}\n"
            f"• Ahorro de datos: {'Activado' if user_preferences[user_id]['data_saver'] else 'Desactivado'}\n"
            f"• Notificaciones: {'Activadas' if user_preferences[user_id]['notifications'] else 'Desactivadas'}\n"
            f"• Contenido adulto: {'Permitir' if user_preferences[user_id]['adult_content'] else 'Filtrar'}\n"
            f"• Idioma: {user_preferences[user_id]['language'].upper()}"
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
            InlineKeyboardButton(
                f"Ahorro de datos: {'Activado' if user_preferences[user_id]['data_saver'] else 'Desactivado'}",
                callback_data="config_data_saver"
            )
        ],
        [
            InlineKeyboardButton(
                f"Notificaciones: {'Activadas' if user_preferences[user_id]['notifications'] else 'Desactivadas'}",
                callback_data="config_notifications"
            )
        ],
        [
            InlineKeyboardButton(
                f"Contenido adulto: {'Permitir' if user_preferences[user_id]['adult_content'] else 'Filtrar'}",
                callback_data="config_adult"
            )
        ],
        [
            InlineKeyboardButton(
                f"Idioma: {user_preferences[user_id]['language'].upper()}",
                callback_data="config_language"
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

async def handle_history_callback(query, context, action):
    """Handle history callbacks."""
    user_id = str(query.from_user.id)
    
    if action == "clear":
        # Clear history
        if user_id in user_history:
            user_history[user_id] = []
            await save_data()
        
        await query.answer("Historial eliminado")
        await query.edit_message_text(
            "🗑️ Tu historial de búsquedas ha sido eliminado."
        )
    
    else:
        # Repeat a search from history
        try:
            index = int(action)
            if user_id in user_history and 0 <= index < len(user_history[user_id]):
                # Get the search query
                search_query = user_history[user_id][-index-1]['query']
                
                # Answer the callback query
                await query.answer(f"Repitiendo búsqueda: {search_query}")
                
                # Create a new message object to simulate user input
                message = type('obj', (object,), {
                    'chat_id': query.message.chat_id,
                    'text': search_query,
                    'reply_text': query.message.reply_text
                })
                
                # Create a new update object
                new_update = type('obj', (object,), {
                    'message': message,
                    'effective_user': type('obj', (object,), {'id': int(user_id)})
                })
                
                # Call search_content with the new update
                await search_content(new_update, context)
            else:
                await query.answer("Búsqueda no encontrada")
        except Exception as e:
            logger.error(f"Error handling history callback: {e}")
            await query.answer("Error al procesar la búsqueda")

async def handle_genre_callback(query, context, genre):
    """Handle genre callbacks."""
    # Create a search query with the genre
    search_query = f"@{genre}"
    
    # Answer the callback query
    await query.answer(f"Buscando contenido de género: {genre}")
    
    # Create a new message object to simulate user input
    message = type('obj', (object,), {
        'chat_id': query.message.chat_id,
        'text': search_query,
        'reply_text': query.message.reply_text
    })
    
    # Create a new update object
    new_update = type('obj', (object,), {
        'message': message,
        'effective_user': query.from_user
    })
    
    # Call search_content with the new update
    await search_content(new_update, context)

async def handle_share_callback(query, context, query_text):
    """Handle share results callback."""
    user_id = str(query.from_user.id)
    
    # Check if we have cached results for this query
    cache_key = f"{query_text}_{user_id}"
    if cache_key in search_cache:
        cache_time, results = search_cache[cache_key]
        
        if results:
            # Create a shareable message with results
            share_text = f"🔍 *Resultados para '{query_text}'*\n\n"
            
            for i, result in enumerate(results):
                # Choose icon based on content type
                icon = "🎬"
                if result.get('type') == 'photo':
                    icon = "📷"
                elif result.get('type') == 'video':
                    icon = "🎥"
                elif result.get('type') == 'document':
                    icon = "📁"
                elif result.get('type') == 'audio':
                    icon = "🎵"
                elif not result.get('has_media', False):
                    icon = "📝"
                
                share_text += f"{i+1}. {icon} {result['preview']}\n"
            
            share_text += f"\n💬 Compartido por @{query.from_user.username or 'usuario'} usando el Bot de Búsqueda"
            
            # Create a keyboard with a button to open the bot
            keyboard = [[
                InlineKeyboardButton(
                    "🤖 Abrir Bot de Búsqueda",
                    url=f"https://t.me/{context.bot.username}"
                )
            ]]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send the shareable message
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=share_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            
            await query.answer("Resultados compartidos")
        else:
            await query.answer("No hay resultados para compartir")
    else:
        await query.answer("No se encontraron resultados en caché")

async def handle_action_callback(query, context, action):
    """Handle action callbacks."""
    if action == "recent":
        # Create a new update object for recent command
        message = type('obj', (object,), {
            'chat_id': query.message.chat_id,
            'reply_text': query.message.reply_text
        })
        
        new_update = type('obj', (object,), {
            'message': message,
            'effective_user': query.from_user,
            'effective_chat': type('obj', (object,), {'id': query.message.chat_id})
        })
        
        # Call recent_command
        await recent_command(new_update, context)
        
    elif action == "genres":
        # Create a new update object for genres command
        message = type('obj', (object,), {
            'chat_id': query.message.chat_id,
            'reply_text': query.message.reply_text
        })
        
        new_update = type('obj', (object,), {
            'message': message,
            'effective_user': query.from_user
        })
        
        # Call genres_command
        await genres_command(new_update, context)

async def init_bot(application: Application) -> None:
    """Initialize the bot."""
    logger.info("Initializing bot...")
    
    # Initialize aiohttp session
    await initialize_session()
    
    # Load data
    await load_data()
    
    # Get the latest message ID
    await get_latest_message_id(application)
    
    # Schedule periodic data saving
    application.job_queue.run_repeating(
        lambda context: save_data(),
        interval=300,  # Every 5 minutes
        first=300
    )
    
    # Schedule cache cleanup
    application.job_queue.run_repeating(
        lambda context: cleanup_cache(),
        interval=3600,  # Every hour
        first=3600
    )
    
    logger.info(f"Bot initialized successfully! Latest message ID: {last_message_id}")

async def cleanup_cache():
    """Clean up expired cache entries."""
    global message_cache, search_cache
    
    # Current time
    now = datetime.now()
    
    # Clean up search cache
    expired_keys = []
    for key, (cache_time, _) in search_cache.items():
        if (now - cache_time).total_seconds() > CACHE_EXPIRATION:
            expired_keys.append(key)
    
    for key in expired_keys:
        del search_cache[key]
    
    # Limit message cache size
    if len(message_cache) > 5000:
        # Keep only the 3000 most recent entries
        sorted_keys = sorted(message_cache.keys(), reverse=True)
        keys_to_keep = sorted_keys[:3000]
        
        new_cache = {}
        for key in keys_to_keep:
            new_cache[key] = message_cache[key]
        
        message_cache = new_cache
    
    logger.info(f"Cache cleanup completed. Message cache: {len(message_cache)} items, Search cache: {len(search_cache)} items")

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("config", config_command))
    application.add_handler(CommandHandler("recientes", recent_command))
    application.add_handler(CommandHandler("historial", history_command))
    application.add_handler(CommandHandler("generos", genres_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("notificar", notify_command))
    application.add_handler(CommandHandler("limpiar", clear_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_content))
    application.add_handler(CallbackQueryHandler(handle_callback))

    # Initialize the bot
    application.job_queue.run_once(lambda context: init_bot(application), 0)

    # Register shutdown handler
    application.post_shutdown.append(close_session)

    # Run the bot until the user presses Ctrl-C
    print("Bot started!")
    application.run_polling()

if __name__ == "__main__":
    main()
