import os
import psycopg2
from dotenv import load_dotenv
from telegram import Update
import logging

from telegram.ext import (
    Application,
    CallbackContext,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

logger = logging.getLogger(__name__)
# Load environment variables
load_dotenv()

# Function to get a connection
def get_conn():
    conn = psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
    )
    return conn

# Initialize the connection
conn = get_conn()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROUP_ID = "-1002044469000"  # The correct group ID you found

# State constants for ConversationHandler
EMAIL_INPUT = 0

application = Application.builder().token(TELEGRAM_TOKEN).build()

async def error_handler(update: Update, context: CallbackContext) -> None:
    """Log the error and send a message to the user, if applicable."""
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

def log_event(user_id, group_id, action, message=None):
    check_connection()
    try:
        with conn.cursor() as cur:
            print(f"Logging event: user_id={user_id}, group_id={group_id}, action={action}, message={message}")
            cur.execute(
                "INSERT INTO access_logs (telegram_user_id, group_id, action, message) VALUES (%s, %s, %s, %s)", 
                (user_id, group_id, action, message)
            )
            conn.commit()
            print("Event logged successfully")
    except Exception as e:
        print("Logging error:", e)
        conn.rollback()

async def add_user_to_group(update: Update, context: CallbackContext, user_id: str) -> None:
    """Adds a user to the Telegram group and updates the database."""
    check_connection()
    try:
        telegram_id = update.effective_user.id
        with conn.cursor() as cur:
            # Check if user is already in the group
            cur.execute(
                "SELECT 1 FROM group_users WHERE user_id = %s AND group_id = %s",
                (user_id, GROUP_ID),
            )
            existing_user = cur.fetchone()
            print(f"Existing user: {existing_user}")

            if not existing_user:
                # Add user to group_users table
                cur.execute(
                    """
                    INSERT INTO group_users (group_id, user_id, is_active, join_date, action_type, action_timestamp, telegram_id)
                    VALUES (%s, %s, %s, NOW(), %s, NOW(), %s)
                    """,
                    (
                        GROUP_ID,
                        user_id,
                        True,
                        "added",
                        telegram_id,
                    ),
                )
                conn.commit()

                # Create invite link 
                chat = await context.bot.get_chat(GROUP_ID)
                invite_link = await chat.create_invite_link(
                    member_limit=1, creates_join_request=False
                )

                await update.message.reply_text(
                     f"Используй эту <a href='{invite_link.invite_link}'>ссылку</a> чтобы присоединиться к группе.",
                     parse_mode='HTML' 
                 )
            else:
                await update.message.reply_text("Ты уже являешься участником группы!")
    except psycopg2.errors.UniqueViolation as e: # Catch unique violation error
        await update.message.reply_text("Ты уже являешься участником группы! Ждем тебя на уроке!")
    except Exception as e:
        print(f"Error adding user to group: {e}")
        await update.message.reply_text(
            "Произошла ошибка при добавлении в группу. Пожалуйста, попробуй позже."
        )

async def start(update: Update, context: CallbackContext):
    """Send a message when the command /start is issued."""
    user = update.effective_user
    telegram_id = user.id  # Get the Telegram user ID
    full_name = f"{user.first_name} {user.last_name}".strip()  # Get the full name

    # Get the 'order_id' from the start command arguments
    order_id = context.args[0] if context.args else None

    print(f"Received order_id: {order_id}, telegram_id: {telegram_id}, full_name: {full_name}")

    if order_id:
        check_connection()
        try:
            with conn.cursor() as cur:
                # Log the SQL query
                query = "SELECT user_id FROM payment_transactions WHERE order_id = %s"
                print(f"Executing query: {query} with order_id: {order_id}")
                cur.execute(query, (order_id,))
                result = cur.fetchone()

                if result:
                    user_id = result[0]
                    print(f"Found user_id: {user_id} for order_id: {order_id}")

                    # Update the 'users' table with the 'telegram_id' and 'full_name'
                    update_query = "UPDATE users SET telegram_id = %s, full_name = %s WHERE user_id = %s"
                    print(f"Executing query: {update_query} with telegram_id: {telegram_id}, full_name: {full_name}, and user_id: {user_id}")
                    cur.execute(update_query, (telegram_id, full_name, user_id))
                    conn.commit()
                    greeting = (
                        f"Привет, {user.mention_html()}. Добро пожаловать. Твой ID заказа: {order_id}. Твой аккаунт теперь подключен!"
                    )
                    await update.message.reply_html(greeting)
                    # Add user to the group 
                    await add_user_to_group(update, context, user_id)
                    return ConversationHandler.END
                else:
                    print(f"No user_id found for order_id: {order_id}")
                    await update.message.reply_text(
                        f"Приветствую, {user.first_name}, мы пока не получили твоего номера заказа. Введи свой email, и мы проверим."
                    )
                    return EMAIL_INPUT
        except Exception as e:
            print(f"Error updating user table: {e}")
            greeting = (
                f"Привет {user.mention_html()}! Добро пожаловать! Возникла ошибка при обработке запроса. Пожалуйста, попробуй позже."
            )
            await update.message.reply_html(greeting)
            return ConversationHandler.END
    else:
        print("No order_id provided")
        await update.message.reply_text(
            f"Приветствую, {user.first_name}, мы пока не получили твоего номера заказа. Введи свой email, и мы проверим."
        )
        return EMAIL_INPUT

