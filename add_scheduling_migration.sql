-- Add habit scheduling and reminder features
-- This migration adds scheduling options and reminder settings

-- Create habit_schedules table for better organization
CREATE TABLE IF NOT EXISTS habit_schedules (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id TEXT REFERENCES users(user_id) ON DELETE CASCADE,
    habit_id UUID REFERENCES habits(id) ON DELETE CASCADE,
    days TEXT[] DEFAULT ARRAY['Mon', 'Tue', 'Wed', 'Thu', 'Fri'],
    reminder_time TIME DEFAULT '20:00',
    fallback_time TIME,
    fallback_enabled BOOLEAN DEFAULT FALSE,
    snooze_enabled BOOLEAN DEFAULT TRUE,
    last_sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(habit_id)
);

-- Add reminder preferences to users
ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone TEXT DEFAULT 'UTC';
ALTER TABLE users ADD COLUMN IF NOT EXISTS reminder_enabled BOOLEAN DEFAULT TRUE;

-- Create vacation/pause periods table
CREATE TABLE IF NOT EXISTS habit_pauses (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    habit_id UUID REFERENCES habits(id) ON DELETE CASCADE,
    user_id TEXT REFERENCES users(user_id) ON DELETE CASCADE,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    reason TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create reminders table for tracking sent reminders
CREATE TABLE IF NOT EXISTS reminders_sent (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id TEXT REFERENCES users(user_id) ON DELETE CASCADE,
    habit_id UUID REFERENCES habits(id) ON DELETE CASCADE,
    reminder_type TEXT NOT NULL, -- 'daily', 'streak_warning', 'comeback'
    sent_at TIMESTAMP DEFAULT NOW()
);

-- Add last seen timestamp to users for smart reminders
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMP DEFAULT NOW();

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_habit_pauses_dates ON habit_pauses(start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_habit_pauses_habit ON habit_pauses(habit_id);
CREATE INDEX IF NOT EXISTS idx_reminders_sent_user ON reminders_sent(user_id);
CREATE INDEX IF NOT EXISTS idx_reminders_sent_date ON reminders_sent(sent_at);
