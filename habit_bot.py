import os
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from supabase import create_client, Client
import stripe
import json

load_dotenv()

# Environment variables
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
STRIPE_PRICE_ID = os.getenv('STRIPE_PRICE_ID')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')

# Initialize services
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
stripe.api_key = STRIPE_SECRET_KEY

# Constants
FREE_HABIT_LIMIT = 3
XP_PER_COMPLETION = 10
LEVEL_XP_REQUIREMENT = 100

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.first_name
    
    # Check if user exists
    try:
        result = supabase.table('users').select("*").eq('user_id', user_id).execute()
        
        if not result.data:
            # Create new user
            supabase.table('users').insert({
                'user_id': user_id,
                'is_premium': False
            }).execute()
            
            # Create user profile
            supabase.table('profiles').insert({
                'user_id': user_id,
                'data': {
                    'name': user_name,
                    'xp': 0,
                    'level': 1,
                    'language': 'en',
                    'timezone': 'UTC'
                }
            }).execute()
            
            welcome_message = f"🎉 Welcome to Habit Tracker Bot, {user_name}!\n\n"
            welcome_message += "I'll help you build better habits and track your progress.\n\n"
            welcome_message += "📋 Available commands:\n"
            welcome_message += "/addhabit - Add a new habit\n"
            welcome_message += "/habits - View your habits\n"
            welcome_message += "/complete - Mark habit as complete\n"
            welcome_message += "/stats - View your XP and level\n"
            welcome_message += "/upgrade - Upgrade to premium\n"
        else:
            welcome_message = f"👋 Welcome back, {user_name}!\n\n"
            welcome_message += "Ready to continue your habit journey?\n"
            welcome_message += "Use /habits to see your current habits."
            
    except Exception as e:
        welcome_message = "❌ There was an error setting up your account. Please make sure the bot is properly configured."
        print(f"Error in start: {e}")
    
    await update.message.reply_text(welcome_message)

# Add habit command
async def add_habit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    
    try:
        # Check user's premium status
        user_result = supabase.table('users').select("is_premium").eq('user_id', user_id).execute()
        is_premium = user_result.data[0]['is_premium'] if user_result.data else False
        
        # Count current habits
        habits_result = supabase.table('habits').select("id").eq('user_id', user_id).eq('is_active', True).execute()
        habit_count = len(habits_result.data)
        
        if not is_premium and habit_count >= FREE_HABIT_LIMIT:
            await update.message.reply_text(
                f"❌ Free users can only track up to {FREE_HABIT_LIMIT} habits.\n\n"
                "🌟 Upgrade to premium for unlimited habits!\n"
                "Use /upgrade to learn more."
            )
            return
        
        # Store state for conversation
        context.user_data['adding_habit'] = True
        await update.message.reply_text(
            "📝 Let's add a new habit!\n\n"
            "What habit would you like to track?\n"
            "(e.g., 'Drink 8 glasses of water', 'Exercise for 30 minutes')"
        )
        
    except Exception as e:
        await update.message.reply_text("❌ Error adding habit. Please try again.")
        print(f"Error in add_habit: {e}")

# Handle habit text
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get('adding_habit'):
        user_id = str(update.effective_user.id)
        habit_name = update.message.text
        
        try:
            # Create the habit
            supabase.table('habits').insert({
                'user_id': user_id,
                'name': habit_name,
                'frequency': 'daily',
                'is_active': True
            }).execute()
            
            context.user_data['adding_habit'] = False
            
            await update.message.reply_text(
                f"✅ Great! I've added '{habit_name}' to your habits.\n\n"
                "You can mark it as complete using /complete\n"
                "View all your habits with /habits"
            )
            
        except Exception as e:
            await update.message.reply_text("❌ Error saving habit. Please try again.")
            print(f"Error saving habit: {e}")

