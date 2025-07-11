#!/usr/bin/env python3
"""
Test script to verify OpenAI API connection and available models
"""

import os
from dotenv import load_dotenv
import openai

load_dotenv()

# Get API key
api_key = os.getenv('OPENAI_API_KEY')

if not api_key:
    print("❌ OPENAI_API_KEY not found in environment variables!")
    print("Please add it to your .env file")
    exit(1)

print(f"✅ API Key found: {api_key[:10]}...")

# Initialize client
client = openai.OpenAI(api_key=api_key)

# Test different models
models_to_test = ['gpt-4', 'gpt-4-turbo-preview', 'gpt-3.5-turbo']

for model in models_to_test:
    print(f"\n🧪 Testing model: {model}")
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'Hello, I work!' in 5 words or less."}
            ],
            max_tokens=20,
            temperature=0
        )
        print(f"✅ {model} works! Response: {response.choices[0].message.content}")
    except Exception as e:
        print(f"❌ {model} failed: {type(e).__name__}: {str(e)}")

# List available models
print("\n📋 Listing available models...")
try:
    models = client.models.list()
    gpt_models = [m.id for m in models.data if 'gpt' in m.id.lower()]
    print(f"Available GPT models: {', '.join(sorted(gpt_models)[:10])}...")
except Exception as e:
    print(f"❌ Failed to list models: {e}")
