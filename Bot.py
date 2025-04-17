import logging
import asyncio
import re
import time
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode, ChatAction
from telegram.error import TelegramError
from database import Database
from plans import PLANS
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from flask import Flask
from threading import Thread

# Mantener el bot activo en Render
app = Flask('')

@app.route('/')
def home():
    return "¡El bot está activo!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# Constantes del bot
TOKEN = "7853962859:AAEsWR8uuqey8zh62XnFDlXmjDZzaNiO_YA"
ADMIN_ID = 1742433244
CHANNEL_ID = -1002584219284
GROUP_ID = -1002585538833
SEARCH_CHANNEL_ID = -1002302159104

# Add this at the top with other constants
PLANS_INFO = {
    'basic': {
        'name': 'Plan Básico',
        'price': 'Gratis',
        'searches_per_day': 3,
        'requests_per_day': 1,
        'can_forward': False,
        'duration_days': None  # No expiration
    },
    'pro': {
        'name': 'Plan Pro',
        'price': '169.99 CUP / 0.49 USD',
        'searches_per_day': 15,
        'requests_per_day': 2,
        'can_forward': False,
        'duration_days': 30,
        'features': ['15 búsquedas diarias', '2 pedidos diarios', 'No puede reenviar contenido ni guardarlo', 'Duración: 30 días']
    },
    'plus': {
        'name': 'Plan Plus',
        'price': '649.99 CUP / 1.99 USD',
        'searches_per_day': 50,
        'requests_per_day': 10,
        'can_forward': True,
        'duration_days': 30,
        'features': ['50 búsquedas diarias', '10 pedidos diarios', 'Soporte prioritario', 'Enlaces directos de descarga', 'Duración: 30 días']
    },
    'ultra': {
        'name': 'Plan Ultra',
        'price': '1049.99 CUP / 2.99 USD',
        'searches_per_day': float('inf'),  # Unlimited
        'requests_per_day': float('inf'),  # Unlimited
        'can_forward': True,
        'duration_days': 30,
        'features': ['Búsquedas ilimitadas', 'Pedidos ilimitados', 'Reenvío y guardado permitido', 'Enlaces directos de descarga', 'Soporte VIP', 'Duración: 30 días']
    }
}

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize database
db = Database()

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

