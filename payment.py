import os
import psycopg2
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler
import logging

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Database connection
def get_conn():
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
        )
        return conn
    except Exception as e:
        logger.error(f"Error connecting to database: {e}")
        return None

def check_user(telegram_id):
    conn = get_conn()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT telegram_id FROM users WHERE telegram_id = %s", (telegram_id,))
            user = cur.fetchone()
        return user
    except Exception as e:
        logger.error(f"Error checking user: {e}")
        return None
    finally:
        conn.close()

def insert_user(telegram_id, full_name, username):
    conn = get_conn()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (telegram_id, full_name, username) VALUES (%s, %s, %s)",
                (telegram_id, full_name, username)
            )
            conn.commit()
            logger.info(f"Inserted user {telegram_id}")
    except Exception as e:
        logger.error(f"Error inserting user: {e}")
        conn.rollback()
    finally:
        conn.close()

async def greet_and_offer_payment(update: Update, context: CallbackContext) -> None:
    telegram_id = update.effective_user.id
    full_name = f"{update.effective_user.first_name} {update.effective_user.last_name}".strip()
    username = update.effective_user.username

    user = check_user(telegram_id)

    if not user:
        logger.info(f"New user {telegram_id}. Inserting into database.")
        insert_user(telegram_id, full_name, username)
        await update.message.reply_text("Привет, добро пожаловать на курс йоги")
        
        keyboard = [
            [InlineKeyboardButton("Russian banks", url="https://payform.ru/iw4eY7T/")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Please choose a payment method:", reply_markup=reply_markup)
    else:
        logger.info(f"User {telegram_id} already exists in the database.")
        await update.message.reply_text("Welcome back!")

async def start(update: Update, context: CallbackContext) -> None:
    keyboard = [
        [InlineKeyboardButton("Start", callback_data='start')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Press the button below to start:", reply_markup=reply_markup)

async def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    logger.debug(f"Button pressed with data: {query.data}")

    if query.data == 'start':
        logger.debug("Start button pressed, calling greet_and_offer_payment")
        await greet_and_offer_payment(query, context)

def setup_payment_handlers(application):
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))