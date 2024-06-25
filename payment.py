from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

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
    user = update.effective_user

    # Check if the user is already in the database
    telegram_id = user.id
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT telegram_id FROM users WHERE telegram_id = %s", (telegram_id,))
        result = cur.fetchone()

    if not result:
        # Insert the new user into the database
        with conn.cursor() as cur:
            cur.execute("INSERT INTO users (telegram_id, full_name) VALUES (%s, %s)", (telegram_id, user.full_name))
            conn.commit()

    # Send greeting and payment options
    greeting = f"Привет, {user.first_name}! Добро пожаловать на курс йоги."
    payment_button = InlineKeyboardButton("Russian banks", url="https://payform.ru/iw4eY7T/")
    keyboard = InlineKeyboardMarkup([[payment_button]])

    await update.message.reply_text(greeting, reply_markup=keyboard)

def setup_payment_handlers(application):
    pass
