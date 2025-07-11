#!/usr/bin/env python3

import os
import requests
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

if not OPENAI_API_KEY:
    print("❌ No OpenAI API key found in environment!")
    exit(1)

print("🔍 Checking OpenAI API Status...")
print(f"API Key: {OPENAI_API_KEY[:8]}...{OPENAI_API_KEY[-4:]}")

# Check if the API key is valid by making a simple request
headers = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json"
}

# Test with a minimal request
test_data = {
    "model": "gpt-3.5-turbo",
    "messages": [{"role": "user", "content": "Hi"}],
    "max_tokens": 5
}

try:
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=headers,
        json=test_data
    )
    
    if response.status_code == 200:
        print("✅ API Key is valid and working!")
        print("✅ GPT-3.5-turbo is accessible")
    elif response.status_code == 429:
        print("⏱️ Rate limit hit!")
        print(f"Response: {response.text}")
        
        # Check headers for rate limit info
        if 'x-ratelimit-limit-requests' in response.headers:
            print(f"\nRate Limit Info:")
            print(f"- Request Limit: {response.headers.get('x-ratelimit-limit-requests', 'N/A')}")
            print(f"- Remaining: {response.headers.get('x-ratelimit-remaining-requests', 'N/A')}")
            print(f"- Reset Time: {response.headers.get('x-ratelimit-reset-requests', 'N/A')}")
    else:
        print(f"❌ Error: {response.status_code}")
        print(f"Response: {response.text}")
        
except Exception as e:
    print(f"❌ Error making request: {e}")

print("\n📋 Recommendations:")
print("1. If you're hitting rate limits frequently, consider:")
print("   - Upgrading your OpenAI plan for higher limits")
print("   - Implementing request queuing in your bot")
print("   - Using GPT-3.5-turbo instead of GPT-4 (10x higher rate limits)")
print("\n2. Current implementation already includes:")
print("   - Automatic retry with exponential backoff")
print("   - Fallback from GPT-4 to GPT-3.5-turbo")
print("   - Daily session limits (10 per user)")
