#!/usr/bin/env python3
"""
Utility script to manually update a user's subscription tier to coach
Usage: python fix_coach_tier.py USER_ID
"""

import os
import sys
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

# Initialize Supabase
supabase = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

def fix_coach_tier(user_id):
    """Update a specific user to coach tier"""
    try:
        # Check if user exists
        user_result = supabase.table('users').select("*").eq('user_id', user_id).execute()
        
        if not user_result.data:
            print(f"❌ User {user_id} not found in database")
            return False
        
        current_user = user_result.data[0]
        print(f"Current user data: {current_user}")
        
        # Update to coach tier
        update_result = supabase.table('users').update({
            'is_premium': True,
            'subscription_tier': 'coach'
        }).eq('user_id', user_id).execute()
        
        print(f"✅ Successfully updated user {user_id} to coach tier")
        print(f"Updated data: {update_result.data}")
        return True
        
    except Exception as e:
        print(f"❌ Error updating user: {e}")
        return False

def list_premium_users():
    """List all premium users and their tiers"""
    try:
        premium_users = supabase.table('users').select("*").eq('is_premium', True).execute()
        
        print("\n📊 Premium Users:")
        print("-" * 50)
        for user in premium_users.data:
            print(f"User ID: {user['user_id']}")
            print(f"  Premium: {user['is_premium']}")
            print(f"  Tier: {user.get('subscription_tier', 'not set')}")
            print(f"  Created: {user['created_at']}")
            print("-" * 50)
            
    except Exception as e:
        print(f"❌ Error listing users: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        user_id = sys.argv[1]
        print(f"Fixing coach tier for user: {user_id}")
        fix_coach_tier(user_id)
    else:
        print("Usage: python fix_coach_tier.py USER_ID")
        print("\nListing all premium users...")
        list_premium_users()