# Lógica para el bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja el comando /start."""
    if update.message is None:
        return
        
    user = update.effective_user
    
    # Comprobar si es una solicitud de contenido específico
    if context.args and context.args[0].startswith('content_'):
        try:
            content_id = int(context.args[0].replace('content_', ''))
            user_data = db.get_user(user.id)
            can_forward = user_data and user_data.get('can_forward', False)
            
            # Mostrar acción de escribiendo mientras se procesa
            await context.bot.send_chat_action(
                chat_id=update.message.chat_id,
                action=ChatAction.TYPING
            )
            
            try:
                if can_forward:
                    # Reenviar el mensaje si está permitido
                    await context.bot.forward_message(
                        chat_id=update.message.chat_id,
                        from_chat_id=SEARCH_CHANNEL_ID,
                        message_id=content_id
                    )
                else:
                    # Copiar el mensaje con protección si no está permitido reenviar
                    await context.bot.copy_message(
                        chat_id=update.message.chat_id,
                        from_chat_id=SEARCH_CHANNEL_ID,
                        message_id=content_id,
                        protect_content=True  # Evitar reenvío/guardado
                    )
                
                # Incrementar contador de búsquedas diarias
                db.increment_daily_usage(user.id)
                
                return  # Salir de la función después de enviar el contenido
            except Exception as e:
                logger.error(f"Error al enviar contenido específico: {e}")
                await update.message.reply_text(
                    "❌ No se pudo cargar el contenido solicitado. Es posible que ya no esté disponible."
                )
                # Continuar con el flujo normal de start si falla
        except (ValueError, IndexError) as e:
            logger.error(f"Error procesando content_id: {e}")
            # Continuar con el flujo normal de start si falla
    
    # Check if this is a referral (código existente)
    if context.args and context.args[0].startswith('ref_'):
        ref_id = context.args[0].replace('ref_', '')
        try:
            ref_id = int(ref_id)
            if ref_id != user.id and db.user_exists(ref_id):
                # Add referral if not already added
                if not db.is_referred(user.id):
                    db.add_referral(ref_id, user.id)
                    await context.bot.send_message(
                        chat_id=ref_id,
                        text=f"¡Nuevo referido! {user.first_name} se ha unido usando tu enlace. Has ganado +1 💎"
                    )
        except ValueError:
            pass

    # Resto del código original de start...
    user_data = db.get_user(user.id)
    if not user_data:  # Registrar solo si el usuario no existe
        db.add_user(
            user.id,
            user.username,
            user.first_name,
            user.last_name
        )
    
    # Create main menu keyboard
    keyboard = [
        [
            InlineKeyboardButton("Multimedia Tv 📺", url=f"https://t.me/multimediatvOficial"),
            InlineKeyboardButton("Pedidos 📡", url=f"https://t.me/+X9S4pxF8c7plYjYx")
        ],
        [InlineKeyboardButton("Perfil 👤", callback_data="profile")],
        [InlineKeyboardButton("Planes 📜", callback_data="plans")],
        [InlineKeyboardButton("Información 📰", callback_data="info")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"¡Hola! {user.first_name}👋 te doy la bienvenida\n\n"
        f"MultimediaTv un bot donde encontraras un amplio catálogo de películas y series, "
        f"las cuales puedes buscar o solicitar en caso de no estar en el catálogo",
        reply_markup=reply_markup
    )

async def search_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Search for content in the channel based on user query."""
    if not update.message:
        return
        
    user_id = update.effective_user.id
    
    # Get search query from command arguments
    if not context.args:
        await update.message.reply_text(
            "Por favor, proporciona el nombre de la película o serie que deseas buscar.\n"
            "Ejemplo: /search Stranger Things"
        )
        return
    
    query = " ".join(context.args).lower()
    
    # Check user's search limits
    user_data = db.get_user(user_id)
    
    if not user_data:
        await update.message.reply_text(
            "❌ Error: Usuario no registrado. Usa /start para registrarte."
        )
        return
    
    # Check if user can make more searches today
    if not db.increment_daily_usage(user_id):
        # Show purchase plans if limit exceeded
        keyboard = []
        for plan_id, plan in PLANS_INFO.items():
            if plan_id != 'basic':
                keyboard.append([
                    InlineKeyboardButton(
                        f"{plan['name']} - {plan['price']}",
                        callback_data=f"buy_plan_{plan_id}"
                    )
                ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "❌ Has alcanzado tu límite de búsquedas diarias.\n\n"
            "Para continuar buscando, adquiere un plan premium:",
            reply_markup=reply_markup
        )
        return
    
    # Show typing action
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )
    
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
        # Get the latest message ID if we don't have it
        if not last_message_id:
            try:
                latest_id = await get_latest_message_id(context)
            except Exception as e:
                logger.error(f"Error getting latest message ID: {e}")
                await status_message.edit_text(
                    f"❌ Error al buscar en el canal. Por favor, intenta más tarde."
                )
                return
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
        if user_id in user_preferences and user_preferences[user_id]["sort_by_date"]:
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

async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle direct message searches."""
    # Verificar que update.message no sea None
    if not update.message:
        return
        
    user_id = update.effective_user.id
    query = update.message.text.lower()
    
    # Asignar el texto como argumentos para search_content
    context.args = query.split()
    await search_content(update, context)

async def get_latest_message_id(context: ContextTypes.DEFAULT_TYPE) -> int:
    """Get the latest message ID from the channel."""
    global last_message_id

    try:
        # Verificar primero si el canal existe y el bot tiene acceso
        try:
            await context.bot.get_chat(chat_id=SEARCH_CHANNEL_ID)
        except Exception as e:
            logger.error(f"Error accessing the search channel: {e}")
            raise

        # Send a temporary message to get the latest message ID
        temp_msg = await context.bot.send_message(chat_id=SEARCH_CHANNEL_ID, text=".")
        latest_id = temp_msg.message_id
        
        # Delete the temporary message
        try:
            await context.bot.delete_message(chat_id=SEARCH_CHANNEL_ID, message_id=latest_id)
        except Exception as e:
            logger.error(f"Error deleting temporary message: {e}")
        
        last_message_id = latest_id
        return latest_id
    except Exception as e:
        logger.error(f"Error getting latest message ID: {e}")
        # Return a default value instead of raising an exception
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
                from_chat_id=SEARCH_CHANNEL_ID,
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
                    from_chat_id=SEARCH_CHANNEL_ID,
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
        # Content not found, offer to make a request
        keyboard = [
            [
                InlineKeyboardButton("Película 🎞️", callback_data=f"req_movie_{query}"),
                InlineKeyboardButton("Serie 📺", callback_data=f"req_series_{query}")
            ],
            [InlineKeyboardButton("Hacer Pedido 📡", callback_data="make_request")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await status_message.edit_text(
            f"No se encontraron resultados para '{query}'.\n\n"
            f"Comprueba que escribes el nombre correctamente o utiliza variaciones del mismo. "
            f"Prueba escribiendo el nombre en el idioma oficial o español o solamente pon una palabra clave.\n"
            f"¿Quieres hacer un pedido?\n"
            f"Selecciona el tipo y haz clic en 'Hacer pedido'.",
            reply_markup=reply_markup
        )

async def handle_send_callback(query, context, msg_id):
    """Handle send content callback."""
    user_id = query.from_user.id
    user_data = db.get_user(user_id)
    can_forward = user_data and user_data.get('can_forward', False)
    
    try:
        # Show typing action
        await context.bot.send_chat_action(
            chat_id=query.message.chat_id,
            action=ChatAction.TYPING
        )
        
        try:
            if can_forward:
                # Forward the message if allowed
                await context.bot.forward_message(
                    chat_id=query.message.chat_id,
                    from_chat_id=SEARCH_CHANNEL_ID,
                    message_id=msg_id
                )
            else:
                # Copy the message to the user with protection if not allowed to forward
                await context.bot.copy_message(
                    chat_id=query.message.chat_id,
                    from_chat_id=SEARCH_CHANNEL_ID,
                    message_id=msg_id,
                    protect_content=True  # Prevent forwarding/saving
                )
            
            # Answer the callback query
            await query.answer("Contenido enviado")
            
            # Add share button for easy sharing
            share_url = f"https://t.me/MultimediaTVbot?start=content_{msg_id}"
            keyboard = [
                [InlineKeyboardButton("Compartir 🔗", url=f"https://t.me/share/url?url={share_url}&text=¡Mira%20este%20contenido%20conmigo!")]
            ]
            share_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="¿Te gustó el contenido? ¡Compártelo con tus amigos!",
                reply_markup=share_markup
            )
            
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
            logger.error(f"Error sending content: {e}")
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"❌ Error al enviar el contenido: {str(e)[:100]}\n\nEs posible que el canal de búsqueda no esté accesible o que el mensaje ya no exista."
            )
    
    except Exception as e:
        logger.error(f"Error handling send callback: {e}")
        await query.answer(f"Error: {str(e)[:200]}")

async def handle_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle profile button click with real-time limit information"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data = db.get_user(user_id)
    
    if not user_data:
        await query.edit_message_text("Error al obtener datos del perfil. Intenta con /start")
        return
    
    # Get user plan details
    plan_type = user_data.get('plan_type', 'basic')
    plan_name = PLANS_INFO.get(plan_type, PLANS_INFO['basic'])['name']
    
    # Calculate expiration date if not on basic plan
    expiration_text = ""
    if plan_type != 'basic':
        if 'plan_expiry' in user_data and user_data['plan_expiry']:
            # Verificar si plan_expiry es una cadena o un objeto datetime
            if isinstance(user_data['plan_expiry'], str):
                try:
                    expiry_date = datetime.strptime(user_data['plan_expiry'], '%Y-%m-%d %H:%M:%S')
                    # Calcular días restantes
                    days_left = (expiry_date - datetime.now()).days
                    expiration_text = f"Expira: {expiry_date.strftime('%d/%m/%Y')} ({days_left} días)\n"
                except ValueError:
                    expiration_text = f"Expira: {user_data['plan_expiry']}\n"
            else:
                days_left = (user_data['plan_expiry'] - datetime.now()).days
                expiration_text = f"Expira: {user_data['plan_expiry'].strftime('%d/%m/%Y')} ({days_left} días)\n"
    
    # Get search and request limits based on plan
    plan_info = PLANS_INFO.get(plan_type, PLANS_INFO['basic'])
    content_limit = plan_info['searches_per_day']
    request_limit = plan_info['requests_per_day']
    
    # Get current usage
    current_searches = user_data.get('daily_searches', 0)
    current_requests = user_data.get('daily_requests', 0)
    
    # Calculate remaining searches and requests
    if content_limit == float('inf'):
        searches_remaining_text = "Ilimitado"
    else:
        searches_remaining = max(0, content_limit - current_searches)
        searches_remaining_text = f"{searches_remaining}/{content_limit}"
    
    if request_limit == float('inf'):
        requests_remaining_text = "Ilimitado"
    else:
        requests_remaining = max(0, request_limit - current_requests)
        requests_remaining_text = f"{requests_remaining}/{request_limit}"
    
    # Calculate next reset time (midnight)
    now = datetime.now()
    next_reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    time_until_reset = next_reset - now
    hours, remainder = divmod(time_until_reset.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    reset_text = f"{hours:02d}:{minutes:02d}"
    
    # Get referral count
    referral_count = db.get_referral_count(user_id)
    
    # Format join date
    join_date = user_data.get('join_date', now.strftime('%Y-%m-%d %H:%M:%S'))
    if isinstance(join_date, str):
        try:
            join_date = datetime.strptime(join_date, '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y')
        except ValueError:
            join_date = now.strftime('%d/%m/%Y')
    elif isinstance(join_date, datetime):
        join_date = join_date.strftime('%d/%m/%Y')
    else:
        join_date = now.strftime('%d/%m/%Y')
    
    # Create profile message with real-time limits
    profile_text = (
        f"👤 *Perfil de Usuario*\n\n"
        f"Nombre: {query.from_user.first_name}\n"
        f"Saldo: {user_data.get('balance', 0)} 💎\n"
        f"ID: {user_id}\n"
        f"Plan: {plan_name}\n"
        f"{expiration_text}"
        f"Pedidos restantes: {requests_remaining_text}\n"
        f"Búsquedas restantes: {searches_remaining_text}\n"
        f"Fecha de Unión: {join_date}\n"
        f"Referidos: {referral_count}\n"
        f"Reinicio en: {reset_text}\n\n"
        f"🎁 Comparte tu enlace de referido y gana diamantes!"
    )
    
    # Create buttons
    keyboard = [
        [InlineKeyboardButton("Compartir Enlace de referencia 🔗", 
                             url=f"https://t.me/share/url?url=https://t.me/MultimediaTVbot?start=ref_{user_id}&text=¡Únete%20y%20ve%20películas%20conmigo!")],
        [InlineKeyboardButton("Volver 🔙", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=profile_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plans button click"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data = db.get_user(user_id)
    
    if not user_data:
        await query.edit_message_text("Error al obtener datos del usuario. Intenta con /start")
        return
    
    # Get user plan details
    plan_type = user_data.get('plan_type', 'basic')
    plan_name = PLANS_INFO.get(plan_type, PLANS_INFO['basic'])['name']
    
    # Create plans message
    plans_text = (
        f"▧ Planes de Suscripción ▧\n\n"
        f"Tu saldo actual: {user_data.get('balance', 0)} 💎\n"
        f"Plan actual: {plan_name}\n\n"
        f"📋 Planes Disponibles:\n\n"
        f"Pro (169.99 | 29 ⭐)\n"
        f"169.99 CUP\n"
        f"0.49 USD\n\n"
        f"Plus (649.99 | 117 ⭐)\n"
        f"649.99 CUP\n"
        f"1.99 USD\n\n"
        f"Ultra (1049.99 | 176 ⭐)\n"
        f"1049.99 CUP\n"
        f"2.99 USD\n\n"
        f"Pulsa los botones de debajo para mas info de los planes y formas de pago."
    )
    
    # Create buttons
    keyboard = [
        [
            InlineKeyboardButton("Plan pro ✨", callback_data="plan_pro"),
            InlineKeyboardButton("Plan plus ⭐", callback_data="plan_plus"),
            InlineKeyboardButton("Plan ultra 🌟", callback_data="plan_ultra")
        ],
        [InlineKeyboardButton("Volver 🔙", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=plans_text,
        reply_markup=reply_markup
    )

async def handle_plan_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plan details button clicks"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data = db.get_user(user_id)
    callback_data = query.data
    
    if not user_data:
        await query.edit_message_text("Error al obtener datos del usuario. Intenta con /start")
        return
    
    plan_details = ""
    if callback_data == "plan_pro":
        plan_details = (
            f"💫 Plan Pro - Detalles 💫\n\n"
            f"Precio: 169.99\n"
            f"Duración: 30 días\n\n"
            f"Beneficios:\n"
            f"└ 2 pedidos diarios\n"
            f"└ 15 películas o series al día\n"
            f"└ No puede reenviar contenido ni guardarlo\n\n"
            f"Tu saldo actual: {user_data.get('balance', 0)} 💎"
        )
    elif callback_data == "plan_plus":
        plan_details = (
            f"💫 Plan Plus - Detalles 💫\n\n"
            f"Precio: 649.99\n"
            f"Duración: 30 días\n\n"
            f"Beneficios:\n"
            f"└ 10 pedidos diarios\n"
            f"└ 50 películas o series al día\n"
            f"└ Soporte prioritario\n"
            f"└ Enlaces directos de descarga\n"
            f"└ Acceso a contenido exclusivo\n\n"
            f"Tu saldo actual: {user_data.get('balance', 0)} 💎"
        )
    elif callback_data == "plan_ultra":
        plan_details = (
            f"⭐ Plan Ultra - Detalles ⭐\n\n"
            f"Precio: 1049.99\n"
            f"Duración: 30 días\n\n"
            f"Beneficios:\n"
            f"└ Pedidos ilimitados\n"
            f"└ Sin restricciones de contenido\n"
            f"└ Reenvío y guardado permitido\n"
            f"└ Enlaces directos de descarga\n"
            f"└ Soporte VIP\n"
            f"└ Acceso anticipado a nuevo contenido\n\n"
            f"Tu saldo actual: {user_data.get('balance', 0)} 💎"
        )
    
    # Create buttons
    keyboard = [
        [
            InlineKeyboardButton("Cup (Cuba 🇨🇺)", callback_data=f"{callback_data}_cup"),
            InlineKeyboardButton("Crypto", callback_data=f"{callback_data}_crypto")
        ],
        [InlineKeyboardButton("Volver 🔙", callback_data="plans")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=plan_details,
        reply_markup=reply_markup
    )

async def handle_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment method selection"""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    plan_type, payment_method = callback_data.rsplit('_', 1)
    
    payment_info = ""
    if payment_method == "cup":
        if plan_type == "plan_pro":
            payment_info = (
                f"Pago en CUP (Transferencia)\n"
                f"Precio: 169.99 CUP\n"
                f"Pago en CUP (Saldo)\n"
                f"Precio: 189.99 CUP\n"
                f"Detalles de pago:\n"
                f"Número: 9205 1299 7736 4067\n"
                f"Telef: 55068190\n\n"
                f"⚠️ Después de realizar el pago, mandar captura del pago a @osvaldo20032 para activar tu plan."
            )
        elif plan_type == "plan_plus":
            payment_info = (
                f"Pago en CUP (Transferencia)\n"
                f"Precio: 649.99 CUP\n"
                f"Pago en CUP (Saldo)\n"
                f"Precio: 669.99 CUP\n"
                f"Detalles de pago:\n"
                f"Número: 9205 1299 7736 4067\n"
                f"Telef: 55068190\n\n"
                f"⚠️ Después de realizar el pago, mandar captura del pago a @osvaldo20032 para activar tu plan."
            )
        elif plan_type == "plan_ultra":
            payment_info = (
                f"Pago en CUP (Transferencia)\n"
                f"Precio: 1049.99 CUP\n"
                f"Pago en CUP (Saldo)\n"
                f"Precio: 1089.99 CUP\n"
                f"Detalles de pago:\n"
                f"Número: 9205 1299 7736 4067\n"
                f"Telef: 55068190\n\n"
                f"⚠️ Después de realizar el pago, mandar captura del pago a @osvaldo20032 para activar tu plan."
            )
    elif payment_method == "crypto":
        if plan_type == "plan_pro":
            payment_info = (
                f"Pago con USDT (BEP 20)\n"
                f"Precio: 0.49 USDTT\n"
                f"Detalles de pago:\n"
                f"Dirección: 0x26d89897c4e452C7BD3a0B8Aa79dD84E516BD4c6\n\n"
                f"⚠️ Después de realizar el pago, mandar captura del pago a @osvaldo20032 para activar tu plan."
            )
        elif plan_type == "plan_plus":
            payment_info = (
                f"Pago con USDT (BEP 20)\n"
                f"Precio: 1.99 USDTT\n"
                f"Detalles de pago:\n"
                f"Dirección: 0x26d89897c4e452C7BD3a0B8Aa79dD84E516BD4c6\n\n"
                f"⚠️ Después de realizar el pago, mandar captura del pago a @osvaldo20032 para activar tu plan."
            )
        elif plan_type == "plan_ultra":
            payment_info = (
                f"Pago con USDT (BEP 20)\n"
                f"Precio: 2.99 USDTT\n"
                f"Detalles de pago:\n"
                f"Dirección: 0x26d89897c4e452C7BD3a0B8Aa79dD84E516BD4c6\n\n"
                f"⚠️ Después de realizar el pago, mandar captura del pago a @osvaldo20032 para activar tu plan."
            )
    
    # Create back button
    keyboard = [
        [InlineKeyboardButton("Volver 🔙", callback_data=plan_type)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=payment_info,
        reply_markup=reply_markup
    )

async def handle_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle info button click"""
    query = update.callback_query
    await query.answer()
    
    info_text = (
        "Funcionamiento del bot:\n\n"
        "Comandos:\n"
        "/start - Inicia el bot y envía el mensaje de bienvenida con los botones principales\n"
        "/search - Seguido del nombre de la película o serie, buscará en el canal y luego enviará al usuario\n\n"
        "Si la película o serie no se encuentra en el canal, el bot te permitirá hacer un pedido.\n\n"
        "Búsquedas para usuarios sin plan premium: solo podrán realizar 3 búsquedas diarias, 1 pedido diario y no se les permitirá reenviar el video."
    )
    
    # Create back button
    keyboard = [
        [InlineKeyboardButton("Volver 🔙", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=info_text,
        reply_markup=reply_markup
    )

async def handle_request_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle request type selection"""
    query = update.callback_query
    await query.answer()
    
    # Store the request type in user_data
    context.user_data['request_type'] = query.data
    
    await query.edit_message_text(
        text="Tipo seleccionado. Ahora haz clic en 'Hacer Pedido 📡' para enviar tu solicitud.",
        reply_markup=update.callback_query.message.reply_markup
    )

async def handle_make_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle make request button click"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data = db.get_user(user_id)
    
    if not user_data:
        await query.edit_message_text("Error al obtener datos del usuario. Intenta con /start")
        return
    
    # Check if user has requests left
    requests_left = db.get_requests_left(user_id)
    if requests_left <= 0:
        await query.edit_message_text(
            "Has alcanzado el límite de pedidos diarios para tu plan.\n"
            "Considera actualizar tu plan para obtener más pedidos."
        )
        return
    
    # Get request type and content name
    callback_data = context.user_data.get('request_type', '')
    if not callback_data:
        await query.edit_message_text(
            "Por favor, selecciona primero el tipo de contenido (Película o Serie)."
        )
        return
    
    try:
        req_type, content_name = callback_data.split('_', 2)[1:]
    except ValueError:
        await query.edit_message_text(
            "Error al procesar la solicitud. Por favor, intenta nuevamente."
        )
        return
    
    # Update user's request count
    db.update_request_count(user_id)
    
    # Send request to admin
    try:
        keyboard = [
            [InlineKeyboardButton("Aceptar ✅", callback_data=f"accept_req_{user_id}_{content_name}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📩 *Nuevo Pedido*\n\n"
                 f"Usuario: {query.from_user.first_name} (@{query.from_user.username})\n"
                 f"ID: {user_id}\n"
                 f"Tipo: {'Película' if req_type == 'movie' else 'Serie'}\n"
                 f"Nombre: {content_name}",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Confirm to user
        await query.edit_message_text(
            f"✅ Tu pedido de {'película' if req_type == 'movie' else 'serie'} '{content_name}' ha sido enviado al administrador.\n"
            f"Te notificaremos cuando esté disponible.\n"
            f"Te quedan {requests_left-1} pedidos hoy."
        )
    except Exception as e:
        logger.error(f"Error sending request to admin: {e}")
        await query.edit_message_text(
            "Error al enviar el pedido. Intenta más tarde."
        )

async def handle_accept_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin accepting a content request"""
    query = update.callback_query
    await query.answer()
    
    # Check if user is admin
    if query.from_user.id != ADMIN_ID:
        return
    
    # Parse callback data
    try:
        _, req_type, user_id, content_name = query.data.split('_', 3)
        user_id = int(user_id)
        
        # Notify user that request was accepted
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ ¡Buenas noticias! Tu solicitud para '{content_name}' ha sido aceptada.\n"
                 f"El contenido estará disponible pronto en el bot. Podrás buscarlo usando /search."
        )
        
        # Update admin's message
        await query.edit_message_text(
            text=f"✅ Pedido aceptado: {content_name}\n"
                 f"El usuario ha sido notificado.",
            reply_markup=None
        )
    except Exception as e:
        logger.error(f"Error handling accept request: {e}")
        await query.edit_message_text(
            text="Error al procesar la aceptación del pedido.",
            reply_markup=None
        )

async def set_user_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to set a user's plan"""
    user = update.effective_user
    
    # Check if user is admin
    if user.id != ADMIN_ID:
        return
    
    # Check arguments
    if len(context.args) < 2:
        await update.message.reply_text(
            "Uso: /plan @username número_de_plan\n"
            "1 - Plan Pro\n"
            "2 - Plan Plus\n"
            "3 - Plan Ultra"
        )
        return
    
    username = context.args[0].replace('@', '')
    try:
        plan_number = int(context.args[1])
        if plan_number not in [1, 2, 3]:
            raise ValueError("Número de plan inválido")
        
        plan_map = {1: 'pro', 2: 'plus', 3: 'ultra'}
        plan_type = plan_map[plan_number]
        
        # Get user_id from username
        user_id = db.get_user_id_by_username(username)
        if not user_id:
            await update.message.reply_text(f"Usuario @{username} no encontrado en la base de datos.")
            return
        
        # Update user's plan
        expiry_date = datetime.now() + timedelta(days=30)
        db.update_plan(user_id, plan_type, expiry_date)
        
        # Notify user about plan change
        plan_name = PLANS_INFO[plan_type]['name']
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎉 ¡Felicidades! Tu plan ha sido actualizado a {plan_name}.\n"
                     f"Expira el: {expiry_date.strftime('%d/%m/%Y')}\n"
                     f"Disfruta de todos los beneficios de tu nuevo plan."
            )
        except Exception as e:
            logger.error(f"Error notifying user about plan change: {e}")
        
        await update.message.reply_text(
            f"Plan de @{username} actualizado a {plan_name}.\n"
            f"Expira el: {expiry_date.strftime('%d/%m/%Y')}"
        )
    except ValueError:
        await update.message.reply_text(
            "Número de plan inválido. Debe ser 1, 2 o 3."
        )
    except Exception as e:
        logger.error(f"Error setting user plan: {e}")
        await update.message.reply_text(
            "Error al actualizar el plan del usuario."
        )

async def add_gift_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to create a gift code"""
    user = update.effective_user
    
    # Check if user is admin
    if user.id != ADMIN_ID:
        return
    
    # Check arguments
    if len(context.args) < 3:
        await update.message.reply_text(
            "Uso: /addgift_code código plan_number max_uses\n"
            "Ejemplo: /addgift_code 2432 3 1\n"
            "1 - Plan Pro\n"
            "2 - Plan Plus\n"
            "3 - Plan Ultra"
        )
        return
    
    try:
        code = context.args[0]
        plan_number = int(context.args[1])
        max_uses = int(context.args[2])
        
        if plan_number not in [1, 2, 3]:
            raise ValueError("Número de plan inválido")
        
        plan_map = {1: 'pro', 2: 'plus', 3: 'ultra'}
        plan_type = plan_map[plan_number]
        
        # Add gift code to database
        db.add_gift_code(code, plan_type, max_uses)
        
        await update.message.reply_text(
            f"Código de regalo '{code}' creado para el plan {PLANS_INFO[plan_type]['name']}.\n"
            f"Usos máximos: {max_uses}"
        )
    except ValueError:
        await update.message.reply_text(
            "Formato inválido. Usa /addgift_code código plan_number max_uses"
        )
    except Exception as e:
        logger.error(f"Error adding gift code: {e}")
        await update.message.reply_text(
            "Error al crear el código de regalo."
        )

async def redeem_gift_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to redeem a gift code"""
    user_id = update.effective_user.id
    
    # Check arguments
    if not context.args:
        await update.message.reply_text(
            "Uso: /gift_code código\n"
            "Ejemplo: /gift_code 2432"
        )
        return
    
    code = context.args[0]
    
    try:
        # Check if code exists and is valid
        gift_code_data = db.get_gift_code(code)
        if not gift_code_data:
            await update.message.reply_text(
                "Código de regalo inválido o ya ha sido utilizado."
            )
            return
        
        # Update user's plan
        plan_type = gift_code_data['plan_type']
        expiry_date = datetime.now() + timedelta(days=30)
        db.update_plan(user_id, plan_type, expiry_date)
        
        # Update gift code usage
        db.update_gift_code_usage(code)
        
        # Notify user
        plan_name = PLANS_INFO[plan_type]['name']
        await update.message.reply_text(
            f"🎉 ¡Felicidades! Has canjeado un código de regalo.\n"
            f"Tu plan ha sido actualizado a {plan_name}.\n"
            f"Expira el: {expiry_date.strftime('%d/%m/%Y')}\n"
            f"Disfruta de todos los beneficios de tu nuevo plan."
        )
    except Exception as e:
        logger.error(f"Error redeeming gift code: {e}")
        await update.message.reply_text(
            "Error al canjear el código de regalo. Intenta más tarde."
        )

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to ban a user"""
    user = update.effective_user
    
    # Check if user is admin
    if user.id != ADMIN_ID:
        return
    
    # Check arguments
    if not context.args:
        await update.message.reply_text(
            "Uso: /ban @username o /ban user_id"
        )
        return
    
    target = context.args[0]
    
    try:
        # Check if target is username or user_id
        if target.startswith('@'):
            username = target.replace('@', '')
            user_id = db.get_user_id_by_username(username)
            if not user_id:
                await update.message.reply_text(f"Usuario {target} no encontrado.")
                return
        else:
            try:
                user_id = int(target)
                if not db.user_exists(user_id):
                    await update.message.reply_text(f"Usuario con ID {user_id} no encontrado.")
                    return
            except ValueError:
                await update.message.reply_text("Formato inválido. Usa /ban @username o /ban user_id")
                return
        
        # Ban user
        db.ban_user(user_id)
        
        # Notify user
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="⛔ Has sido baneado del bot MultimediaTv. Si crees que es un error, contacta al administrador."
            )
        except Exception as e:
            logger.error(f"Error notifying banned user: {e}")
        
        await update.message.reply_text(f"Usuario con ID {user_id} ha sido baneado.")
    except Exception as e:
        logger.error(f"Error banning user: {e}")
        await update.message.reply_text(
            "Error al banear al usuario."
        )

async def upload_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to upload content to the search channel"""
    user = update.effective_user
    
    # Check if user is admin
    if user.id != ADMIN_ID:
        return
    
    # Check if message is a reply to a media message
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "Este comando debe ser usado respondiendo a un mensaje que contenga "
            "la película, serie o imagen con su descripción."
        )
        return
    
    original_message = update.message.reply_to_message
    
    try:
        # Verificar acceso al canal de búsqueda
        try:
            await context.bot.get_chat(chat_id=SEARCH_CHANNEL_ID)
        except Exception as e:
            await update.message.reply_text(
                f"Error al acceder al canal de búsqueda. Verifica que el bot sea administrador del canal.\nError: {str(e)}"
            )
            return
            
        # Forward content to search channel
        forwarded_msg = await context.bot.copy_message(
            chat_id=SEARCH_CHANNEL_ID,
            from_chat_id=update.effective_chat.id,
            message_id=original_message.message_id
        )
        
        # Generate unique content ID
        content_id = forwarded_msg.message_id
        
        # Create share button
        share_url = f"https://t.me/MultimediaTVbot?start=content_{content_id}"
        keyboard = [
            [InlineKeyboardButton("Ver", url=share_url)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Update message in channel with share button if possible
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=SEARCH_CHANNEL_ID,
                message_id=content_id,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error adding share button to content: {e}")
        
        await update.message.reply_text(
            f"✅ Contenido subido correctamente al canal con ID #{content_id}"
        )
    except Exception as e:
        logger.error(f"Error uploading content: {e}")
        await update.message.reply_text(
            f"Error al subir el contenido: {str(e)}\nIntenta más tarde."
        )

async def request_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to request a specific movie or series"""
    user_id = update.effective_user.id
    
    # Check arguments
    if len(context.args) < 2:
        await update.message.reply_text(
            "Uso: /pedido año nombre_del_contenido\n"
            "Ejemplo: /pedido 2023 Oppenheimer"
        )
        return
    
    # Check if user is banned
    if db.is_user_banned(user_id):
        await update.message.reply_text(
            "No puedes realizar pedidos porque has sido baneado del bot."
        )
        return
    
    # Check if user has requests left
    requests_left = db.get_requests_left(user_id)
    if requests_left <= 0:
        await update.message.reply_text(
            "Has alcanzado el límite de pedidos diarios para tu plan.\n"
            "Considera actualizar tu plan para obtener más pedidos."
        )
        return
    
    year = context.args[0]
    content_name = " ".join(context.args[1:])
    
    # Update user's request count
    db.update_request_count(user_id)
    
    # Send request to admin
    try:
        keyboard = [
            [InlineKeyboardButton("Aceptar ✅", callback_data=f"accept_req_{user_id}_{content_name}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📩 *Nuevo Pedido*\n\n"
                 f"Usuario: {update.effective_user.first_name} (@{update.effective_user.username})\n"
                 f"ID: {user_id}\n"
                 f"Año: {year}\n"
                 f"Nombre: {content_name}",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Confirm to user
        await update.message.reply_text(
            f"✅ Tu pedido '{content_name}' ({year}) ha sido enviado al administrador.\n"
            f"Te notificaremos cuando esté disponible.\n"
            f"Te quedan {requests_left-1} pedidos hoy."
        )
    except Exception as e:
        logger.error(f"Error sending request to admin: {e}")
        await update.message.reply_text(
            "Error al enviar el pedido. Intenta más tarde."
        )

async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to show all available commands"""
    user = update.effective_user
    
    # Check if user is admin
    if user.id != ADMIN_ID:
        return
    
    help_text = (
        "📋 Comandos de Administrador 📋\n\n"
        "Gestión de Usuarios:\n"
        "/plan @username número_plan - Asigna un plan a un usuario\n"
        "   1 - Plan Pro\n"
        "   2 - Plan Plus\n"
        "   3 - Plan Ultra\n\n"
        "/ban @username - Banea a un usuario\n\n"
        "Gestión de Contenido:\n"
        "/up - Responde a un mensaje con este comando para subirlo al canal\n\n"
        "Códigos de Regalo:\n"
        "/addgift_code código plan_number max_uses - Crea un código de regalo\n"
        "   Ejemplo: /addgift_code 2432 3 1\n\n"
        "Estadísticas:\n"
        "/stats - Muestra estadísticas del bot\n\n"
        "Comunicación:\n"
        "/broadcast mensaje - Envía un mensaje a todos los usuarios"
    )
    
    await update.message.reply_text(text=help_text)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to show bot statistics"""
    user = update.effective_user
    
    # Check if user is admin
    if user.id != ADMIN_ID:
        return
    
    try:
        total_users = db.get_total_users()
        active_users = db.get_active_users()
        premium_users = db.get_premium_users()
        total_searches = db.get_total_searches()
        total_requests = db.get_total_requests()
        
        stats_text = (
            "📊 Estadísticas del Bot 📊\n\n"
            f"👥 Usuarios:\n"
            f"- Total: {total_users}\n"
            f"- Activos (últimos 7 días): {active_users}\n"
            f"- Con plan premium: {premium_users}\n\n"
            f"🔍 Actividad:\n"
            f"- Búsquedas totales: {total_searches}\n"
            f"- Pedidos totales: {total_requests}\n\n"
            f"📈 Distribución de Planes:\n"
            f"- Básico: {db.get_users_by_plan('basic')}\n"
            f"- Pro: {db.get_users_by_plan('pro')}\n"
            f"- Plus: {db.get_users_by_plan('plus')}\n"
            f"- Ultra: {db.get_users_by_plan('ultra')}"
        )
        
        await update.message.reply_text(text=stats_text)
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        await update.message.reply_text(
            "Error al obtener estadísticas."
        )

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to broadcast a message to all users"""
    user = update.effective_user
    
    # Check if user is admin
    if user.id != ADMIN_ID:
        return
    
    # Check arguments
    if not context.args:
        await update.message.reply_text(
            "Uso: /broadcast mensaje"
        )
        return
    
    message = " ".join(context.args)
    
    # Get all user IDs
    user_ids = db.get_all_user_ids()
    
    sent_count = 0
    failed_count = 0
    
    await update.message.reply_text(
        f"Iniciando difusión a {len(user_ids)} usuarios..."
    )
    
    for user_id in user_ids:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📢 *Anuncio Oficial*\n\n{message}",
                parse_mode=ParseMode.MARKDOWN
            )
            sent_count += 1
            
            # Add a small delay to avoid hitting rate limits
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"Error sending broadcast to {user_id}: {e}")
            failed_count += 1
    
    await update.message.reply_text(
        f"Difusión completada:\n"
        f"✅ Enviados: {sent_count}\n"
        f"❌ Fallidos: {failed_count}"
    )

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries from inline buttons"""
    query = update.callback_query
    data = query.data
    
    # Route to appropriate handler based on callback data
    if data == "profile":
        await handle_profile(update, context)
    elif data == "plans":
        await handle_plans(update, context)
    elif data == "info":
        await handle_info(update, context)
    elif data == "main_menu":
        # Recrear el mensaje de menú principal sin usar start
        user = query.from_user
        keyboard = [
            [
                InlineKeyboardButton("Multimedia Tv 📺", url=f"https://t.me/multimediatvOficial"),
                InlineKeyboardButton("Pedidos 📡", url=f"https://t.me/+X9S4pxF8c7plYjYx")
            ],
            [InlineKeyboardButton("Perfil 👤", callback_data="profile")],
            [InlineKeyboardButton("Planes 📜", callback_data="plans")],
            [InlineKeyboardButton("Información 📰", callback_data="info")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await query.edit_message_text(
                f"¡Hola! {user.first_name}👋 te doy la bienvenida\n\n"
                f"MultimediaTv un bot donde encontraras un amplio catálogo de películas y series, "
                f"las cuales puedes buscar o solicitar en caso de no estar en el catálogo",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error returning to main menu: {e}")
            # Si falla el edit_message, intentamos enviar un nuevo mensaje
            try:
                await context.bot.send_message(
                    chat_id=query.message.chat.id,
                    text=f"¡Hola! {user.first_name}👋 te doy la bienvenida\n\n"
                         f"MultimediaTv un bot donde encontraras un amplio catálogo de películas y series, "
                         f"las cuales puedes buscar o solicitar en caso de no estar en el catálogo",
                    reply_markup=reply_markup
                )
            except Exception as inner_e:
                logger.error(f"Error sending new main menu message: {inner_e}")
                await query.answer("Error al mostrar el menú principal. Intenta con /start")
                
    elif data in ["plan_pro", "plan_plus", "plan_ultra"]:
        await handle_plan_details(update, context)
    elif "_cup" in data or "_crypto" in data:
        await handle_payment_method(update, context)
    elif data.startswith("req_"):
        await handle_request_type(update, context)
    elif data == "make_request":
        await handle_make_request(update, context)
    elif data.startswith("accept_req_"):
        await handle_accept_request(update, context)
    elif data.startswith("send_"):
        # Get the message ID from the callback data
        try:
            msg_id = int(data.split("_")[1])
            await handle_send_callback(query, context, msg_id)
        except (ValueError, IndexError) as e:
            logger.error(f"Error parsing send callback data: {e}")
            await query.answer("Error: formato de datos inválido")
    else:
        await query.answer("Opción no disponible.")

async def check_plan_expiry(context: ContextTypes.DEFAULT_TYPE):
    """Background task to check for expired plans"""
    try:
        # Get users with expired plans
        expired_users = db.get_expired_plans()
        
        for user_id in expired_users:
            # Reset user to basic plan
            db.update_plan(user_id, 'basic', None)
            
            # Notify user
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="⚠️ Tu plan premium ha expirado. Has sido cambiado al plan básico.\n"
                         "Para renovar tu plan, utiliza el botón 'Planes 📜' en el menú principal."
                )
            except Exception as e:
                logger.error(f"Error notifying user {user_id} about plan expiry: {e}")
    except Exception as e:
        logger.error(f"Error in plan expiry check: {e}")

async def reset_daily_limits(context: ContextTypes.DEFAULT_TYPE):
    """Background task to reset daily limits at midnight"""
    try:
        # Reset daily limits
        db.reset_daily_limits()
        logger.info("Daily limits reset")
    except Exception as e:
        logger.error(f"Error in daily limits reset: {e}")

async def error_handler(update, context):
    """Handle errors in the dispatcher"""
    logger.error(f"Exception while handling an update: {context.error}")

    # Log the error before we do anything else
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

    # Send a message to the user
    if update and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text="Ocurrió un error al procesar tu solicitud. Por favor, intenta nuevamente."
            )
        except Exception as e:
            logger.error(f"Error sending error message: {e}")
    
async def upload_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to upload content to the search channel"""
    user = update.effective_user
    
    # Check if user is admin
    if user.id != ADMIN_ID:
        return
    
    # Check if message is a reply to a media message
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "Este comando debe ser usado respondiendo a un mensaje que contenga "
            "la película, serie o imagen con su descripción."
        )
        return
    
    original_message = update.message.reply_to_message
    
    try:
        # Verificar acceso al canal de búsqueda
        try:
            await context.bot.get_chat(chat_id=SEARCH_CHANNEL_ID)
        except Exception as e:
            await update.message.reply_text(
                f"Error al acceder al canal de búsqueda. Verifica que el bot sea administrador del canal.\nError: {str(e)}"
            )
            return
            
        # Forward content to search channel
        forwarded_msg = await context.bot.copy_message(
            chat_id=SEARCH_CHANNEL_ID,
            from_chat_id=update.effective_chat.id,
            message_id=original_message.message_id
        )
        
        # Generate unique content ID
        content_id = forwarded_msg.message_id
        
        # Create share button
        share_url = f"https://t.me/MultimediaTVbot?start=content_{content_id}"
        keyboard = [
            [InlineKeyboardButton("Ver", url=share_url)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Update message in channel with share button if possible
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=SEARCH_CHANNEL_ID,
                message_id=content_id,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error adding share button to content: {e}")
        
        await update.message.reply_text(
            f"✅ Contenido subido correctamente al canal con ID #{content_id}"
        )
    except Exception as e:
        logger.error(f"Error uploading content: {e}")
        await update.message.reply_text(
            f"Error al subir el contenido: {str(e)}\nIntenta más tarde."
        )

async def request_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to request a specific movie or series"""
    user_id = update.effective_user.id
    
    # Check arguments
    if len(context.args) < 2:
        await update.message.reply_text(
            "Uso: /pedido año nombre_del_contenido\n"
            "Ejemplo: /pedido 2023 Oppenheimer"
        )
        return
    
    # Check if user is banned
    if db.is_user_banned(user_id):
        await update.message.reply_text(
            "No puedes realizar pedidos porque has sido baneado del bot."
        )
        return
    
    # Check if user has requests left
    requests_left = db.get_requests_left(user_id)
    if requests_left <= 0:
        await update.message.reply_text(
            "Has alcanzado el límite de pedidos diarios para tu plan.\n"
            "Considera actualizar tu plan para obtener más pedidos."
        )
        return
    
    year = context.args[0]
    content_name = " ".join(context.args[1:])
    
    # Update user's request count
    db.update_request_count(user_id)
    
    # Send request to admin
    try:
        keyboard = [
            [InlineKeyboardButton("Aceptar ✅", callback_data=f"accept_req_{user_id}_{content_name}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📩 *Nuevo Pedido*\n\n"
                 f"Usuario: {update.effective_user.first_name} (@{update.effective_user.username})\n"
                 f"ID: {user_id}\n"
                 f"Año: {year}\n"
                 f"Nombre: {content_name}",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Confirm to user
        await update.message.reply_text(
            f"✅ Tu pedido '{content_name}' ({year}) ha sido enviado al administrador.\n"
            f"Te notificaremos cuando esté disponible.\n"
            f"Te quedan {requests_left-1} pedidos hoy."
        )
    except Exception as e:
        logger.error(f"Error sending request to admin: {e}")
        await update.message.reply_text(
            "Error al enviar el pedido. Intenta más tarde."
        )

async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to show all available commands"""
    user = update.effective_user
    
    # Check if user is admin
    if user.id != ADMIN_ID:
        return
    
    help_text = (
        "📋 Comandos de Administrador 📋\n\n"
        "Gestión de Usuarios:\n"
        "/plan @username número_plan - Asigna un plan a un usuario\n"
        "   1 - Plan Pro\n"
        "   2 - Plan Plus\n"
        "   3 - Plan Ultra\n\n"
        "/ban @username - Banea a un usuario\n\n"
        "Gestión de Contenido:\n"
        "/up - Responde a un mensaje con este comando para subirlo al canal\n\n"
        "Códigos de Regalo:\n"
        "/addgift_code código plan_number max_uses - Crea un código de regalo\n"
        "   Ejemplo: /addgift_code 2432 3 1\n\n"
        "Estadísticas:\n"
        "/stats - Muestra estadísticas del bot\n\n"
        "Comunicación:\n"
        "/broadcast mensaje - Envía un mensaje a todos los usuarios"
    )
    
    await update.message.reply_text(text=help_text)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to show bot statistics"""
    user = update.effective_user
    
    # Check if user is admin
    if user.id != ADMIN_ID:
        return
    
    try:
        total_users = db.get_total_users()
        active_users = db.get_active_users()
        premium_users = db.get_premium_users()
        total_searches = db.get_total_searches()
        total_requests = db.get_total_requests()
        
        stats_text = (
            "📊 Estadísticas del Bot 📊\n\n"
            f"👥 Usuarios:\n"
            f"- Total: {total_users}\n"
            f"- Activos (últimos 7 días): {active_users}\n"
            f"- Con plan premium: {premium_users}\n\n"
            f"🔍 Actividad:\n"
            f"- Búsquedas totales: {total_searches}\n"
            f"- Pedidos totales: {total_requests}\n\n"
            f"📈 Distribución de Planes:\n"
            f"- Básico: {db.get_users_by_plan('basic')}\n"
            f"- Pro: {db.get_users_by_plan('pro')}\n"
            f"- Plus: {db.get_users_by_plan('plus')}\n"
            f"- Ultra: {db.get_users_by_plan('ultra')}"
        )
        
        await update.message.reply_text(text=stats_text)
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        await update.message.reply_text(
            "Error al obtener estadísticas."
        )

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to broadcast a message to all users"""
    user = update.effective_user
    
    # Check if user is admin
    if user.id != ADMIN_ID:
        return
    
    # Check arguments
    if not context.args:
        await update.message.reply_text(
            "Uso: /broadcast mensaje"
        )
        return
    
    message = " ".join(context.args)
    
    # Get all user IDs
    user_ids = db.get_all_user_ids()
    
    sent_count = 0
    failed_count = 0
    
    await update.message.reply_text(
        f"Iniciando difusión a {len(user_ids)} usuarios..."
    )
    
    for user_id in user_ids:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📢 *Anuncio Oficial*\n\n{message}",
                parse_mode=ParseMode.MARKDOWN
            )
            sent_count += 1
            
            # Add a small delay to avoid hitting rate limits
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"Error sending broadcast to {user_id}: {e}")
            failed_count += 1
    
    await update.message.reply_text(
        f"Difusión completada:\n"
        f"✅ Enviados: {sent_count}\n"
        f"❌ Fallidos: {failed_count}"
    )

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries from inline buttons"""
    query = update.callback_query
    data = query.data
    
    # Route to appropriate handler based on callback data
    if data == "profile":
        await handle_profile(update, context)
    elif data == "plans":
        await handle_plans(update, context)
    elif data == "info":
        await handle_info(update, context)
    elif data == "main_menu":
        # Recrear el mensaje de menú principal sin usar start
        user = query.from_user
        keyboard = [
            [
                InlineKeyboardButton("Multimedia Tv 📺", url=f"https://t.me/multimediatvOficial"),
                InlineKeyboardButton("Pedidos 📡", url=f"https://t.me/+X9S4pxF8c7plYjYx")
            ],
            [InlineKeyboardButton("Perfil 👤", callback_data="profile")],
            [InlineKeyboardButton("Planes 📜", callback_data="plans")],
            [InlineKeyboardButton("Información 📰", callback_data="info")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await query.edit_message_text(
                f"¡Hola! {user.first_name}👋 te doy la bienvenida\n\n"
                f"MultimediaTv un bot donde encontraras un amplio catálogo de películas y series, "
                f"las cuales puedes buscar o solicitar en caso de no estar en el catálogo",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error returning to main menu: {e}")
            # Si falla el edit_message, intentamos enviar un nuevo mensaje
            try:
                await context.bot.send_message(
                    chat_id=query.message.chat.id,
                    text=f"¡Hola! {user.first_name}👋 te doy la bienvenida\n\n"
                         f"MultimediaTv un bot donde encontraras un amplio catálogo de películas y series, "
                         f"las cuales puedes buscar o solicitar en caso de no estar en el catálogo",
                    reply_markup=reply_markup
                )
            except Exception as inner_e:
                logger.error(f"Error sending new main menu message: {inner_e}")
                await query.answer("Error al mostrar el menú principal. Intenta con /start")
                
    elif data in ["plan_pro", "plan_plus", "plan_ultra"]:
        await handle_plan_details(update, context)
    elif "_cup" in data or "_crypto" in data:
        await handle_payment_method(update, context)
    elif data.startswith("req_"):
        await handle_request_type(update, context)
    elif data == "make_request":
        await handle_make_request(update, context)
    elif data.startswith("accept_req_"):
        await handle_accept_request(update, context)
    elif data.startswith("send_"):
        # Get the message ID from the callback data
        try:
            msg_id = int(data.split("_")[1])
            await handle_send_callback(query, context, msg_id)
        except (ValueError, IndexError) as e:
            logger.error(f"Error parsing send callback data: {e}")
            await query.answer("Error: formato de datos inválido")
    else:
        await query.answer("Opción no disponible.")

async def check_plan_expiry(context):
    """Background task to check for expired plans"""
    try:
        # Get users with expired plans
        expired_users = db.get_expired_plans()
        
        for user_id in expired_users:
            # Reset user to basic plan
            db.update_plan(user_id, 'basic', None)
            
            # Notify user
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="⚠️ Tu plan premium ha expirado. Has sido cambiado al plan básico.\n"
                         "Para renovar tu plan, utiliza el botón 'Planes 📜' en el menú principal."
                )
            except Exception as e:
                logger.error(f"Error notifying user {user_id} about plan expiry: {e}")
    except Exception as e:
        logger.error(f"Error in plan expiry check: {e}")

async def reset_daily_limits(context):
    """Background task to reset daily limits at midnight"""
    try:
        # Reset daily limits
        db.reset_daily_limits()
        logger.info("Daily limits reset")
    except Exception as e:
        logger.error(f"Error in daily limits reset: {e}")

async def reset_daily_limits(context: ContextTypes.DEFAULT_TYPE):
    """Background task to reset daily limits at midnight"""
    try:
        # Reset daily limits
        db.reset_daily_limits()
        logger.info("Daily limits reset")
    except Exception as e:
        logger.error(f"Error in daily limits reset: {e}")

async def error_handler(update, context):
    """Handle errors in the dispatcher"""
    logger.error(f"Exception while handling an update: {context.error}")

    # Log the error before we do anything else
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

    # Send a message to the user
    if update and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text="Ocurrió un error al procesar tu solicitud. Por favor, intenta nuevamente."
            )
        except Exception as e:
            logger.error(f"Error sending error message: {e}")

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(TOKEN).build()

    # Register error handler
    application.add_error_handler(error_handler)

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("search", search_content))
    application.add_handler(CommandHandler("plan", set_user_plan))
    application.add_handler(CommandHandler("addgift_code", add_gift_code))
    application.add_handler(CommandHandler("gift_code", redeem_gift_code))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("up", upload_content))
    application.add_handler(CommandHandler("pedido", request_content))
    application.add_handler(CommandHandler("admin_help", admin_help))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("broadcast", broadcast))
    
    # Add message handler for direct text searches
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        handle_search
    ))
    
    # Add callback query handler
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    
    # Schedule periodic tasks - Solución alternativa
    # En lugar de run_daily, usamos run_repeating con un intervalo de 24h
    application.job_queue.run_repeating(
        check_plan_expiry,
        interval=24*60*60,  # 24 horas en segundos
        first=60            # Esperar 60 segundos antes de la primera ejecución
    )
    
    application.job_queue.run_repeating(
        reset_daily_limits,
        interval=24*60*60,  # 24 horas en segundos
        first=120           # Esperar 120 segundos antes de la primera ejecución
    )
    
    # Start the Bot
    application.run_polling()
    
    # Start Flask server to keep bot alive on Render
    keep_alive()

if __name__ == "__main__":
    main()
