from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
import logging

logger = logging.getLogger(__name__)

def get_conn():
    import os
    import psycopg2
    from dotenv import load_dotenv

    load_dotenv()

    conn = psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
    )
    return conn

async def greet_and_offer_payment(update: Update, context: CallbackContext):
    logger.info(f"greet_and_offer_payment function called for user {update.effective_user.id}")
    user = update.effective_user
    telegram_id = user.id
    
    try:
        conn = get_conn()
        logger.info("Database connection established")
        
        with conn.cursor() as cur:
            cur.execute("SELECT telegram_id FROM users WHERE telegram_id = %s", (telegram_id,))
            result = cur.fetchone()
            
        if not result:
            logger.info(f"Inserting new user {telegram_id} into database")
            with conn.cursor() as cur:
                cur.execute("INSERT INTO users (telegram_id, full_name) VALUES (%s, %s)", (telegram_id, user.full_name))
            conn.commit()
        
        greeting = f"Привет, {user.first_name}! Добро пожаловать на курс йоги."
        payment_button = InlineKeyboardButton("Russian banks", url="https://payform.ru/iw4eY7T/")
        keyboard = InlineKeyboardMarkup([[payment_button]])
        
        logger.info(f"Sending greeting to user {telegram_id}")
        await update.message.reply_text(greeting, reply_markup=keyboard)
        logger.info(f"Greeting sent to user {telegram_id}")
    except Exception as e:
        logger.error(f"Error in greet_and_offer_payment: {e}")
        logger.exception("Full traceback:")

def setup_payment_handlers(application):
    pass
