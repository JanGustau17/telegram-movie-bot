import firebase_admin
from firebase_admin import credentials, db
import os
import json
import base64

# Firebase initialization flag
_firebase_initialized = False

def init_firebase():
    """Initializes Firebase app if it hasn't been initialized already."""
    global _firebase_initialized
    if _firebase_initialized:
        print("Firebase already initialized.")
        return

    try:
        # Check for FIREBASE_CRED_BASE64 and FIREBASE_DB_URL environment variables
        firebase_credentials_base64_str = os.getenv("FIREBASE_CRED_BASE64")
        database_url = os.getenv("FIREBASE_DB_URL") # Confirmed from your prompt

        if firebase_credentials_base64_str and database_url:
            print("Found base64 encoded Firebase credentials.")
            # Decode the base64 string
            decoded_credentials_bytes = base64.b64decode(firebase_credentials_base64_str)
            # Convert bytes to string, then load as JSON
            cred_dict = json.loads(decoded_credentials_bytes.decode('utf-8'))
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred, {
                'databaseURL': database_url
            })
            print("Firebase initialized successfully from base64 environment variable.")
            _firebase_initialized = True
        else:
            print("Firebase environment variables (FIREBASE_CRED_BASE64, FIREBASE_DB_URL) not found or incomplete.")
            print("Attempting to initialize Firebase from local 'serviceAccountKey.json' (for local development)...")
            # Fallback for local development if .env is missing or for explicit path
            # For local testing, ensure 'serviceAccountKey.json' is in the same directory as this script.
            # You should only have serviceAccountKey.json locally, NOT committed to Heroku.
            cred = credentials.Certificate('serviceAccountKey.json')
            # Make sure to replace this with your actual Firebase Database URL if different for local testing
            firebase_admin.initialize_app(cred, {
                'databaseURL': 'https://moviebotdb-efb27-default-rtdb.firebaseio.com/' # Make sure this matches your actual DB URL
            })
            print("Firebase initialized successfully from serviceAccountKey.json (local).")
            _firebase_initialized = True
    except (ValueError, json.JSONDecodeError) as ve:
        print(f"Error initializing Firebase (ValueError/JSONDecodeError, likely invalid base64 or JSON in env var): {ve}")
        _firebase_initialized = False
    except FileNotFoundError as fnfe:
        print(f"Error initializing Firebase (FileNotFoundError): {fnfe}. Make sure 'serviceAccountKey.json' exists if running locally without env vars, or ensure env vars are set on Heroku.")
        _firebase_initialized = False
    except Exception as e:
        print(f"An unexpected error occurred during Firebase initialization: {e}")
        _firebase_initialized = False

def _ensure_firebase_initialized():
    """Internal helper to ensure Firebase is initialized before performing operations."""
    global _firebase_initialized
    if not _firebase_initialized:
        print("Firebase not initialized. Attempting to initialize now for operation.")
        init_firebase()
        if not _firebase_initialized:
            print("Firebase initialization failed, cannot proceed with operation.")
            return False
    return True

def save_movie_data(code, file_id, name):
    """Saves movie data (file_id and name) to Firebase under the given code."""
    if not _ensure_firebase_initialized():
        return False # Indicate failure if initialization fails

    ref = db.reference(f'/movies/{code}')
    ref.set({
        'file_id': file_id,
        'name': name
    })
    return True # Indicate success

def get_movie_data(code):
    """Retrieves movie data for a given code from Firebase."""
    if not _ensure_firebase_initialized():
        return None # Return None if initialization fails

    ref = db.reference(f'/movies/{code}')
    return ref.get()

def get_all_movies_data():
    """
    Retrieves all movie data from Firebase.
    Ensures the returned data is always a dictionary, even if Firebase
    returns a list for integer keys.
    """
    if not _ensure_firebase_initialized():
        return {} # Return empty dictionary if initialization fails

    ref = db.reference('/movies')
    data = ref.get()

    if data is None:
        return {} # Return empty dictionary if no data at the /movies path
    elif isinstance(data, list):
        # If Firebase returns a list, it means the keys are sequential integers.
        # Convert it to a dictionary for consistent processing by the bot.
        converted_data = {}
        for i, item in enumerate(data):
            if item is not None: # Firebase can return None for sparse arrays
                converted_data[str(i)] = item # Convert index to string key
        return converted_data
    else:
        return data # Already a dictionary, return as is

def delete_movie_code(code):
    """Deletes a movie entry by its code from Firebase."""
    if not _ensure_firebase_initialized():
        return False # Indicate failure if initialization fails

    ref = db.reference(f'/movies/{code}')
    ref.delete()
    return True

def add_user_to_stats(user_id):
    """Adds a unique user ID to the user_stats collection."""
    if not _ensure_firebase_initialized():
        return False # Indicate failure if initialization fails

    ref = db.reference(f'/user_stats/{user_id}')
    ref.set(True) # Use True as a simple value to mark presence
    return True

def get_user_count():
    """Returns the total number of unique users recorded."""
    if not _ensure_firebase_initialized():
        return 0 # Return 0 if initialization fails

    ref = db.reference('/user_stats')
    users = ref.get()
    return len(users) if users else 0 # Ensure 0 is returned if 'users' is None