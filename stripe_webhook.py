import os
from flask import Flask, request
import stripe
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

# Initialize services
app = Flask(__name__)
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

@app.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, os.getenv('STRIPE_WEBHOOK_SECRET')
        )
    except ValueError as e:
        print(f'⚠️  Webhook error while parsing basic request: {e}')
        return '', 400
    except stripe.error.SignatureVerificationError as e:
        print(f'⚠️  Webhook signature verification failed: {e}')
        return '', 400

    # Handle the checkout.session.completed event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        telegram_user_id = session.get('metadata', {}).get('telegram_user_id')
        tier = session.get('metadata', {}).get('tier', 'basic')  # Default to basic if not specified
        
        if telegram_user_id:
            print(f"✅ Payment received for user {telegram_user_id} - Tier: {tier}")
            
            # Update user to premium with correct tier
            try:
                supabase.table('users').update({
                    'is_premium': True,
                    'subscription_tier': tier
                }).eq('user_id', telegram_user_id).execute()
                print(f"✅ User {telegram_user_id} upgraded to {tier} tier")
            except Exception as e:
                print(f"❌ Error updating user {telegram_user_id}: {e}")
    
    return '', 200

if __name__ == '__main__':
    app.run(port=5000)
