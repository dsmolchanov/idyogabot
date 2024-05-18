import psycopg2
import os
from dotenv import load_dotenv
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext

# Load environment variables
load_dotenv()

# Connect to your PostgreSQL database on Supabase
conn = psycopg2.connect(
    dbname=os.getenv('DB_NAME'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASS'),
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT')
)



TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

def log_event(user_id, group_id, action):
    try:
        with conn.cursor() as cur:
            # Now inserting into the new bigint column for Telegram user IDs
            cur.execute("INSERT INTO access_logs (access_id, telegram_user_id, group_id, action) VALUES (uuid_generate_v4(), %s, %s, %s)", (user_id, group_id, action))
            conn.commit()
    except Exception as e:
        print("Logging error:", e)
        conn.rollback()  # Reset transaction state



def welcome(update: Update, context: CallbackContext):
    for member in update.message.new_chat_members:
        log_event(member.id, 'ID_yoga_start', 'joined')
        context.bot.send_message(chat_id=update.effective_chat.id, text=f"Welcome {member.full_name}!")

def goodbye(update: Update, context: CallbackContext):
    log_event(update.message.left_chat_member.id, 'ID_yoga_start', 'left')
    context.bot.send_message(chat_id=update.effective_chat.id, text=f"Goodbye {update.message.left_chat_member.full_name}!")

async def handle_message(update: Update, context: CallbackContext):
    print("Received message:", update.message.text)  # Debug print
    try:
        user_id = update.message.from_user.id
        group_id = update.effective_chat.id
        action = 'message'
        log_event(user_id, group_id, action)
        print("Logged message event")  # Confirm logging
    except Exception as e:
        print("Error handling message:", str(e))



if __name__ == '__main__':
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, goodbye))
    application.add_handler(MessageHandler(filters.ALL, handle_message))
    application.run_polling()