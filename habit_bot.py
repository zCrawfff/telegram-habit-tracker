import os
import asyncio
from datetime import datetime, timedelta, time
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from supabase import create_client, Client
import stripe
import json
import openai
import pytz

load_dotenv()

# Load translations
with open('translations.json', 'r') as f:
    translations = json.load(f)

def get_translation(user_language, key, **kwargs):
    # Default to English if language is not supported
    lang = translations.get(user_language, translations['en'])
    return lang.get(key, '').format(**kwargs)

# Environment variables
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
STRIPE_PRICE_ID = os.getenv('STRIPE_PRICE_ID')
STRIPE_COACH_PRICE_ID = os.getenv('STRIPE_COACH_PRICE_ID')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Initialize services
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
stripe.api_key = STRIPE_SECRET_KEY

# Constants
FREE_HABIT_LIMIT = 3
XP_PER_COMPLETION = 10
LEVEL_XP_REQUIREMENT = 100
DAILY_COACH_LIMIT = 10  # Max coach sessions per day

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    user_name = update.effective_user.first_name
    
    # Check for payment success parameter
    if context.args and len(context.args) > 0:
        if context.args[0] == 'premium_success':
            # Check if there's a pending Stripe session for this user
            try:
                # Store session ID when creating checkout
                session_id = context.user_data.get('pending_session_id')
                if session_id:
                    # Verify the session with Stripe
                    session = stripe.checkout.Session.retrieve(session_id)
                if session.payment_status == 'paid':
                    # Determine which tier based on price ID
                    if session.line_items and session.line_items.data:
                        price_id = session.line_items.data[0].price.id
                        if price_id == STRIPE_COACH_PRICE_ID:
                            # Update user to coach tier
                            supabase.table('users').update({
                                'is_premium': True,
                                'subscription_tier': 'coach'
                            }).eq('user_id', user_id).execute()
                            await update.message.reply_text(
                                "🎉 Congratulations! You're now a Coach tier member!\n\n"
                                "✨ You now have access to:\n"
                                "• Unlimited habits\n"
                                "• AI Habit Coach\n"
                                "• All premium features\n\n"
                                "Thank you for your support! 💙"
                            )
                        else:
                            # Update user to basic premium
                            supabase.table('users').update({
                                'is_premium': True,
                                'subscription_tier': 'basic'
                            }).eq('user_id', user_id).execute()
                            await update.message.reply_text(
                                "🎉 Congratulations! You're now a Premium member!\n\n"
                                "✨ You can now add unlimited habits and access all premium features.\n\n"
                                "Thank you for your support! 💙"
                            )
                    context.user_data['pending_session_id'] = None
                    return
            except Exception as e:
                print(f"Error checking payment: {e}")
        elif context.args[0] == 'premium_cancel':
            await update.message.reply_text(
                "❌ Payment cancelled.\n\n"
                "If you change your mind, you can always upgrade later with /upgrade"
            )
            return
    
    # Check if user exists
    try:
        result = supabase.table('users').select("*").eq('user_id', user_id).execute()
        
        if not result.data:
            # Create new user
            supabase.table('users').insert({
                'user_id': user_id,
                'is_premium': False,
                'subscription_tier': 'free'
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
            
            language = 'en'  # Default language for new users
            welcome_message = f"🎉 Welcome to Habit Tracker Bot, {user_name}!\n\n"
            welcome_message += "I'll help you build better habits and track your progress.\n\n"
            welcome_message += "📋 Available commands:\n"
            welcome_message += "/addhabit - Add a new habit\n"
            welcome_message += "/habits - View your habits\n"
            welcome_message += "/complete - Mark habit as complete\n"
            welcome_message += "/stats - View your XP and level\n"
            welcome_message += "/upgrade - Upgrade to premium\n"
        else:
            # Get user's language preference from profile
            profile_result = supabase.table('profiles').select("data").eq('user_id', user_id).execute()
            if profile_result.data and profile_result.data[0]['data']:
                language = profile_result.data[0]['data'].get('language', 'en')
            else:
                language = 'en'
            
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
    user_id = str(update.effective_user.id)
    text = update.message.text
    
    # Check if we're waiting for time input
    setting_time_key = None
    for key in context.user_data:
        if key.startswith('setting_time_'):
            setting_time_key = key
            break
    
    if setting_time_key:
        # Validate time format
        try:
            time_parts = text.split(':')
            if len(time_parts) != 2:
                raise ValueError
            
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
            
            # Store the time
            habit_id = setting_time_key.replace('setting_time_', '')
            context.user_data[f'time_{habit_id}'] = text
            context.user_data.pop(setting_time_key)
            
            # Get habit name
            habit_result = supabase.table('habits').select("name").eq('id', habit_id).execute()
            habit_name = habit_result.data[0]['name'] if habit_result.data else "your habit"
            
            # Show confirmation with options
            keyboard = [
                [InlineKeyboardButton("📅 Choose Days", callback_data=f'days_{habit_id}')],
                [InlineKeyboardButton("🚑 Fallback Reminder", callback_data=f'fallback_{habit_id}')],
                [InlineKeyboardButton("💾 Save Settings", callback_data=f'save_reminder_{habit_id}')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✅ Time set to {text}!\n\n"
                f"**{habit_name}** will remind you at {text}.\n\n"
                "What would you like to do next?",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid time format!\n\n"
                "Please use 24-hour format: HH:MM\n"
                "Examples: 09:00, 21:30, 13:45"
            )
        return
    
    # Check for fallback time input
    setting_fallback_key = None
    for key in context.user_data:
        if key.startswith('setting_fallback_time_'):
            setting_fallback_key = key
            break
            
    if setting_fallback_key:
        # Similar validation for fallback time
        try:
            time_parts = text.split(':')
            if len(time_parts) != 2:
                raise ValueError
            
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
            
            # Store the fallback time
            habit_id = setting_fallback_key.replace('setting_fallback_time_', '')
            context.user_data[f'fallback_time_{habit_id}'] = text
            context.user_data[f'fallback_enabled_{habit_id}'] = True
            context.user_data.pop(setting_fallback_key)
            
            # Back to reminder setup
            keyboard = [[InlineKeyboardButton("⬅ Back to Settings", callback_data=f'remind_setup_{habit_id}')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✅ Fallback time set to {text}!\n\n"
                f"You'll get a final reminder at {text} if you haven't logged your habit.",
                reply_markup=reply_markup
            )
            
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid time format!\n\n"
                "Please use 24-hour format: HH:MM"
            )
        return
    
    # Check if setting timezone
    if context.user_data.get('setting_timezone'):
        try:
            # Validate timezone
            test_tz = pytz.timezone(text)
            
            # Update user profile
            profile_result = supabase.table('profiles').select("data").eq('user_id', user_id).execute()
            profile_data = profile_result.data[0]['data']
            profile_data['timezone'] = text
            
            supabase.table('profiles').update({
                'data': profile_data
            }).eq('user_id', user_id).execute()
            
            # Also update users table for reminders
            supabase.table('users').update({
                'timezone': text
            }).eq('user_id', user_id).execute()
            
            context.user_data.pop('setting_timezone', None)
            
            await update.message.reply_text(
                f"✅ Timezone updated to {text}!\n\n"
                f"All your reminders will now use this timezone."
            )
            
        except pytz.exceptions.UnknownTimeZoneError:
            await update.message.reply_text(
                "❌ Invalid timezone!\n\n"
                "Please use a valid timezone like:\n"
                "• Europe/London\n"
                "• America/New_York\n"
                "• UTC"
            )
        return
    
    # Original habit adding logic
    if context.user_data.get('adding_habit'):
        habit_name = text
        
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

# Handle callback queries
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    # Handle upgrade tier selection
    if query.data == 'upgrade_basic':
        user_id = str(query.from_user.id)
        try:
            # Create Stripe checkout for basic tier
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
                    'telegram_user_id': user_id,
                    'tier': 'basic'
                },
                client_reference_id=user_id
            )
            context.user_data['pending_session_id'] = checkout_session.id
            
            keyboard = [[InlineKeyboardButton("💳 Pay Now", url=checkout_session.url)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "🌟 **Basic Premium** (£0.50/month)\n\n"
                "Click below to complete your purchase:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        except Exception as e:
            await query.edit_message_text("❌ Error creating payment link. Please try again.")
            print(f"Error creating basic checkout: {e}")
    
    elif query.data == 'upgrade_coach':
        user_id = str(query.from_user.id)
        try:
            # Create Stripe checkout for coach tier
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price': STRIPE_COACH_PRICE_ID,
                    'quantity': 1,
                }],
                mode='subscription',
                success_url='https://t.me/' + (await context.bot.get_me()).username + '?start=premium_success',
                cancel_url='https://t.me/' + (await context.bot.get_me()).username + '?start=premium_cancel',
                metadata={
                    'telegram_user_id': user_id,
                    'tier': 'coach'
                },
                client_reference_id=user_id
            )
            context.user_data['pending_session_id'] = checkout_session.id
            
            keyboard = [[InlineKeyboardButton("💳 Pay Now", url=checkout_session.url)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "💪 **Coach Tier** (£2.50/month)\n\n"
                "Click below to complete your purchase:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        except Exception as e:
            await query.edit_message_text("❌ Error creating payment link. Please try again.")
            print(f"Error creating coach checkout: {e}")
    
    elif query.data.startswith('remind_setup_'):
        habit_id = query.data.replace('remind_setup_', '')
        user_id = str(query.from_user.id)
        
        # Get current schedule if exists
        schedule_result = supabase.table('habit_schedules').select("*").eq('habit_id', habit_id).execute()
        if schedule_result.data:
            current = schedule_result.data[0]
            days = ', '.join(current['days'])
            time = str(current['reminder_time'])[:5]  # HH:MM format
            fallback = f"\n🚑 Fallback: {str(current['fallback_time'])[:5]}" if current['fallback_enabled'] else ""
            
            message = f"**Current Settings:**\n"
            message += f"📅 Days: {days}\n"
            message += f"🕓 Time: {time}{fallback}\n\n"
            message += "What would you like to change?"
        else:
            message = "Let's set up a reminder for this habit!\n\nChoose what to configure:"
        
        keyboard = [
            [InlineKeyboardButton("📅 Choose Days", callback_data=f'days_{habit_id}')],
            [InlineKeyboardButton("⏰ Set Time", callback_data=f'time_{habit_id}')],
            [InlineKeyboardButton("🚑 Fallback Reminder", callback_data=f'fallback_{habit_id}')],
            [InlineKeyboardButton("💾 Save Settings", callback_data=f'save_reminder_{habit_id}')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    elif query.data.startswith('days_'):
        habit_id = query.data.replace('days_', '')
        
        # Get current days or defaults
        schedule_key = f'schedule_{habit_id}'
        
        # Check if we already have days in context
        if schedule_key not in context.user_data:
            # If not, check database
            schedule_result = supabase.table('habit_schedules').select("days").eq('habit_id', habit_id).execute()
            
            if schedule_result.data:
                selected_days = schedule_result.data[0]['days']
            else:
                # Default to weekdays
                selected_days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
            
            context.user_data[schedule_key] = selected_days
        else:
            selected_days = context.user_data[schedule_key]
        
        keyboard = [
            [InlineKeyboardButton(f"{'✅' if 'Mon' in selected_days else '⬜'} Mon", callback_data=f'day_Mon_{habit_id}'),
             InlineKeyboardButton(f"{'✅' if 'Tue' in selected_days else '⬜'} Tue", callback_data=f'day_Tue_{habit_id}'),
             InlineKeyboardButton(f"{'✅' if 'Wed' in selected_days else '⬜'} Wed", callback_data=f'day_Wed_{habit_id}')],
            [InlineKeyboardButton(f"{'✅' if 'Thu' in selected_days else '⬜'} Thu", callback_data=f'day_Thu_{habit_id}'),
             InlineKeyboardButton(f"{'✅' if 'Fri' in selected_days else '⬜'} Fri", callback_data=f'day_Fri_{habit_id}'),
             InlineKeyboardButton(f"{'✅' if 'Sat' in selected_days else '⬜'} Sat", callback_data=f'day_Sat_{habit_id}')],
            [InlineKeyboardButton(f"{'✅' if 'Sun' in selected_days else '⬜'} Sun", callback_data=f'day_Sun_{habit_id}')],
            [InlineKeyboardButton("✅ Done", callback_data=f'remind_setup_{habit_id}')]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📅 **Select Days**\n\n"
            "When should we remind you about this habit?\n\n"
            f"Selected: {', '.join(selected_days) or 'None'}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    elif query.data.startswith('day_'):
        parts = query.data.split('_')
        day = parts[1]
        habit_id = parts[2]
        
        # Toggle day selection
        schedule_key = f'schedule_{habit_id}'
        selected_days = context.user_data.get(schedule_key, [])
        
        if day in selected_days:
            selected_days.remove(day)
        else:
            selected_days.append(day)
        
        context.user_data[schedule_key] = selected_days
        
        # Refresh the keyboard
        keyboard = [
            [InlineKeyboardButton(f"{'✅' if 'Mon' in selected_days else '⬜'} Mon", callback_data=f'day_Mon_{habit_id}'),
             InlineKeyboardButton(f"{'✅' if 'Tue' in selected_days else '⬜'} Tue", callback_data=f'day_Tue_{habit_id}'),
             InlineKeyboardButton(f"{'✅' if 'Wed' in selected_days else '⬜'} Wed", callback_data=f'day_Wed_{habit_id}')],
            [InlineKeyboardButton(f"{'✅' if 'Thu' in selected_days else '⬜'} Thu", callback_data=f'day_Thu_{habit_id}'),
             InlineKeyboardButton(f"{'✅' if 'Fri' in selected_days else '⬜'} Fri", callback_data=f'day_Fri_{habit_id}'),
             InlineKeyboardButton(f"{'✅' if 'Sat' in selected_days else '⬜'} Sat", callback_data=f'day_Sat_{habit_id}')],
            [InlineKeyboardButton(f"{'✅' if 'Sun' in selected_days else '⬜'} Sun", callback_data=f'day_Sun_{habit_id}')],
            [InlineKeyboardButton("✅ Done", callback_data=f'remind_setup_{habit_id}')]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📅 **Select Days**\n\n"
            "When should we remind you about this habit?\n\n"
            f"Selected: {', '.join(selected_days) or 'None'}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    elif query.data.startswith('time_'):
        habit_id = query.data.replace('time_', '')
        
        # Show time selection grid
        keyboard = [
            [InlineKeyboardButton("🌅 6:00", callback_data=f'settime_06:00_{habit_id}'),
             InlineKeyboardButton("☀️ 7:00", callback_data=f'settime_07:00_{habit_id}'),
             InlineKeyboardButton("🍳 8:00", callback_data=f'settime_08:00_{habit_id}')],
            [InlineKeyboardButton("💼 9:00", callback_data=f'settime_09:00_{habit_id}'),
             InlineKeyboardButton("☕ 10:00", callback_data=f'settime_10:00_{habit_id}'),
             InlineKeyboardButton("🌞 12:00", callback_data=f'settime_12:00_{habit_id}')],
            [InlineKeyboardButton("🍕 14:00", callback_data=f'settime_14:00_{habit_id}'),
             InlineKeyboardButton("🎉 17:00", callback_data=f'settime_17:00_{habit_id}'),
             InlineKeyboardButton("🌃 19:00", callback_data=f'settime_19:00_{habit_id}')],
            [InlineKeyboardButton("🌙 20:00", callback_data=f'settime_20:00_{habit_id}'),
             InlineKeyboardButton("🌜 21:00", callback_data=f'settime_21:00_{habit_id}'),
             InlineKeyboardButton("😴 22:00", callback_data=f'settime_22:00_{habit_id}')],
            [InlineKeyboardButton("🕒 Custom Time", callback_data=f'customtime_{habit_id}')],
            [InlineKeyboardButton("⬅ Back", callback_data=f'remind_setup_{habit_id}')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Get current time if set
        current_time = context.user_data.get(f'time_{habit_id}', 'Not set')
        
        await query.edit_message_text(
            "⏰ **Set Reminder Time**\n\n"
            f"Current time: {current_time}\n\n"
            "Choose when you want to be reminded:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    elif query.data.startswith('settime_'):
        parts = query.data.split('_')
        time_str = parts[1]
        habit_id = parts[2]
        
        # Save the selected time
        context.user_data[f'time_{habit_id}'] = time_str
        
        # Go back to reminder setup
        try:
            await query.edit_message_text(
                f"✅ Reminder time set to {time_str}!\n\n"
                "Going back to settings..."
            )
        except Exception as e:
            # If message hasn't changed, answer the callback to remove loading state
            await query.answer()
        
        # Show the reminder setup menu
        await asyncio.sleep(1)  # Brief pause for better UX
        
        # Get habit info
        habit_result = supabase.table('habits').select("name").eq('id', habit_id).execute()
        habit_name = habit_result.data[0]['name'] if habit_result.data else "Habit"
        
        # Get current settings
        days = context.user_data.get(f'schedule_{habit_id}', [])
        time = context.user_data.get(f'time_{habit_id}', 'Not set')
        
        keyboard = [
            [InlineKeyboardButton("📅 Choose Days", callback_data=f'days_{habit_id}')],
            [InlineKeyboardButton("⏰ Set Time", callback_data=f'time_{habit_id}')],
            [InlineKeyboardButton("😑 Fallback Reminder", callback_data=f'fallback_{habit_id}')],
            [InlineKeyboardButton("🔔 Toggle On/Off", callback_data=f'toggle_{habit_id}')],
            [InlineKeyboardButton("💾 Save Settings", callback_data=f'save_reminder_{habit_id}')],
            [InlineKeyboardButton("⬅ Back", callback_data=f'view_habit_{habit_id}')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.reply_text(
            f"🔔 **Reminder Settings**\n\n"
            f"Habit: {habit_name}\n\n"
            f"📅 Days: {', '.join(days) if days else 'Not set'}\n"
            f"⏰ Time: {time}\n\n"
            "Choose an option:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    elif query.data.startswith('customtime_'):
        habit_id = query.data.replace('customtime_', '')
        context.user_data[f'setting_time_{habit_id}'] = True
        
        await query.edit_message_text(
            "⏰ **Custom Time**\n\n"
            "Please send the time in 24-hour format (HH:MM).\n\n"
            "Examples:\n"
            "• `09:30` for 9:30 AM\n"
            "• `15:45` for 3:45 PM\n"
            "• `23:15` for 11:15 PM",
            parse_mode='Markdown'
        )
        
    elif query.data.startswith('fallback_'):
        habit_id = query.data.replace('fallback_', '')
        
        keyboard = [
            [InlineKeyboardButton("✅ Enable Fallback", callback_data=f'enable_fallback_{habit_id}')],
            [InlineKeyboardButton("❌ Disable Fallback", callback_data=f'disable_fallback_{habit_id}')],
            [InlineKeyboardButton("⬅ Back", callback_data=f'remind_setup_{habit_id}')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🚑 **Fallback Reminder**\n\n"
            "Get a final reminder if you haven't logged your habit by a certain time.\n\n"
            "Example: If you forget to log by 11 PM, get a \"Don't lose your streak!\" alert.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    elif query.data.startswith('save_reminder_'):
        habit_id = query.data.replace('save_reminder_', '')
        user_id = str(query.from_user.id)
        
        # Get all settings from context
        days = context.user_data.get(f'schedule_{habit_id}', ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'])
        reminder_time = context.user_data.get(f'time_{habit_id}', '20:00')
        fallback_enabled = context.user_data.get(f'fallback_enabled_{habit_id}', False)
        fallback_time = context.user_data.get(f'fallback_time_{habit_id}', '23:00')
        
        try:
            # Check if schedule exists
            existing = supabase.table('habit_schedules').select("id").eq('habit_id', habit_id).execute()
            
            schedule_data = {
                'user_id': user_id,
                'habit_id': habit_id,
                'days': days,
                'reminder_time': reminder_time,
                'fallback_enabled': fallback_enabled,
                'fallback_time': fallback_time if fallback_enabled else None
            }
            
            if existing.data:
                # Update existing
                supabase.table('habit_schedules').update(schedule_data).eq('habit_id', habit_id).execute()
            else:
                # Create new
                supabase.table('habit_schedules').insert(schedule_data).execute()
            
            # Get habit name
            habit_result = supabase.table('habits').select("name").eq('id', habit_id).execute()
            habit_name = habit_result.data[0]['name'] if habit_result.data else "your habit"
            
            fallback_msg = f"\n🚑 Fallback reminder at {fallback_time}" if fallback_enabled else ""
            
            await query.edit_message_text(
                f"✅ **Reminder Set!**\n\n"
                f"Habit: {habit_name}\n"
                f"📅 Days: {', '.join(days)}\n"
                f"🕓 Time: {reminder_time}{fallback_msg}\n\n"
                f"You'll be reminded at {reminder_time} on {', '.join(days)}.",
                parse_mode='Markdown'
            )
            
            # Clean up context
            for key in list(context.user_data.keys()):
                if habit_id in key:
                    context.user_data.pop(key, None)
                    
        except Exception as e:
            await query.edit_message_text("❌ Error saving reminder settings. Please try again.")
            print(f"Error saving reminder: {e}")
    
    elif query.data.startswith('save_schedule_'):
        habit_id = query.data.replace('save_schedule_', '')
        schedule_key = f'schedule_{habit_id}'
        selected_days = context.user_data.get(schedule_key, [])
        
        if not selected_days:
            await query.edit_message_text("❌ Please select at least one day!")
            return
        
        try:
            # Update habit schedule
            supabase.table('habits').update({
                'schedule_days': selected_days
            }).eq('id', habit_id).execute()
            
            await query.edit_message_text(
                f"✅ Schedule updated!\n\n"
                f"This habit is now scheduled for: {', '.join(selected_days)}"
            )
            
            # Clean up context
            context.user_data.pop(schedule_key, None)
            
        except Exception as e:
            await query.edit_message_text("❌ Error updating schedule. Please try again.")
            print(f"Error saving schedule: {e}")
    
    elif query.data.startswith('enable_fallback_'):
        habit_id = query.data.replace('enable_fallback_', '')
        context.user_data[f'setting_fallback_time_{habit_id}'] = True
        
        await query.edit_message_text(
            "🚑 **Set Fallback Time**\n\n"
            "When should we send the final reminder?\n\n"
            "Please send the time in 24-hour format (HH:MM).\n\n"
            "Recommended: 23:00 (11 PM)",
            parse_mode='Markdown'
        )
    
    elif query.data.startswith('disable_fallback_'):
        habit_id = query.data.replace('disable_fallback_', '')
        context.user_data[f'fallback_enabled_{habit_id}'] = False
        context.user_data.pop(f'fallback_time_{habit_id}', None)
        
        keyboard = [[InlineKeyboardButton("⬅ Back to Settings", callback_data=f'remind_setup_{habit_id}')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "✅ Fallback reminder disabled.",
            reply_markup=reply_markup
        )
    
    elif query.data == 'settings_language_more':
        keyboard = [
            [InlineKeyboardButton("🇸🇦 العربية", callback_data='set_lang_ar'),
             InlineKeyboardButton("🇮🇳 हिन्दी", callback_data='set_lang_hi')],
            [InlineKeyboardButton("🇹🇷 Türkçe", callback_data='set_lang_tr'),
             InlineKeyboardButton("🇳🇱 Nederlands", callback_data='set_lang_nl')],
            [InlineKeyboardButton("🇵🇱 Polski", callback_data='set_lang_pl'),
             InlineKeyboardButton("🇸🇪 Svenska", callback_data='set_lang_sv')],
            [InlineKeyboardButton("🇺🇦 Українська", callback_data='set_lang_uk'),
             InlineKeyboardButton("🇨🇿 Čeština", callback_data='set_lang_cs')],
            [InlineKeyboardButton("🇩🇰 Dansk", callback_data='set_lang_da'),
             InlineKeyboardButton("🇫🇮 Suomi", callback_data='set_lang_fi')],
            [InlineKeyboardButton("🇭🇺 Magyar", callback_data='set_lang_hu'),
             InlineKeyboardButton("🇷🇴 Română", callback_data='set_lang_ro')],
            [InlineKeyboardButton("🇧🇬 Български", callback_data='set_lang_bg')],
            [InlineKeyboardButton("⬅ Back", callback_data='settings_language')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🌐 Select your language:",
            reply_markup=reply_markup
        )
    
    elif query.data == 'settings_language':
        # Create a multi-page language selection
        keyboard = [
            [InlineKeyboardButton("🇬🇧 English", callback_data='set_lang_en'),
             InlineKeyboardButton("🇪🇸 Español", callback_data='set_lang_es')],
            [InlineKeyboardButton("🇫🇷 Français", callback_data='set_lang_fr'),
             InlineKeyboardButton("🇩🇪 Deutsch", callback_data='set_lang_de')],
            [InlineKeyboardButton("🇮🇹 Italiano", callback_data='set_lang_it'),
             InlineKeyboardButton("🇵🇹 Português", callback_data='set_lang_pt')],
            [InlineKeyboardButton("🇷🇺 Русский", callback_data='set_lang_ru'),
             InlineKeyboardButton("🇨🇳 中文", callback_data='set_lang_zh')],
            [InlineKeyboardButton("🇯🇵 日本語", callback_data='set_lang_ja'),
             InlineKeyboardButton("🇰🇷 한국어", callback_data='set_lang_ko')],
            [InlineKeyboardButton("➡ More Languages", callback_data='settings_language_more')],
            [InlineKeyboardButton("⬅ Back", callback_data='settings_back')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🌐 Select your language / Seleccione su idioma / Choisissez votre langue:",
            reply_markup=reply_markup
        )
    
    elif query.data.startswith('set_lang_'):
        lang = query.data.replace('set_lang_', '')
        user_id = str(query.from_user.id)
        
        try:
            # Update language in profile
            profile_result = supabase.table('profiles').select("data").eq('user_id', user_id).execute()
            profile_data = profile_result.data[0]['data']
            profile_data['language'] = lang
            
            supabase.table('profiles').update({
                'data': profile_data
            }).eq('user_id', user_id).execute()
            
            lang_names = {
                'en': 'English', 'es': 'Español', 'fr': 'Français', 'de': 'Deutsch',
                'it': 'Italiano', 'pt': 'Português', 'ru': 'Русский', 'zh': '中文',
                'ja': '日本語', 'ko': '한국어', 'ar': 'العربية', 'hi': 'हिन्दी',
                'tr': 'Türkçe', 'nl': 'Nederlands', 'pl': 'Polski', 'sv': 'Svenska',
                'uk': 'Українська', 'cs': 'Čeština', 'da': 'Dansk', 'fi': 'Suomi',
                'hu': 'Magyar', 'ro': 'Română', 'bg': 'Български'
            }
            await query.edit_message_text(f"✅ Language changed to {lang_names.get(lang, lang)}!")
            
        except Exception as e:
            await query.edit_message_text("❌ Error updating language.")
            print(f"Error setting language: {e}")
    
    elif query.data.startswith('settings_timezone'):
        await query.edit_message_text(
            "🕒 **Set Timezone**\n\n"
            "Please send your timezone in format:\n"
            "• `Europe/London`\n"
            "• `America/New_York`\n"
            "• `Asia/Tokyo`\n\n"
            "Common timezones:\n"
            "• UTC\n"
            "• Europe/London\n"
            "• America/New_York\n"
            "• America/Los_Angeles\n"
            "• Asia/Singapore",
            parse_mode='Markdown'
        )
        context.user_data['setting_timezone'] = True
    
    elif query.data == 'settings_back':
        # Go back to main settings
        user_id = str(query.from_user.id)
        try:
            # Retrieve user profile
            profile_result = supabase.table('profiles').select("data").eq('user_id', user_id).execute()
            if not profile_result.data:
                await query.edit_message_text("❌ Profile not found. Please use /start first.")
                return
            
            profile_data = profile_result.data[0]['data']
            language = profile_data.get('language', 'en')
            timezone = profile_data.get('timezone', 'UTC')
            
            # Create inline keyboard for settings
            keyboard = [
                [InlineKeyboardButton("🌐 Change Language", callback_data='settings_language')],
                [InlineKeyboardButton("🕒 Change Timezone", callback_data='settings_timezone')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            message = "🔧 **Settings**\n\n"
            message += f"🌐 Language: {language}\n"
            message += f"🕒 Timezone: {timezone}\n\n"
            message += "Choose what you'd like to change:"
            
            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            print(f"Error in settings_back: {e}")
            await query.edit_message_text("❌ Error loading settings.")
    
    elif query.data.startswith('complete_'):
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
    
    # Show tier selection
    keyboard = [
        [InlineKeyboardButton("🌟 Basic (£0.50/month)", callback_data='upgrade_basic')],
        [InlineKeyboardButton("💪 Coach (£2.50/month)", callback_data='upgrade_coach')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = "🚀 Choose Your Plan!\n\n"
    message += "🌟 **Basic Premium** (£0.50/month)\n"
    message += "• Unlimited habits\n"
    message += "• Advanced statistics\n"
    message += "• Priority support\n"
    message += "• Export your data\n\n"
    message += "💪 **Coach Tier** (£2.50/month)\n"
    message += "• Everything in Basic, plus:\n"
    message += "• 🤖 AI Habit Coach - Get personalized advice\n"
    message += "• Unlimited AI coaching sessions\n"
    message += "• Deep habit analysis\n"
    message += "• Personalized motivation\n\n"
    message += "❌ Cancel anytime\n\n"
    message += "Select your preferred plan:"
    
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

# Manage settings
async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    
    try:
        # Retrieve user profile
        profile_result = supabase.table('profiles').select("data").eq('user_id', user_id).execute()
        if not profile_result.data:
            await update.message.reply_text("❌ Profile not found. Please use /start first.")
            return
        
        profile_data = profile_result.data[0]['data']
        language = profile_data.get('language', 'en')
        timezone = profile_data.get('timezone', 'UTC')
        
        # Create inline keyboard for settings
        keyboard = [
            [InlineKeyboardButton("🌐 Change Language", callback_data='settings_language')],
            [InlineKeyboardButton("🕒 Change Timezone", callback_data='settings_timezone')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = "🔧 **Settings**\n\n"
        message += f"🌐 Language: {language}\n"
        message += f"🕒 Timezone: {timezone}\n\n"
        message += "Choose what you'd like to change:"
        
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        print(f"Error fetching settings: {e}")
        await update.message.reply_text("❌ Error fetching settings. Please try again.")


# AI Habit Coach (Premium Feature)
async def coach(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    
    # Check if user has coach tier
    try:
        user_result = supabase.table('users').select("subscription_tier, coach_sessions_used, coach_sessions_reset_at").eq('user_id', user_id).execute()
        
        if not user_result.data:
            await update.message.reply_text("❌ Please use /start first to set up your account.")
            return
            
        user_data = user_result.data[0]
        subscription_tier = user_data['subscription_tier']
        sessions_used = user_data['coach_sessions_used'] or 0
        reset_date = user_data['coach_sessions_reset_at']
        
        if subscription_tier != 'coach':
            keyboard = [[InlineKeyboardButton("💪 Upgrade to Coach Tier", callback_data='upgrade_coach')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "🤖 **AI Habit Coach** (Coach Tier Feature)\n\n"
                "Get personalized coaching from our AI to help you:\n"
                "• Understand why you're breaking streaks\n"
                "• Build better discipline\n"
                "• Get motivational support\n"
                "• Personalized habit recommendations\n\n"
                "Upgrade to Coach tier (£2.50/month) to unlock this feature!",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return
        
        # Check daily limit
        today = datetime.now().date()
        if reset_date and str(reset_date) < str(today):
            # Reset daily counter
            sessions_used = 0
            supabase.table('users').update({
                'coach_sessions_used': 0,
                'coach_sessions_reset_at': today.isoformat()
            }).eq('user_id', user_id).execute()
        
        if sessions_used >= DAILY_COACH_LIMIT:
            await update.message.reply_text(
                f"⏰ **Daily Limit Reached**\n\n"
                f"You've used all {DAILY_COACH_LIMIT} coaching sessions for today.\n"
                f"Your sessions will reset tomorrow!\n\n"
                f"💡 Tip: Make your questions count by being specific about your habit challenges.",
                parse_mode='Markdown'
            )
            return
        
        # For premium users - show coach interface
        if context.args and len(context.args) > 0:
            # User provided a question
            question = ' '.join(context.args)
            
            # Check if OpenAI API key is configured
            if not OPENAI_API_KEY:
                await update.message.reply_text(
                    "⚠️ AI Coach is not configured yet. Using helpful tips instead:\n\n"
                    "Ask about breaking streaks, building discipline, or staying motivated!"
                )
                return
            
            # First, validate if this is a habit-related question
            validation_prompt = (
                "You are a filter that determines if a question is related to habits, discipline, motivation, or personal development. "
                "Respond with only 'YES' if the question is about habits, building discipline, motivation, productivity, breaking bad habits, "
                "forming good habits, or similar self-improvement topics. Respond with 'NO' for anything else like general knowledge, "
                "technical questions, entertainment, or unrelated topics."
            )
            
            try:
                # Validate the question first
                client = openai.OpenAI(api_key=OPENAI_API_KEY)
                validation = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": validation_prompt},
                        {"role": "user", "content": question}
                    ],
                    max_tokens=10,
                    temperature=0
                )
                
                is_valid = validation.choices[0].message.content.strip().upper() == 'YES'
                
                if not is_valid:
                    await update.message.reply_text(
                        "🚫 **Off-Topic Question**\n\n"
                        "I'm your habit coach, and I can only help with:\n"
                        "• Building better habits\n"
                        "• Breaking bad habits\n"
                        "• Staying motivated\n"
                        "• Understanding discipline\n"
                        "• Overcoming procrastination\n\n"
                        "Please ask me something related to habits or personal development!",
                        parse_mode='Markdown'
                    )
                    return
                
                # Show typing indicator while AI processes
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
                
                # Get user's habit data for context
                habits_result = supabase.table('habits').select("name").eq('user_id', user_id).eq('is_active', True).execute()
                habit_names = [h['name'] for h in habits_result.data] if habits_result.data else []
                
                # Create context-aware prompt
                system_prompt = (
                    "You are an expert habit coach helping users build better habits. "
                    "Be supportive, practical, and concise. Give actionable advice. "
                    "Use emojis sparingly for emphasis. Format with markdown. "
                    "Focus only on habits, discipline, motivation, and personal development."
                )
                
                user_context = f"User's current habits: {', '.join(habit_names)}" if habit_names else "User has no habits yet"
                
                # Call OpenAI API for the actual coaching response
                completion = client.chat.completions.create(
                    model="gpt-4-turbo-preview",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"{user_context}\n\nQuestion: {question}"}
                    ],
                    max_tokens=500,
                    temperature=0.7
                )
                
                response_text = completion.choices[0].message.content
                
                # Calculate approximate tokens used (rough estimate)
                tokens_used = len(question.split()) * 1.3 + len(response_text.split()) * 1.3
                
                # Log the conversation
                try:
                    supabase.table('coach_conversations').insert({
                        'user_id': user_id,
                        'question': question,
                        'response': response_text,
                        'tokens_used': int(tokens_used)
                    }).execute()
                except Exception as log_error:
                    print(f"Error logging conversation: {log_error}")
                
                # Add coach prefix
                response = f"🤖 **AI Coach says:**\n\n{response_text}"
                
            except Exception as e:
                print(f"OpenAI API error: {e}")
                # Fallback to helpful response
                response = (
                    "⚠️ I'm having trouble connecting to my AI brain right now.\n\n"
                    "Here's a quick tip: Start small with your habits! "
                    "Even 2 minutes a day is better than nothing. "
                    "Consistency beats perfection every time."
                )
            
            await update.message.reply_text(response, parse_mode='Markdown')
        else:
            # No question provided
            await update.message.reply_text(
                "🤖 **AI Habit Coach**\n\n"
                "I'm here to help you build better habits! Ask me anything:\n\n"
                "Examples:\n"
                "• /coach Why am I breaking my streak?\n"
                "• /coach How can I build discipline for reading?\n"
                "• /coach I feel unmotivated today\n\n"
                "What would you like help with?",
                parse_mode='Markdown'
            )
            
    except Exception as e:
        print(f"Error in coach: {e}")
        await update.message.reply_text("❌ Error accessing AI Coach. Please try again.")


# Remind command - Set up reminders
async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    
    try:
        # Check if user is premium (free users get default 8pm only)
        user_result = supabase.table('users').select("subscription_tier").eq('user_id', user_id).execute()
        subscription_tier = user_result.data[0]['subscription_tier'] if user_result.data else 'free'
        
        if subscription_tier == 'free':
            await update.message.reply_text(
                "🔔 **Reminder Settings** (Free Plan)\n\n"
                "Free users get daily reminders at 8:00 PM for all habits.\n\n"
                "✨ Upgrade to Premium to:\n"
                "• Set custom reminder times per habit\n"
                "• Choose specific days for each habit\n"
                "• Enable streak-saving fallback reminders\n\n"
                "Use /upgrade to unlock custom reminders!",
                parse_mode='Markdown'
            )
            return
            
        # Get user's habits
        habits_result = supabase.table('habits').select("*").eq('user_id', user_id).eq('is_active', True).execute()
        
        if not habits_result.data:
            await update.message.reply_text("📋 You don't have any habits yet! Use /addhabit to create one.")
            return
        
        # Create inline keyboard with habits
        keyboard = []
        for habit in habits_result.data:
            # Check if habit has existing schedule
            schedule_result = supabase.table('habit_schedules').select("reminder_time").eq('habit_id', habit['id']).execute()
            has_reminder = "🔔" if schedule_result.data else ""
            
            keyboard.append([InlineKeyboardButton(
                f"{has_reminder} {habit['name']}", 
                callback_data=f"remind_setup_{habit['id']}"
            )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🔔 **Set Reminders**\n\n"
            "Which habit would you like to set a reminder for?\n\n"
            "🔔 = Has reminder set",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        await update.message.reply_text("❌ Error loading habits. Please try again.")
        print(f"Error in remind: {e}")

# Pause habit (vacation mode)
async def pause_habit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    
    # Check if dates provided
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "📅 **Pause a Habit**\n\n"
            "Usage: `/pause [start_date] [end_date]`\n"
            "Example: `/pause 2024-12-25 2025-01-02`\n\n"
            "This will pause all your habits during this period.",
            parse_mode='Markdown'
        )
        return
    
    try:
        start_date = datetime.strptime(context.args[0], '%Y-%m-%d').date()
        end_date = datetime.strptime(context.args[1], '%Y-%m-%d').date()
        
        if start_date > end_date:
            await update.message.reply_text("❌ Start date must be before end date!")
            return
        
        # Check maximum 3 weeks
        duration = (end_date - start_date).days
        if duration > 21:  # 3 weeks
            await update.message.reply_text(
                "❌ Pause period cannot exceed 3 weeks (21 days)!\n\n"
                "For longer breaks, consider deactivating habits instead."
            )
            return
        
        # Get all user habits
        habits_result = supabase.table('habits').select("id").eq('user_id', user_id).eq('is_active', True).execute()
        
        # Create pause for each habit
        for habit in habits_result.data:
            supabase.table('habit_pauses').insert({
                'habit_id': habit['id'],
                'user_id': user_id,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'reason': 'vacation'
            }).execute()
        
        await update.message.reply_text(
            f"✅ All habits paused from {start_date} to {end_date}!\n\n"
            "Your streaks will be preserved during this period. 🏖️"
        )
        
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid date format! Use YYYY-MM-DD\n"
            "Example: `/pause 2024-12-25 2025-01-02`",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text("❌ Error setting pause period. Please try again.")
        print(f"Error in pause_habit: {e}")

# List commands
async def list_commands(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    
    # Check user subscription tier
    try:
        user_result = supabase.table('users').select("subscription_tier").eq('user_id', user_id).execute()
        subscription_tier = user_result.data[0]['subscription_tier'] if user_result.data else 'free'
        
        message = "📋 **Available Commands**\n\n"
        message += "🎆 **Habit Tracking**\n"
        message += "/addhabit - Add a new habit to track\n"
        message += "/habits - View all your habits\n"
        message += "/complete - Mark a habit as done\n"
        message += "/remind - Set up habit reminders\n"
        message += "/pause - Pause habits for vacation\n\n"
        
        message += "📊 **Progress & Stats**\n"
        message += "/stats - View your XP, level & stats\n\n"
        
        if subscription_tier == 'coach':
            message += "💪 **Coach Tier Features**\n"
            message += "/coach - AI Habit Coach\n\n"
        elif subscription_tier == 'basic':
            message += "🌟 **Basic Premium Features**\n"
            message += "(Unlimited habits enabled)\n\n"
        
        message += "🆙 **Other Commands**\n"
        message += "/start - Welcome message\n"
        message += "/settings - Manage your settings\n"
        message += "/commands - Show this list\n"
        
        if subscription_tier == 'free':
            message += "/upgrade - Get premium features\n\n"
            message += "🎆 You're using the free version (3 habits max)"
        elif subscription_tier == 'basic':
            message += "/upgrade - Upgrade to Coach tier\n\n"
            message += "🌟 You're a Basic Premium member!"
        else:
            message += "\n💪 You're a Coach tier member!"
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
    except Exception as e:
        # Fallback message if database check fails
        message = "📋 **Available Commands**\n\n"
        message += "/start - Begin or restart\n"
        message += "/addhabit - Add a new habit\n"
        message += "/habits - View your habits\n"
        message += "/complete - Mark habit as done\n"
        message += "/stats - Check your progress\n"
        message += "/upgrade - Get premium\n"
        message += "/commands - Show this list\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')


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
    app.add_handler(CommandHandler("commands", list_commands))
    app.add_handler(CommandHandler("settings", settings))
    app.add_handler(CommandHandler("coach", coach))
    app.add_handler(CommandHandler("remind", remind))
    app.add_handler(CommandHandler("pause", pause_habit))
    
    # Message handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Callback query handler
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # Note: Job Queue doesn't work well with webhooks
    # Use the separate send_reminders.py script with a cron job instead
    # See send_reminders.py for the reminder implementation
    
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
