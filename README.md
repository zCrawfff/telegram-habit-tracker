# Telegram Habit Tracker Bot

A gamified habit tracking bot for Telegram with XP, leveling, achievements, and premium features.

## Features

- 🎯 Track up to 3 habits (free) or unlimited (premium)
- 🏆 XP and leveling system
- 🔥 Streak tracking
- 🌍 Multi-language support (13 languages)
- 💎 Premium tier with Stripe integration
- 📊 Dashboard with visual stats
- 🎮 Gamified rewards and achievements

## Prerequisites

1. **Telegram Bot Token** - Get from [@BotFather](https://t.me/botfather)
2. **Supabase Account** - For database ([supabase.com](https://supabase.com))
3. **Stripe Account** - For payments ([stripe.com](https://stripe.com))
4. **Python 3.10+** installed locally

## Setup Instructions

### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd telegram-habit-tracker
```

### 2. Install Dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure Environment

1. Copy `.env.template` to `.env`:
   ```bash
   cp .env.template .env
   ```

2. Fill in your credentials in `.env`:
   - `TELEGRAM_BOT_TOKEN`: From BotFather
   - `SUPABASE_URL`: Your Supabase project URL
   - `SUPABASE_KEY`: Your Supabase anon/public key
   - `STRIPE_SECRET_KEY`: Your Stripe secret key
   - `STRIPE_PRICE_ID`: Your Stripe price ID for premium
   - `STRIPE_WEBHOOK_SECRET`: From Stripe webhook settings

### 4. Supabase Setup

Create these tables in your Supabase project:

```sql
-- Users table
CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    is_premium BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Profiles table
CREATE TABLE profiles (
    user_id TEXT PRIMARY KEY,
    data JSONB,
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### 5. Stripe Setup

1. Create a product in Stripe Dashboard
2. Set up a recurring price (e.g., £0.50/month)
3. Add webhook endpoint: `https://your-domain.com/stripe-webhook`
4. Select event: `checkout.session.completed`

### 6. Local Testing

```bash
python bot.py
```

## Deployment

### Option 1: Deploy to Render

1. Push your code to GitHub
2. Connect to [Render](https://render.com)
3. Create new Web Service
4. Connect your GitHub repo
5. Set environment variables
6. Deploy!

### Option 2: Deploy to Railway

1. Push your code to GitHub
2. Go to [Railway](https://railway.app)
3. Create new project from GitHub
4. Add environment variables
5. Deploy!

## Bot Commands

- `/start` - Welcome message and onboarding
- `/addhabit` - Add a new habit
- `/habits` - View your habits
- `/stats` - View your XP and level
- `/dashboard` - Visual progress dashboard
- `/achievements` - View earned achievements
- `/upgrade` - Upgrade to premium
- `/deleteaccount` - Delete your account
- `/cancelpremium` - Cancel premium subscription

## Support

For issues or questions, please open an issue on GitHub.

## License

MIT License
