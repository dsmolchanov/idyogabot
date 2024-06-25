import os
import psycopg2
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CallbackContext, CommandHandler, MessageHandler, filters
import logging
from flask import Flask, request
import asyncio

# Import payment handling logic
from payment import setup_payment_handlers, get_conn, greet_and_offer_payment

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

conn = get_conn()
if conn:
    logger.info("Database connection established successfully.")
else:
    logger.error("Failed to establish database connection.")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
GROUP_ID = os.getenv("GROUP_ID")

if not WEBHOOK_URL:
    logger.error("WEBHOOK_URL is not set in the environment variables.")
    raise ValueError("WEBHOOK_URL must be set")

# Create Flask app
app = Flask(__name__)

# Create the Application and pass it your bot's token
application = Application.builder().token(TELEGRAM_TOKEN).build()

async def error_handler(update: Update, context: CallbackContext):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    if update and update.message:
        try:
            await update.message.reply_text("Oops! Something went wrong. Please try again later.")
        except Exception as e:
            logger.error(f"Error sending error message: {e}")

def check_connection():
    global conn
    try:
        conn.cursor().execute("SELECT 1")
    except (psycopg2.InterfaceError, psycopg2.OperationalError):
        conn = get_conn()

def log_event(telegram_user_id, group_id, action, message=None):
    check_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO access_logs (telegram_user_id, group_id, action, message) VALUES (%s, %s, %s, %s)", 
                (telegram_user_id, group_id, action, message)
            )
            conn.commit()
    except Exception as e:
        logger.error("Logging error:", e)
        conn.rollback()

async def get_group_id(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"The group ID is: {chat_id}")

async def handle_message(update: Update, context: CallbackContext):
    if update.message:
        logger.info(f"Received message: {update.message.text}")
        try:
            user_id = update.message.from_user.id
            group_id = update.effective_chat.id
            action = "message"
            message_text = update.message.text
            log_event(user_id, group_id, action, message_text)
            logger.info("Logged message event")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    else:
        logger.warning("Received update without message")

@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), application.bot)
        asyncio.run(application.process_update(update))
    return "OK"

async def setup():
    # Setup handlers
    setup_payment_handlers(application)

    application.add_handler(MessageHandler(filters.ALL, handle_message))
    application.add_handler(CommandHandler("get_group_id", get_group_id))
    application.add_error_handler(error_handler)

    # Set the webhook
    logger.info(f"Setting webhook to: {WEBHOOK_URL}")
    success = await application.bot.set_webhook(url=WEBHOOK_URL)
    if success:
        logger.info(f"Webhook successfully set to {WEBHOOK_URL}")
    else:
        logger.error(f"Failed to set webhook to {WEBHOOK_URL}")

if __name__ == '__main__':
    # Run the setup function
    asyncio.run(setup())
    
    # Start the Flask server
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port)