# firebase_utils.py
import os
import json
import base64 # New import for base64 decoding
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

# Load environment variables for local development (ignored by Heroku)
load_dotenv()

# Global variable to store the Firestore client instance
# It will be initialized once when init_firebase() is called.
db = None

def init_firebase():
    """
    Initializes the Firebase Admin SDK.
    It attempts to load credentials from the FIREBASE_CRED_BASE64 environment variable first.
    If not found, it falls back to a local 'serviceAccountKey.json' file.
    The Firestore client instance is stored in the global 'db' variable.
    """
    global db

    # Check if Firebase has already been initialized to prevent multiple initializations
    if firebase_admin._apps:
        print("Firebase app already initialized. Skipping initialization.")
        db = firestore.client() # Ensure db client is set even if already initialized
        return

    # --- RECOMMENDED FOR HEROKU DEPLOYMENT: Load from environment variable ---
    # The FIREBASE_CRED_BASE64 environment variable should contain the
    # Base64 encoded JSON content of your service account key file.
    firebase_base64_config = os.getenv("FIREBASE_CRED_BASE64")

    if firebase_base64_config:
        try:
            # Decode the Base64 string to bytes, then decode bytes to UTF-8 string
            decoded_bytes = base64.b64decode(firebase_base64_config)
            decoded_json_string = decoded_bytes.decode('utf-8')
            # Parse the JSON string into a Python dictionary
            cred_dict = json.loads(decoded_json_string)

            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            print("Firebase initialized using Base64 encoded JSON from FIREBASE_CRED_BASE64 environment variable.")
        except (base64.binascii.Error, json.JSONDecodeError) as e:
            # Handle cases where the environment variable content is not valid Base64 or not valid JSON
            print(f"ERROR: Could not decode or parse FIREBASE_CRED_BASE64. Please ensure it's valid Base64 and valid JSON: {e}")
            exit(1) # Exit the application as Firebase initialization is critical
        except Exception as e:
            # Handle any other exceptions during Firebase initialization
            print(f"ERROR: Failed to initialize Firebase from environment variable: {e}")
            exit(1) # Exit the application

    # --- FALLBACK FOR LOCAL DEVELOPMENT: Load from local file ---
    # This path is used only if FIREBASE_CRED_BASE64 is not set.
    # Ensure 'serviceAccountKey.json' is in your project's root directory.
    else:
        service_account_key_path = "serviceAccountKey.json" # Default path for local file
        if os.path.exists(service_account_key_path):
            try:
                cred = credentials.Certificate(service_account_key_path)
                firebase_admin.initialize_app(cred)
                print(f"Firebase initialized using local file: {service_account_key_path}")
            except Exception as e:
                # Handle errors if the local file exists but is invalid or corrupted
                print(f"ERROR: Failed to initialize Firebase from local file '{service_account_key_path}': {e}")
                print("Please ensure 'serviceAccountKey.json' is a valid Firebase service account key file.")
                exit(1) # Exit the application
        else:
            # If no credentials found in environment variable or local file, print error and exit
            print("CRITICAL ERROR: Firebase service account credentials not found.")
            print("Please set the 'FIREBASE_CRED_BASE64' environment variable on Heroku,")
            print("or place your 'serviceAccountKey.json' file in the project directory for local testing.")
            exit(1) # Exit the application

    # Once Firebase is initialized, get the Firestore client
    db = firestore.client()
    print("Firestore client successfully obtained.")


def save_movie_data(code: str, file_id: str, name: str):
    """
    Saves movie data to the 'movies' collection in Firestore.
    Each movie is stored as a document with its 'code' as the Document ID.
    Includes a server timestamp for when the movie was added.
    """
    if db is None: # Defensive check: ensure db is initialized before use
        init_firebase() # Re-initialize if for some reason it's None (shouldn't happen in normal flow)

    movie_ref = db.collection('movies').document(code)
    movie_ref.set({
        'file_id': file_id,
        'name': name,
        'timestamp': firestore.SERVER_TIMESTAMP
    })
    print(f"Firebase: Movie '{name}' with code '{code}' saved.")

def get_movie_data(code: str):
    """
    Retrieves a single movie's data from the 'movies' collection by its 'code'.
    Returns a dictionary of movie data if found, otherwise None.
    """
    if db is None:
        init_firebase()

    movie_ref = db.collection('movies').document(code)
    doc = movie_ref.get()
    if doc.exists:
        return doc.to_dict()
    else:
        print(f"Firebase: Movie with code '{code}' not found.")
        return None

