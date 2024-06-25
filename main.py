import os
import psycopg2
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CallbackContext, CommandHandler, CallbackQueryHandler
from flask import Flask, request
import logging

# Import payment handling logic
from payment import setup_payment_handlers, get_conn, check_user, greet_and_offer_payment, start, button_handler

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

# Initialize the bot application
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

async def add_user_to_group(update: Update, context: CallbackContext, telegram_id: int) -> None:
    check_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM group_users WHERE telegram_id = %s AND group_id = %s",
                (telegram_id, GROUP_ID),
            )
            existing_user = cur.fetchone()
            
            if not existing_user:
                cur.execute(
                    """
                    INSERT INTO group_users (group_id, telegram_id, is_active, join_date, action_type, action_timestamp)
                    VALUES (%s, %s, %s, NOW(), %s, NOW())
                    """,
                    (GROUP_ID, telegram_id, True, "added")
                )
                conn.commit()

                chat = await context.bot.get_chat(GROUP_ID)
                invite_link = await chat.create_invite_link(member_limit=1, creates_join_request=False)

                await update.message.reply_text(
                    f"Используй эту <a href='{invite_link.invite_link}'>ссылку</a> чтобы присоединиться к группе.",
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text("Ты уже являешься участником группы!")
    except psycopg2.errors.UniqueViolation:
        await update.message.reply_text("Ты уже являешься участником группы! Ждем тебя на уроке!")
    except Exception as e:
        logger.error(f"Error adding user to group: {e}")
        await update.message.reply_text(
            "Произошла ошибка при добавлении в группу. Пожалуйста, попробуй позже."
        )

async def start_command(update: Update, context: CallbackContext):
    try:
        user = update.effective_user
        telegram_id = user.id
        full_name = f"{user.first_name} {user.last_name}".strip()

        order_id = context.args[0] if context.args else None

        if order_id:
            check_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT telegram_id FROM payment_transactions WHERE order_id = %s", (order_id,))
                    result = cur.fetchone()

                    if result:
                        telegram_id = result[0]

                        cur.execute("UPDATE users SET full_name = %s WHERE telegram_id = %s", (full_name, telegram_id))
                        conn.commit()

                        await update.message.reply_html(
                            f"Привет, {user.mention_html()}. Добро пожаловать. Твой ID заказа: {order_id}. Твой аккаунт теперь подключен!"
                        )
                        await add_user_to_group(update, context, telegram_id)
                        return ConversationHandler.END
                    else:
                        await update.message.reply_text(
                            f"Приветствую, {user.first_name}, мы пока не получили твоего номера заказа. Введи свой email, и мы проверим."
                        )
                        return EMAIL_INPUT
            except Exception as e:
                logger.error(f"Error updating user table: {e}")
                await update.message.reply_html(
                    f"Привет {user.mention_html()}! Добро пожаловать! Возникла ошибка при обработке запроса. Пожалуйста, попробуй позже."
                )
                return ConversationHandler.END
        else:
            await greet_and_offer_payment(update, context)
            return EMAIL_INPUT
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте позже.")

async def process_email(update: Update, context: CallbackContext) -> int:
    user = update.effective_user
    email = update.message.text

    check_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT telegram_id FROM users WHERE email = %s", (email,))
            user_result = cur.fetchone()

            if user_result:
                telegram_id = user_result[0]

                cur.execute(
                    """
                    SELECT s.status 
                    FROM subscriptions s
                    JOIN subscription_plans p ON s.plan_id = p.plan_id
                    WHERE s.telegram_id = %s AND s.status = 'active'
                    """,
                    (telegram_id,)
                )
                subscription_result = cur.fetchone()

                if subscription_result:
                    await update.message.reply_text(
                        f"{user.first_name}, у тебя есть активная подписка!"
                    )
                    await add_user_to_group(update, context, telegram_id)
                else:
                    await update.message.reply_text(
                        f"{user.first_name}, у тебя нет активной подписки."
                    )
            else:
                await update.message.reply_text(
                    f"Пользователь с email {email} не найден."
                )
    except Exception as e:
        logger.error(f"Error processing email: {e}")
        await update.message.reply_text(
            "Произошла ошибка при обработке email. Пожалуйста, попробуй позже."
        )

    return ConversationHandler.END

async def get_group_id(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"The group ID is: {chat_id}")

async def welcome(update: Update, context: CallbackContext):
    group_id = update.effective_chat.id
    for member in update.message.new_chat_members:
        log_event(member.id, group_id, 'joined')
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Мы тебе рады, {member.full_name}!")

async def goodbye(update: Update, context: CallbackContext):
    group_id = update.effective_chat.id
    user_id = update.message.left_chat_member.id

    if user_id is not None:
        log_event(user_id, group_id, 'left')
        await context.bot.send_message(chat_id=group_id, text=f"Ну и пока.. {update.message.left_chat_member.full_name}!")

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

if __name__ == '__main__':
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    setup_payment_handlers(application)

    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, goodbye))
    application.add_handler(MessageHandler(filters.ALL, handle_message))
    application.add_handler(CommandHandler("get_group_id", get_group_id))
    application.add_error_handler(error_handler)

    logger.info("Starting bot")

    # Flask app for handling webhook
    app = Flask(__name__)

    @app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
    def webhook():
        update = Update.de_json(request.get_json(force=True), application.bot)
        application.process_update(update)
        return "OK"

    app.run(host='0.0.0.0', port=8443)
