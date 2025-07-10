#!/usr/bin/env python3
"""
Reminder sender script - Run this as a cron job every hour
Can be scheduled on Render/Railway or run via Supabase Edge Functions
"""

import os
import asyncio
from datetime import datetime, time
from dotenv import load_dotenv
from telegram import Bot
from supabase import create_client, Client
import pytz

load_dotenv()

# Environment variables
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# Initialize services
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
bot = Bot(token=TELEGRAM_BOT_TOKEN)

async def send_reminders():
    """Send reminders to users based on their schedules"""
    try:
        now = datetime.now(pytz.utc)
        current_weekday = now.strftime('%a')  # Mon, Tue, etc.
        
        print(f"Running reminder check at {now} for {current_weekday}")
        
        # Get all active habit schedules for today
        schedules = supabase.table('habit_schedules')\
            .select("*, habits(name, is_active), users(timezone)")\
            .contains('days', [current_weekday])\
            .execute()
        
        for schedule in schedules.data:
            try:
                # Skip if habit is not active
                if not schedule['habits']['is_active']:
                    continue
                
                # Check if in pause period
                pause_check = supabase.table('habit_pauses')\
                    .select("id")\
                    .eq('habit_id', schedule['habit_id'])\
                    .lte('start_date', now.date().isoformat())\
                    .gte('end_date', now.date().isoformat())\
                    .execute()
                
                if pause_check.data:
                    continue
                
                # Get user timezone
                user_tz = pytz.timezone(schedule['users']['timezone'] or 'UTC')
                local_time = now.astimezone(user_tz)
                
                # Check if it's time for main reminder
                reminder_time = datetime.strptime(schedule['reminder_time'], '%H:%M:%S').time()
                current_hour = local_time.hour
                reminder_hour = reminder_time.hour
                
                # Send if within the current hour
                if current_hour == reminder_hour:
                    # Check if already sent today
                    last_sent = schedule.get('last_sent_at')
                    if last_sent:
                        last_sent_date = datetime.fromisoformat(last_sent).date()
                        if last_sent_date == now.date():
                            continue
                    
                    # Send reminder
                    habit_name = schedule['habits']['name']
                    message = f"🔔 **Habit Reminder**\\n\\n"
                    message += f"Time to: {habit_name}\\n\\n"
                    message += "Reply /complete to mark it as done!"
                    
                    await bot.send_message(
                        chat_id=schedule['user_id'],
                        text=message,
                        parse_mode='Markdown'
                    )
                    
                    # Update last sent
                    supabase.table('habit_schedules')\
                        .update({'last_sent_at': now.isoformat()})\
                        .eq('id', schedule['id'])\
                        .execute()
                    
                    print(f"Sent reminder to {schedule['user_id']} for {habit_name}")
                
                # Check for fallback reminder
                if schedule['fallback_enabled'] and schedule['fallback_time']:
                    fallback_time = datetime.strptime(schedule['fallback_time'], '%H:%M:%S').time()
                    fallback_hour = fallback_time.hour
                    
                    if current_hour == fallback_hour:
                        # Check if habit was completed today
                        today_start = datetime.combine(now.date(), time.min)
                        completion_check = supabase.table('habit_logs')\
                            .select("id")\
                            .eq('habit_id', schedule['habit_id'])\
                            .gte('completed_at', today_start.isoformat())\
                            .execute()
                        
                        if not completion_check.data:
                            # Send fallback reminder
                            habit_name = schedule['habits']['name']
                            message = f"⚠️ **Don't lose your streak!**\\n\\n"
                            message += f"You haven't logged '{habit_name}' yet today.\\n\\n"
                            message += "Reply /complete to keep your streak alive! 🔥"
                            
                            await bot.send_message(
                                chat_id=schedule['user_id'],
                                text=message,
                                parse_mode='Markdown'
                            )
                            
                            print(f"Sent fallback reminder to {schedule['user_id']} for {habit_name}")
                
            except Exception as e:
                print(f"Error processing schedule {schedule['id']}: {e}")
                continue
                
    except Exception as e:
        print(f"Error in send_reminders: {e}")

async def send_free_user_reminders():
    """Send default 8 PM reminders to free users"""
    try:
        now = datetime.now(pytz.utc)
        
        # Get all free users
        free_users = supabase.table('users')\
            .select("user_id, timezone")\
            .eq('subscription_tier', 'free')\
            .eq('reminder_enabled', True)\
            .execute()
        
        for user in free_users.data:
            try:
                # Check if it's 8 PM in their timezone
                user_tz = pytz.timezone(user['timezone'] or 'UTC')
                local_time = now.astimezone(user_tz)
                
                if local_time.hour == 20:  # 8 PM
                    # Get user's active habits
                    habits = supabase.table('habits')\
                        .select("id, name")\
                        .eq('user_id', user['user_id'])\
                        .eq('is_active', True)\
                        .execute()
                    
                    if habits.data:
                        # Check which habits haven't been completed today
                        today_start = datetime.combine(now.date(), time.min)
                        incomplete_habits = []
                        
                        for habit in habits.data:
                            completion_check = supabase.table('habit_logs')\
                                .select("id")\
                                .eq('habit_id', habit['id'])\
                                .gte('completed_at', today_start.isoformat())\
                                .execute()
                            
                            if not completion_check.data:
                                incomplete_habits.append(habit['name'])
                        
                        if incomplete_habits:
                            message = f"🔔 **Daily Reminder** (8 PM)\\n\\n"
                            message += "You have habits to complete today:\\n\\n"
                            for habit in incomplete_habits:
                                message += f"• {habit}\\n"
                            message += "\\nUse /complete to mark them as done!"
                            
                            await bot.send_message(
                                chat_id=user['user_id'],
                                text=message,
                                parse_mode='Markdown'
                            )
                            
                            print(f"Sent free tier reminder to {user['user_id']}")
                            
            except Exception as e:
                print(f"Error sending free reminder to {user['user_id']}: {e}")
                continue
                
    except Exception as e:
        print(f"Error in send_free_user_reminders: {e}")

async def main():
    """Main function to run both reminder types"""
    await asyncio.gather(
        send_reminders(),
        send_free_user_reminders()
    )

if __name__ == '__main__':
    asyncio.run(main())