def get_all_movies_data():
    """
    Retrieves all movie data from the 'movies' collection.
    Returns a dictionary where keys are movie codes (Document IDs) and values are movie data.
    """
    if db is None:
        init_firebase()

    movies_collection = db.collection('movies').stream()
    all_movies = {}
    for doc in movies_collection:
        all_movies[doc.id] = doc.to_dict()
    print(f"Firebase: Retrieved {len(all_movies)} movies.")
    return all_movies

def delete_movie_code(code: str):
    """
    Deletes a movie document from the 'movies' collection by its 'code'.
    """
    if db is None:
        init_firebase()

    movie_ref = db.collection('movies').document(code)
    movie_ref.delete()
    print(f"Firebase: Movie with code '{code}' deleted.")

def add_user_to_stats(user_id: str):
    """
    Adds a new user to the 'user_stats' collection or updates an existing user's
    'last_seen' timestamp. 'first_joined' is set only on creation.
    """
    if db is None:
        init_firebase()

    user_ref = db.collection('user_stats').document(user_id)
    # Use merge=True to create the document if it doesn't exist,
    # and to only update specified fields if it does exist.
    user_ref.set({
        'first_joined': firestore.SERVER_TIMESTAMP,
        'last_seen': firestore.SERVER_TIMESTAMP
    }, merge=True)
    print(f"Firebase: User '{user_id}' stats updated/added.")

def get_user_count():
    """
    Returns the total number of unique users in the 'user_stats' collection.
    Uses Firestore's aggregation query for efficiency. Includes a fallback.
    """
    if db is None:
        init_firebase()

    try:
        # Attempt to use the count aggregation query (requires Firebase SDK >= 2.13.0)
        count_query_result = db.collection('user_stats').count().get()
        count = count_query_result[0].get('count')
        print(f"Firebase: Total users (aggregated count): {count}")
        return count
    except Exception as e:
        # Fallback to streaming all documents and counting them if aggregation fails
        print(f"Firebase: Error getting user count with aggregation ({e}). Falling back to streaming.")
        users_collection = db.collection('user_stats').stream()
        count = 0
        for _ in users_collection:
            count += 1
        print(f"Firebase: Total users (streamed count): {count}")
        return count

# Optional: Example usage for local testing of firebase_utils.py directly
if __name__ == '__main__':
    print("--- Running firebase_utils.py for local testing ---")
    init_firebase()

    # --- Test Movie Operations ---
    test_code_1 = "test_movie_1"
    test_name_1 = "My First Test Movie"
    test_file_id_1 = "AgACAgIAAxkBA_test_file_id_1"

    test_code_2 = "test_movie_2"
    test_name_2 = "Another Test Movie"
    test_file_id_2 = "AgACAgIAAxkBA_test_file_id_2"

    print(f"\n--- Saving Movies ---")
    save_movie_data(test_code_1, test_file_id_1, test_name_1)
    save_movie_data(test_code_2, test_file_id_2, test_name_2)

    print(f"\n--- Getting Movie '{test_code_1}' ---")
    movie_1 = get_movie_data(test_code_1)
    if movie_1:
        print(f"Found: Code={test_code_1}, Name={movie_1.get('name')}, FileID={movie_1.get('file_id')}")
    else:
        print(f"Movie '{test_code_1}' not found.")

    print(f"\n--- Getting All Movies ---")
    all_movies = get_all_movies_data()
    for code, data in all_movies.items():
        print(f"Code: {code}, Name: {data.get('name')}")

    # --- Test User Stats Operations ---
    test_user_id_1 = "123456789"
    test_user_id_2 = "987654321"

    print(f"\n--- Adding/Updating Users ---")
    add_user_to_stats(test_user_id_1)
    add_user_to_stats(test_user_id_2)
    add_user_to_stats(test_user_id_1) # Update last_seen for existing user

    print(f"\n--- Getting User Count ---")
    current_user_count = get_user_count()
    print(f"Total unique users: {current_user_count}")

    # --- Clean up (optional) ---
    print(f"\n--- Deleting Movie '{test_code_1}' ---")
    delete_movie_code(test_code_1)
    print(f"--- Deleting Movie '{test_code_2}' ---")
    delete_movie_code(test_code_2)

    # Verify deletion
    movie_1_after_delete = get_movie_data(test_code_1)
    if movie_1_after_delete is None:
        print(f"Confirmed: Movie '{test_code_1}' is deleted.")
