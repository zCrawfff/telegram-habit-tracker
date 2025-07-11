#!/usr/bin/env python3

import os
import json
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

print("🔍 Testing OpenAI API Key...")
print(f"API Key present: {bool(OPENAI_API_KEY)}")
print(f"API Key length: {len(OPENAI_API_KEY) if OPENAI_API_KEY else 0}")
print(f"API Key preview: {OPENAI_API_KEY[:8]}...{OPENAI_API_KEY[-4:] if OPENAI_API_KEY else 'None'}")

# Test with curl command instead of Python library
import subprocess

if OPENAI_API_KEY:
    # Prepare the curl command
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": "Say 'hello'"}],
        "max_tokens": 5
    }
    
    # Use curl to test the API
    curl_command = [
        'curl', '-s', '-X', 'POST',
        'https://api.openai.com/v1/chat/completions',
        '-H', f'Authorization: Bearer {OPENAI_API_KEY}',
        '-H', 'Content-Type: application/json',
        '-d', json.dumps(data)
    ]
    
    print("\n📡 Testing API connection...")
    try:
        result = subprocess.run(curl_command, capture_output=True, text=True)
        response = json.loads(result.stdout) if result.stdout else {}
        
        if 'error' in response:
            print(f"❌ API Error: {response['error']['type']}")
            print(f"Message: {response['error']['message']}")
            
            # Check for specific error types
            if 'invalid_api_key' in response['error']['type']:
                print("\n⚠️  Your API key appears to be invalid!")
                print("Please check that:")
                print("1. The API key is copied correctly from OpenAI")
                print("2. There are no extra spaces or characters")
                print("3. The key hasn't been revoked")
            elif 'rate_limit' in response['error']['type']:
                print("\n⏱️ Rate limit error - but this means your API key is valid!")
                print("The error in the bot might be a temporary rate limit.")
        elif 'choices' in response:
            print("✅ API Key is valid and working!")
            print(f"Response: {response['choices'][0]['message']['content']}")
        else:
            print(f"🤔 Unexpected response: {json.dumps(response, indent=2)}")
            
    except Exception as e:
        print(f"❌ Error running test: {e}")
else:
    print("❌ No API key found in environment!")
    print("\nTo fix this:")
    print("1. Make sure your .env file contains: OPENAI_API_KEY=your-key-here")
    print("2. Get your API key from: https://platform.openai.com/api-keys")
