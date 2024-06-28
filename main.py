import os
import logging
from quart import Quart, request
from hypercorn.config import Config
from hypercorn.asyncio import serve
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext
import asyncio
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

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


def insert_user(user_id: int, username: str, first_name: str, last_name: str):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (telegram_id, username, first_name, last_name) VALUES (%s, %s, %s, %s) ON CONFLICT (telegram_id) DO NOTHING",
                (user_id, username, first_name, last_name)
            )
        conn.commit()
        logger.info(f"User {user_id} inserted or already exists in the database")
    except Exception as e:
        logger.error(f"Error inserting user into database: {e}")
        conn.rollback()
    finally:
        conn.close()

def get_subscription_plans():
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM subscription_plans")
            plans = cur.fetchall()
        conn.close()
        return plans
    except Exception as e:
        logger.error(f"Error fetching subscription plans: {e}")
        return []

async def start_command(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    # Insert user into the database
    insert_user(user.id, user.username, user.first_name, user.last_name)
    
    await update.message.reply_text(f"Привет, {user.first_name}! Добро пожаловать в наш йога-курс.")
    await send_subscription_plans(update, context)

async def send_subscription_plans(update: Update, context: CallbackContext):
    plans = get_subscription_plans()
    for plan in plans:
        message = (
            f"План: {plan['plan_name']}\n"
            f"Длительность: {plan['duration']}\n"
            f"Описание: {plan['description']}\n"
            f"Цена: {plan['price']}"
        )
        keyboard = [[InlineKeyboardButton("Купить", callback_data=f"buy_{plan['plan_id']}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message, reply_markup=reply_markup)

async def handle_button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("buy_"):
        plan_id = query.data.split("_")[1]
        keyboard = [
            [InlineKeyboardButton("PayPal", callback_data=f"paypal_{plan_id}")],
            [InlineKeyboardButton("Credit card", callback_data=f"stripe_{plan_id}")],
            [InlineKeyboardButton("Российские карты", url="https://payform.ru/iw4eY7T/")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("Выберите способ оплаты:", reply_markup=reply_markup)
    elif query.data.startswith("paypal_"):
        # Implement PayPal payment logic here
        await query.message.reply_text("PayPal payment option selected. Implement payment logic.")
    elif query.data.startswith("stripe_"):
        # Implement Stripe payment logic here
        await query.message.reply_text("Credit card (Stripe) payment option selected. Implement payment logic.")

async def setup_application():
    global application
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(handle_button))
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
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM subscription_plans LIMIT 1")
            result = cur.fetchone()
            logger.info(f"Successfully queried subscription_plans table. Sample result: {result}")
        conn.close()
    except Exception as e:
        logger.error(f"Error connecting to the database or querying subscription_plans table: {e}")
        logger.exception("Full traceback:")
    
    asyncio.run(main())