# View habits
async def view_habits(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    
    try:
        # Get user's habits
        habits_result = supabase.table('habits').select("*").eq('user_id', user_id).eq('is_active', True).execute()
        
        if not habits_result.data:
            await update.message.reply_text(
                "📋 You don't have any habits yet!\n\n"
                "Use /addhabit to start tracking your first habit."
            )
            return
        
        message = "📋 Your Active Habits:\n\n"
        
        for i, habit in enumerate(habits_result.data, 1):
            # Check if completed today
            today = datetime.now().date()
            completion_result = supabase.table('habit_logs').select("id").eq(
                'habit_id', habit['id']
            ).gte('completed_at', today.isoformat()).execute()
            
            completed_today = len(completion_result.data) > 0
            status = "✅" if completed_today else "⭕"
            
            message += f"{i}. {status} {habit['name']}\n"
        
        message += "\n💡 Use /complete to mark habits as done!"
        
        await update.message.reply_text(message)
        
    except Exception as e:
        await update.message.reply_text("❌ Error fetching habits. Please try again.")
        print(f"Error in view_habits: {e}")

# Complete habit
async def complete_habit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    
    try:
        # Get user's incomplete habits for today
        habits_result = supabase.table('habits').select("*").eq('user_id', user_id).eq('is_active', True).execute()
        
        if not habits_result.data:
            await update.message.reply_text("You don't have any habits to complete!")
            return
        
        # Create inline keyboard
        keyboard = []
        for habit in habits_result.data:
            # Check if already completed today
            today = datetime.now().date()
            completion_result = supabase.table('habit_logs').select("id").eq(
                'habit_id', habit['id']
            ).gte('completed_at', today.isoformat()).execute()
            
            if not completion_result.data:  # Not completed today
                keyboard.append([InlineKeyboardButton(
                    habit['name'], 
                    callback_data=f"complete_{habit['id']}"
                )])
        
        if not keyboard:
            await update.message.reply_text("🎉 All habits completed for today! Great job!")
            return
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Which habit did you complete?",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        await update.message.reply_text("❌ Error loading habits. Please try again.")
        print(f"Error in complete_habit: {e}")

# Handle completion callback
async def handle_completion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith('complete_'):
        habit_id = query.data.replace('complete_', '')
        user_id = str(query.from_user.id)
        
        try:
            # Log the completion
            supabase.table('habit_logs').insert({
                'habit_id': habit_id,
                'user_id': user_id,
                'streak_count': 1  # TODO: Calculate actual streak
            }).execute()
            
            # Update user XP
            profile_result = supabase.table('profiles').select("data").eq('user_id', user_id).execute()
            profile_data = profile_result.data[0]['data']
            
            new_xp = profile_data.get('xp', 0) + XP_PER_COMPLETION
            new_level = (new_xp // LEVEL_XP_REQUIREMENT) + 1
            
            profile_data['xp'] = new_xp
            profile_data['level'] = new_level
            
            supabase.table('profiles').update({
                'data': profile_data
            }).eq('user_id', user_id).execute()
            
            # Get habit name
            habit_result = supabase.table('habits').select("name").eq('id', habit_id).execute()
            habit_name = habit_result.data[0]['name']
            
            await query.edit_message_text(
                f"✅ Great job! You completed '{habit_name}'!\n\n"
                f"🌟 +{XP_PER_COMPLETION} XP earned!\n"
                f"📊 Total XP: {new_xp}\n"
                f"🎯 Level: {new_level}"
            )
            
        except Exception as e:
            await query.edit_message_text("❌ Error recording completion. Please try again.")
            print(f"Error in handle_completion: {e}")

# View stats
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    
    try:
        # Get user profile
        profile_result = supabase.table('profiles').select("data").eq('user_id', user_id).execute()
        
        if not profile_result.data:
            await update.message.reply_text("❌ Profile not found. Please use /start first.")
            return
        
        profile_data = profile_result.data[0]['data']
        xp = profile_data.get('xp', 0)
        level = profile_data.get('level', 1)
        
        # Calculate progress to next level
        current_level_xp = (level - 1) * LEVEL_XP_REQUIREMENT
        next_level_xp = level * LEVEL_XP_REQUIREMENT
        progress = xp - current_level_xp
        needed = next_level_xp - xp
        
        # Count total completions
        completions_result = supabase.table('habit_logs').select("id").eq('user_id', user_id).execute()
        total_completions = len(completions_result.data)
        
        # Get active habits count
        habits_result = supabase.table('habits').select("id").eq('user_id', user_id).eq('is_active', True).execute()
        active_habits = len(habits_result.data)
        
        message = f"📊 Your Statistics:\n\n"
        message += f"🎯 Level: {level}\n"
        message += f"⭐ Total XP: {xp}\n"
        message += f"📈 Progress: {progress}/{LEVEL_XP_REQUIREMENT} XP\n"
        message += f"🎮 Next level in: {needed} XP\n\n"
        message += f"✅ Total completions: {total_completions}\n"
        message += f"📋 Active habits: {active_habits}\n"
        
        await update.message.reply_text(message)
        
    except Exception as e:
        await update.message.reply_text("❌ Error fetching stats. Please try again.")
        print(f"Error in stats: {e}")

# Upgrade to premium
async def upgrade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    
    try:
        # Create Stripe checkout session
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': STRIPE_PRICE_ID,
                'quantity': 1,
            }],
            mode='subscription',
            success_url='https://t.me/' + (await context.bot.get_me()).username + '?start=premium_success',
            cancel_url='https://t.me/' + (await context.bot.get_me()).username + '?start=premium_cancel',
            metadata={
                'telegram_user_id': user_id
            }
        )
        
        keyboard = [[InlineKeyboardButton("💳 Upgrade Now", url=checkout_session.url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = "🌟 Upgrade to Premium!\n\n"
        message += "✨ Premium Benefits:\n"
        message += "• Unlimited habits (free users: 3 max)\n"
        message += "• Advanced statistics\n"
        message += "• Priority support\n"
        message += "• Custom reminders\n"
        message += "• Export your data\n\n"
        message += "💰 Upgrade now for only £0.50/month!\n"
        message += "❌ Cancel anytime\n\n"
        message += "Click below to upgrade:"
        
        await update.message.reply_text(message, reply_markup=reply_markup)
        
    except Exception as e:
        await update.message.reply_text("❌ Error creating upgrade link. Please try again later.")
        print(f"Error in upgrade: {e}")

# Main function
def main() -> None:
    # Create application
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addhabit", add_habit))
    app.add_handler(CommandHandler("habits", view_habits))
    app.add_handler(CommandHandler("complete", complete_habit))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("upgrade", upgrade))
    
    # Message handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Callback query handler
    app.add_handler(CallbackQueryHandler(handle_completion))
    
    # Run the bot with webhook
    print("🤖 Bot is starting with webhook...")
    
    # Get the port from environment variable (Render provides this)
    PORT = int(os.environ.get('PORT', 8443))
    
    # Your Render app URL
    RENDER_APP_URL = os.environ.get('RENDER_EXTERNAL_URL') or 'https://telegram-habit-tracker-12qk.onrender.com'
    
    # Start webhook
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TELEGRAM_BOT_TOKEN,
        webhook_url=f"{RENDER_APP_URL}/{TELEGRAM_BOT_TOKEN}"
    )

if __name__ == '__main__':
    main()
