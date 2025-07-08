import os
import sys
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

print(f"Supabase URL: {SUPABASE_URL[:30]}...")
print(f"Supabase Key: {SUPABASE_KEY[:30]}...\n")

try:
    from supabase import create_client, Client
    
    # Create Supabase client without options for compatibility
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    print("✅ Successfully created Supabase client!\n")
    
    # Try to query the users table
    try:
        result = supabase.table('users').select("*").limit(1).execute()
        print("✅ Users table exists!")
        print(f"Current users in database: {len(result.data)}")
    except Exception as table_error:
        if "relation" in str(table_error) and "does not exist" in str(table_error):
            print("❌ The 'users' table doesn't exist yet.")
            print("\nPlease run the SQL from supabase_schema.sql in your Supabase dashboard:")
            print("1. Go to your Supabase project")
            print("2. Click on 'SQL Editor' in the sidebar")
            print("3. Copy and paste the contents of supabase_schema.sql")
            print("4. Click 'Run'")
        else:
            print(f"❌ Table query error: {table_error}")
            
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Try reinstalling: pip3 install --upgrade supabase")
except Exception as e:
    print(f"❌ Unexpected error: {type(e).__name__}: {e}")
