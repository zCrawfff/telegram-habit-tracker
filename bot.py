import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from flask import Flask, request
import stripe

load_dotenv()  # Load environment variables

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
STRIPE_PRICE_ID = os.getenv('STRIPE_PRICE_ID')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')

# Only set stripe API key if it exists
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

app = Flask(__name__)

# Start Telegram bot
async def start(update: Update, context) -> None:
    await update.message.reply_text("Welcome to the Habit Tracker Bot!")

async def add_habit(update: Update, context) -> None:
    await update.message.reply_text("Habit added!")

async def stats(update: Update, context) -> None:
    await update.message.reply_text("Your stats.")

# Define Flask route for Stripe Webhook
def handle_stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    event = None

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        print('Invalid payload')
        return '', 400
    except stripe.error.SignatureVerificationError:
        print('Invalid signature')
        return '', 400

    # Handle the checkout.session.completed event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        print('Payment received.')

    return '', 200

# Connect Flask route
app.route('/stripe-webhook', methods=['POST'])(handle_stripe_webhook)

# Initialize Telegram bot
telegram_app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

telegram_app.add_handler(CommandHandler('start', start))
telegram_app.add_handler(CommandHandler('addhabit', add_habit))
telegram_app.add_handler(CommandHandler('stats', stats))

if __name__ == '__main__':
    # Run only the Telegram bot for now
    telegram_app.run_polling()
