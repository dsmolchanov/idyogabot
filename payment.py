import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import CallbackContext
import logging
from paypalrestsdk import Payment
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

WEBHOOK_URL = os.getenv("WEBHOOK_URL_GENERAL")

# Configure PayPal
import paypalrestsdk

paypalrestsdk.configure({
    "mode": os.getenv("PAYPAL_MODE", "sandbox"),  # sandbox or live
    "client_id": os.getenv("PAYPAL_CLIENT_ID"),
    "client_secret": os.getenv("PAYPAL_CLIENT_SECRET")
})

def create_paypal_payment(plan_id, amount):
    payment = Payment({
        "intent": "sale",
        "payer": {
            "payment_method": "paypal"
        },
        "redirect_urls": {
            "return_url": f"{WEBHOOK_URL}/paypal_return?plan_id={plan_id}",
            "cancel_url": f"{WEBHOOK_URL}/paypal_cancel"
        },
        "transactions": [{
            "item_list": {
                "items": [{
                    "name": f"Yoga Plan {plan_id}",
                    "sku": f"PLAN-{plan_id}",
                    "price": str(amount),
                    "currency": "USD",
                    "quantity": 1
                }]
            },
            "amount": {
                "total": str(amount),
                "currency": "USD"
            },
            "description": f"Yoga Plan {plan_id} Purchase"
        }]
    })

    if payment.create():
        for link in payment.links:
            if link.method == "REDIRECT":
                return link.href
    else:
        logger.error(f"Error creating PayPal payment: {payment.error}")
        return None

async def handle_paypal_payment(query: CallbackQuery, plan_id, price):
    payment_url = create_paypal_payment(plan_id, price)
    if payment_url:
        keyboard = [[InlineKeyboardButton("Pay with PayPal", url=payment_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("Click the button below to proceed with PayPal payment:", reply_markup=reply_markup)
    else:
        await query.message.reply_text("Sorry, there was an error creating the PayPal payment. Please try again later.")

def setup_payment_handlers(application):
    # This function can be used to add any payment-related handlers to the application
    # For now, it's empty as we're handling payments in the main application flow
    pass