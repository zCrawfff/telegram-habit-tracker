#!/usr/bin/env python3

print("🤖 AI Coach Cost Estimator\n")

# Model pricing (per 1K tokens)
models = {
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006, "name": "GPT-4o Mini (Cheapest!)"},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015, "name": "GPT-3.5 Turbo"},
    "gpt-4o": {"input": 0.005, "output": 0.015, "name": "GPT-4o"},
    "gpt-4": {"input": 0.03, "output": 0.06, "name": "GPT-4"}
}

# Average tokens per coach interaction
avg_input_tokens = 150  # Question + context
avg_output_tokens = 300  # Coach response

# Daily limit per user
daily_limit = 10

print("📊 Token Usage per Coach Session:")
print(f"• Average input: ~{avg_input_tokens} tokens")
print(f"• Average output: ~{avg_output_tokens} tokens")
print(f"• Total per session: ~{avg_input_tokens + avg_output_tokens} tokens\n")

print("💰 Cost Comparison by Model:\n")

for model_key, pricing in models.items():
    # Calculate cost per session
    input_cost = (avg_input_tokens / 1000) * pricing["input"]
    output_cost = (avg_output_tokens / 1000) * pricing["output"]
    session_cost = input_cost + output_cost
    
    # Calculate daily cost per user (at max usage)
    daily_cost = session_cost * daily_limit
    
    # Calculate monthly cost per user (at max usage every day)
    monthly_cost = daily_cost * 30
    
    print(f"**{pricing['name']}**")
    print(f"• Per session: ${session_cost:.4f}")
    print(f"• Per user per day (max): ${daily_cost:.3f}")
    print(f"• Per user per month (max): ${monthly_cost:.2f}")
    print()

print("📈 Cost Scenarios with gpt-4o-mini (cheapest):\n")

# Scenarios with gpt-4o-mini
mini_pricing = models["gpt-4o-mini"]
session_cost = ((avg_input_tokens / 1000) * mini_pricing["input"]) + ((avg_output_tokens / 1000) * mini_pricing["output"])

scenarios = [
    {"users": 10, "sessions_per_day": 5, "name": "Small (10 users, moderate usage)"},
    {"users": 50, "sessions_per_day": 3, "name": "Medium (50 users, light usage)"},
    {"users": 100, "sessions_per_day": 5, "name": "Large (100 users, moderate usage)"},
    {"users": 500, "sessions_per_day": 2, "name": "Very Large (500 users, light usage)"}
]

for scenario in scenarios:
    daily_cost = scenario["users"] * scenario["sessions_per_day"] * session_cost
    monthly_cost = daily_cost * 30
    
    print(f"{scenario['name']}:")
    print(f"• Daily cost: ${daily_cost:.2f}")
    print(f"• Monthly cost: ${monthly_cost:.2f}")
    print()

print("💡 Cost Optimization Tips:")
print("• The bot already limits users to 10 sessions/day")
print("• Using gpt-4o-mini (3x cheaper than gpt-3.5-turbo)")
print("• Short, focused responses keep output tokens low")
print("• Question validation prevents wasted API calls")
print("\n✅ With gpt-4o-mini, even 100 active users would cost ~$10-20/month!")
