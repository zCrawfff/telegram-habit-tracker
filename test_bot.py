import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
print(f"Bot token: {TELEGRAM_BOT_TOKEN[:20]}...")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"Received /start from user: {update.effective_user.username} (ID: {update.effective_user.id})")
    await update.message.reply_text("Hello! Bot is working!")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"Received message: {update.message.text}")
    await update.message.reply_text(f"You said: {update.message.text}")

def main():
    print("Starting test bot...")
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    
    print("Bot is ready! Send /start to @Streaksterbot")
    app.run_polling()

if __name__ == '__main__':
    main()
