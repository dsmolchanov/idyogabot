import os
import logging
from quart import Quart, request
from hypercorn.config import Config
from hypercorn.asyncio import serve
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler
import asyncio
import psycopg2
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

app = Quart(__name__)

def get_conn():
    conn = psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
    )
    return conn

def insert_user(user_id: int, username: str):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (telegram_id, username) VALUES (%s, %s) ON CONFLICT (telegram_id) DO NOTHING",
                (user_id, username)
            )
        conn.commit()
        logger.info(f"User {user_id} inserted or already exists in the database")
    except Exception as e:
        logger.error(f"Error inserting user into database: {e}")
        conn.rollback()
    finally:
        conn.close()

async def send_greeting(update: Update):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    greeting = f"Hello, {user.first_name}! Welcome to the yoga course."
    
    await query.message.reply_text(greeting)
    insert_user(user.id, user.username)
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
    await setup_application()
    
    config = Config()
    config.bind = [f"0.0.0.0:{os.environ.get('PORT', '8080')}"]
    
    logger.info(f"Setting webhook to: {WEBHOOK_URL}")
    await application.bot.set_webhook(WEBHOOK_URL)
    logger.info("Webhook set")
    
    logger.info(f"Starting Hypercorn server on {config.bind}")
    await serve(app, config)

if __name__ == "__main__":
    # Test database connection
    try:
        conn = get_conn()
        logger.info("Successfully connected to the database")
        conn.close()
    except Exception as e:
        logger.error(f"Error connecting to the database: {e}")
    
    asyncio.run(main())