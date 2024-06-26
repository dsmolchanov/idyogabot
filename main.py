import os
import psycopg2
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CallbackContext, CommandHandler, MessageHandler, filters
from flask import Flask, request
import logging
import nest_asyncio
import asyncio

# Import payment handling logic
from payment import setup_payment_handlers, get_conn, greet_and_offer_payment

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
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
logger.info("Initializing Application object")
application = Application.builder().token(TELEGRAM_TOKEN).build()
logger.info("Application object initialized")

async def error_handler(update: Update, context: CallbackContext):
    logger.error(f"Exception while handling an update: {context.error}")
    logger.error(f"Update that caused the error: {update}")
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
    logger.info(f"handle_message called with update: {update}")
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
        logger.info("Webhook received a POST request")
        try:
            update = Update.de_json(request.get_json(force=True), application.bot)
            logger.info(f"Received update: {update}")
            
            if update.message:
                if update.message.text.startswith('/'):
                    logger.info(f"Received command: {update.message.text}")
                else:
                    logger.info("Received regular message")
            elif update.callback_query:
                logger.info("Received callback query")
            else:
                logger.info("Received other type of update")
            
            logger.info("Starting to process update")
            future = asyncio.run_coroutine_threadsafe(
                application.process_update(update), loop)
            result = future.result()  # This will raise any exceptions that occurred
            logger.info(f"Update processed. Result: {result}")
        except Exception as e:
            logger.error(f"Error processing update: {e}")
            logger.exception("Full traceback:")
    return "OK"

async def start_command(update: Update, context: CallbackContext):
    logger.info(f"start_command function called for user {update.effective_user.id}")
    logger.info(f"Update object in start_command: {update}")
    logger.info(f"Context object in start_command: {context}")
    try:
        await greet_and_offer_payment(update, context)
        logger.info("greet_and_offer_payment completed successfully")
    except Exception as e:
        logger.error(f"Error in start_command: {e}")
        logger.exception("Full traceback:")

async def setup():
    logger.info("Setting up application...")
    
    # Setup handlers
    setup_payment_handlers(application)
    logger.info("Payment handlers set up")
    
    start_handler = CommandHandler("start", start_command)
    application.add_handler(start_handler)
    logger.info("Added start command handler")
    
    message_handler = MessageHandler(filters.ALL, handle_message)
    application.add_handler(message_handler)
    logger.info("Added message handler")
    
    group_id_handler = CommandHandler("get_group_id", get_group_id)
    application.add_handler(group_id_handler)
    logger.info("Added get_group_id command handler")
    
    application.add_error_handler(error_handler)
    logger.info("Added error handler")

    # Set the webhook
    logger.info(f"Setting webhook to: {WEBHOOK_URL}")
    success = await application.bot.set_webhook(url=WEBHOOK_URL)
    if success:
        logger.info(f"Webhook successfully set to {WEBHOOK_URL}")
    else:
        logger.error(f"Failed to set webhook to {WEBHOOK_URL}")

if __name__ == '__main__':
    logger.info("Starting main execution")
    
    # Apply nest_asyncio to allow nested event loops
    nest_asyncio.apply()
    logger.info("nest_asyncio applied")

    # Create the event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    logger.info("Event loop created and set")

    # Run the setup function
    logger.info("Running setup function")
    loop.run_until_complete(setup())
    logger.info("Setup completed")
    
    # Start the Flask server
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port)