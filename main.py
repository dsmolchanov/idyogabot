import os
import logging
from quart import Quart, request
from hypercorn.config import Config
from hypercorn.asyncio import serve
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext
import asyncio
from dotenv import load_dotenv
from supabase import create_client, Client

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

app = Quart(__name__)

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

async def get_subscription_plans():
    try:
        response = supabase.table('subscription_plans').select('*').execute()
        return response.data
    except Exception as e:
        logger.error(f"Error fetching subscription plans: {e}")
        return []

async def start_command(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    await update.message.reply_text(f"Привет, {user.first_name}! Добро пожаловать в наш йога-курс.")
    await send_subscription_plans(update, context)

async def send_subscription_plans(update: Update, context: CallbackContext):
    plans = await get_subscription_plans()
    for plan in plans:
        message = (
            f"План: {plan['plan_name']}\n"
            f"Длительность: {plan['duration']}\n"
            f"Описание: {plan['description']}\n"
            f"Цена: {plan['price']}"
        )
        keyboard = [[InlineKeyboardButton("Купить", callback_data=f"buy_{plan['id']}")]]
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
    asyncio.run(main())