async def process_email(update: Update, context: CallbackContext) -> int:
    """Process the user's email."""
    user = update.effective_user
    email = update.message.text

    check_connection()
    try:
        with conn.cursor() as cur:
            # Check if user exists
            cur.execute("SELECT user_id FROM users WHERE email = %s", (email,))
            user_result = cur.fetchone()

            if user_result:
                user_id = user_result[0]

                # Check if user has an active subscription
                cur.execute(
                    """
                    SELECT s.status 
                    FROM subscriptions s
                    JOIN subscription_plans p ON s.plan_id = p.plan_id
                    WHERE s.user_id = %s AND s.status = 'active'
                    """,
                    (user_id,),
                )
                subscription_result = cur.fetchone()

                if subscription_result:
                    await update.message.reply_text(
                        f"{user.first_name}, у тебя есть активная подписка!"
                    )
                    await add_user_to_group(update, context, user_id)
                else:
                    await update.message.reply_text(
                        f"{user.first_name}, у тебя нет активной подписки."
                    )
            else:
                await update.message.reply_text(
                    f"Пользователь с email {email} не найден."
                )
    except Exception as e:
        print(f"Error processing email: {e}")
        await update.message.reply_text(
            "Произошла ошибка при обработке email. Пожалуйста, попробуй позже."
        )

    return ConversationHandler.END

async def get_group_id(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    chat = await context.bot.get_chat(chat_id)
    await update.message.reply_text(f"The group ID is: {chat.id}")

async def welcome(update: Update, context: CallbackContext):
    group_id = update.effective_chat.id  # Get group_id here
    for member in update.message.new_chat_members:
        log_event(member.id, group_id, 'joined') 
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Мы тебе рады, {member.full_name}!")

async def goodbye(update: Update, context: CallbackContext):
    group_id = update.effective_chat.id  
    user_id = update.message.left_chat_member.id

    if user_id is not None:  # Check if user_id is not None
        log_event(user_id, group_id, 'left') 
        await context.bot.send_message(chat_id=group_id, text=f"Ну и пока.. {update.message.left_chat_member.full_name}!")

async def handle_message(update: Update, context: CallbackContext):
    if update.message:
        logger.info(f"Received message: {update.message.text}")  # Debug print
        try:
            user_id = update.message.from_user.id
            group_id = update.effective_chat.id
            action = "message"
            message_text = update.message.text
            log_event(user_id, group_id, action, message_text)
            logger.info("Logged message event")  # Confirm logging
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    else:
        logger.warning("Received update without message")


if __name__ == '__main__':
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Conversation handler for /start and email input
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={EMAIL_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_email)]},
        fallbacks=[],  # Add fallbacks if needed
    )

    # Add the conversation handler to the application
    application.add_handler(conv_handler)

    # Add other handlers
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, goodbye))
    application.add_handler(MessageHandler(filters.ALL, handle_message))
    application.add_handler(CommandHandler("get_group_id", get_group_id))

    # Add error handler
    application.add_error_handler(error_handler) 

    # Run the bot with polling
    application.run_polling()
