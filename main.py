import os
import logging
from quart import Quart, request
from hypercorn.config import Config
from hypercorn.asyncio import serve
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler
import asyncio
import asyncpg

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
DATABASE_URL = os.getenv("DATABASE_URL")

app = Quart(__name__)

# Initialize the database pool
db_pool = None

async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)

async def insert_user(user_id: int, username: str):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (telegram_id, username) VALUES ($1, $2) ON CONFLICT (telegram_id) DO NOTHING",
            user_id, username
        )

async def send_greeting(update: Update):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    greeting = f"Hello, {user.first_name}! Welcome to the yoga course."
    
    await query.message.reply_text(greeting)
    await insert_user(user.id, user.username)
    logger.info(f"Greeted user {user.id} and inserted into database")

async def handle_button(update: Update, context):
    await send_greeting(update)

async def setup_application():
    global application
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CallbackQueryHandler(handle_button, pattern='^hello$'))
    await application.initialize()
    await application.start()

@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
async def webhook():
    if request.method == "POST":
        logger.info("Webhook received a POST request")
        try:
            json_data = await request.get_json()
            update = Update.de_json(json_data, application.bot)
            logger.info(f"Parsed update: {update}")
            
            await application.process_update(update)
            logger.info("Update processed")
        except Exception as e:
            logger.error(f"Error processing update: {e}")
            logger.exception("Full traceback:")
    return "OK"

@app.route('/start', methods=['GET'])
async def start():
    keyboard = [[InlineKeyboardButton("Hello", callback_data='hello')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await application.bot.send_message(chat_id='YOUR_CHAT_ID', text="Click the button to get started!", reply_markup=reply_markup)
    return "Button sent!"

async def main():
    await init_db()
    await setup_application()
    
    config = Config()
    config.bind = [f"0.0.0.0:{os.environ.get('PORT', '8080')}"]
    
    logger.info(f"Setting webhook to: {WEBHOOK_URL}")
    await application.bot.set_webhook(WEBHOOK_URL)
    logger.info("Webhook set")
    
    logger.info(f"Starting Hypercorn server on {config.bind}")
    await serve(app, config)

if __name__ == "__main__":
    asyncio.run(main())