import os
import logging
from quart import Quart, request
from hypercorn.config import Config
from hypercorn.asyncio import serve
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext
import asyncio
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
from payment import create_paypal_payment, handle_paypal_payment, setup_payment_handlers

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
        callback_data = f"buy_{plan['plan_id']}_{plan['price']}"
        keyboard = [[InlineKeyboardButton("Купить", callback_data=callback_data)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message, reply_markup=reply_markup)

async def handle_button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("buy_"):
        _, plan_id, price = query.data.split("_")
        keyboard = [
            [InlineKeyboardButton("PayPal", callback_data=f"paypal_{plan_id}_{price}")],
            [InlineKeyboardButton("Credit card", callback_data=f"stripe_{plan_id}_{price}")],
            [InlineKeyboardButton("Российские карты", url="https://payform.ru/iw4eY7T/")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("Выберите способ оплаты:", reply_markup=reply_markup)
    elif query.data.startswith("paypal_"):
        _, plan_id, price = query.data.split("_")
        await handle_paypal_payment(query, plan_id, price)
    elif query.data.startswith("stripe_"):
        _, plan_id, price = query.data.split("_")
        # Implement Stripe payment logic here
        await query.message.reply_text(f"Credit card (Stripe) payment option selected for plan {plan_id} with price {price}. Implement payment logic.")

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

@app.route('/paypal-webhook', methods=['POST'])
async def paypal_webhook():
    print("Received webhook call")
    return '', 200

@app.route('/paypal_return', methods=['GET'])
async def paypal_return():
    plan_id = request.args.get('plan_id')
    payment_id = request.args.get('paymentId')
    payer_id = request.args.get('PayerID')

    # Verify the payment with PayPal
    payment = Payment.find(payment_id)
    if payment.execute({'payer_id': payer_id}):
        logger.info(f"Payment completed for plan {plan_id}")
        # Implement your logic to handle the successful payment, e.g., update the user's subscription
        return "Payment completed successfully"
    else:
        logger.error(f"Error executing payment: {payment.error}")
        return "Error processing payment"
    
@app.route('/paypal_cancel', methods=['GET'])
async def paypal_cancel():
    logger.info("User canceled the PayPal payment")
    return "Payment canceled"

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