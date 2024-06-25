from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, CommandHandler
import psycopg2
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database connection
def get_conn():
    conn = psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
    )
    return conn

conn = get_conn()

def check_user(telegram_id):
    with conn.cursor() as cur:
        cur.execute("SELECT telegram_id FROM users WHERE telegram_id = %s", (telegram_id,))
        user = cur.fetchone()
    return user

async def greet_and_offer_payment(update: Update, context: CallbackContext) -> None:
    telegram_id = update.effective_user.id
    user = check_user(telegram_id)

    if not user:
        await update.message.reply_text("Привет, добро пожаловать на курс йоги")
        
        keyboard = [
            [InlineKeyboardButton("Russian banks", url="https://payform.ru/iw4eY7T/")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Please choose a payment method:", reply_markup=reply_markup)

def setup_payment_handlers(application):
    application.add_handler(CommandHandler("start", greet_and_offer_payment))
