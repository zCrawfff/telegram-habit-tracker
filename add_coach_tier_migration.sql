-- Add coach tier support to the database
-- This migration adds subscription_tier column to track different subscription levels

-- Add subscription_tier column to users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_tier TEXT DEFAULT 'free';

-- Update existing premium users to 'basic' tier
UPDATE users SET subscription_tier = 'basic' WHERE is_premium = TRUE;

-- Add coach tier related columns
ALTER TABLE users ADD COLUMN IF NOT EXISTS coach_sessions_used INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS coach_sessions_reset_at DATE DEFAULT CURRENT_DATE;

-- Create a subscription_history table to track tier changes
CREATE TABLE IF NOT EXISTS subscription_history (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id TEXT REFERENCES users(user_id) ON DELETE CASCADE,
    tier TEXT NOT NULL,
    stripe_price_id TEXT,
    started_at TIMESTAMP DEFAULT NOW(),
    ended_at TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Create index for subscription history
CREATE INDEX IF NOT EXISTS idx_subscription_history_user_id ON subscription_history(user_id);
CREATE INDEX IF NOT EXISTS idx_subscription_history_active ON subscription_history(is_active);

-- Create coach_conversations table to track AI interactions
CREATE TABLE IF NOT EXISTS coach_conversations (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id TEXT REFERENCES users(user_id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    response TEXT NOT NULL,
    tokens_used INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create index for coach conversations
CREATE INDEX IF NOT EXISTS idx_coach_conversations_user_id ON coach_conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_coach_conversations_created_at ON coach_conversations(created_at);
