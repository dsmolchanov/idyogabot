import asyncio
import logging
import os
from quart import Quart, request
from hypercorn.config import Config as HypercornConfig
from hypercorn.asyncio import serve
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from dotenv import load_dotenv
import psycopg2

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
            logger.info(f"Attempting to insert user {user_id} into database")
            cur.execute(
                "INSERT INTO users (telegram_id, username) VALUES (%s, %s) ON CONFLICT (telegram_id) DO NOTHING",
                (user_id, username)
            )
        conn.commit()
        logger.info(f"User {user_id} inserted or already exists in the database")
    except Exception as e:
        logger.error(f"Error inserting user into database: {e}")
        logger.exception("Full traceback:")
        conn.rollback()
    finally:
        conn.close()

async def start_command(update: Update, context):
    user = update.effective_user
    logger.info(f"Start command received from user {user.id}")
    
    keyboard = [[InlineKeyboardButton("Hello", callback_data='hello')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Welcome, {user.first_name}! Click the button below to get started.",
        reply_markup=reply_markup
    )
    
    insert_user(user.id, user.username)

async def handle_button(update: Update, context):
    logger.info("Hello button clicked")
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    greeting = f"Hello, {user.first_name}! Welcome to the yoga course."
    
    await query.message.reply_text(greeting)
    insert_user(user.id, user.username)
    logger.info(f"Greeted user {user.id} and inserted into database")

@app.route('/', methods=["POST"])
async def handle_webhook():
    try:
        json_data = await request.get_json()
        logger.info(f"Handling a webhook: {json_data}")
        update = Update.de_json(json_data, app.bot)
        await app.application.process_update(update)
        return "OK", 200
    except Exception as e:
        logger.error(f"Something went wrong while handling a request: {e}")
        return "Something went wrong", 500

@app.before_serving
async def startup():
    app.application = Application.builder().token(TELEGRAM_TOKEN).build()
    app.application.add_handler(CommandHandler("start", start_command))
    app.application.add_handler(CallbackQueryHandler(handle_button, pattern='^hello$'))
    
    await app.application.initialize()
    await app.application.start()
    app.bot = app.application.bot
    
    logger.info(f"Setting webhook to: {WEBHOOK_URL}")
    await app.bot.set_webhook(WEBHOOK_URL)
    logger.info("Webhook set")

@app.after_serving
async def shutdown():
    await app.application.stop()
    await app.application.shutdown()

async def main():
    hypercorn_config = HypercornConfig()
    hypercorn_config.bind = [f"0.0.0.0:{os.environ.get('PORT', '8080')}"]
    logger.info(f"Starting the application on {hypercorn_config.bind}")
    await serve(app, hypercorn_config)

if __name__ == "__main__":
    # Test database connection and table
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users LIMIT 1")
            result = cur.fetchone()
            logger.info(f"Successfully queried users table. Sample result: {result}")
        conn.close()
    except Exception as e:
        logger.error(f"Error connecting to the database or querying users table: {e}")
        logger.exception("Full traceback:")
    
    asyncio.run(main())