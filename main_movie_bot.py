# main_movie_bot.py (CONTINUED)
# main_movie_bot.py
import asyncio
import os
import re
from functools import wraps # Import wraps for decorators
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from aiogram.client.default import DefaultBotProperties # Essential for aiogram 3.7+
from aiogram.filters import Command, StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

# Import your Firebase utility functions. This file MUST exist alongside main_movie_bot.py
# Ensure firebase_utils.py is correct and configured for your Firebase project.
from firebase_utils import init_firebase, save_movie_data, get_movie_data, get_all_movies_data, delete_movie_code, \
    add_user_to_stats, get_user_count

# Load environment variables from .env file for local development
# On Heroku, environment variables are set directly in the Config Vars.
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- CONFIGURE YOUR ADMINS HERE ---
# These are Telegram User IDs of your bot administrators.
# Only these users will have access to admin-specific commands and features.
# Add your own user IDs here. Example: [123456789, 987654321]
ADMIN_USER_IDS = [
    7602415296,
    1648071876,  # Your second Admin User ID (from previous logs)
    1529476219,  # New Admin User ID
]
# --- END ADMIN CONFIG ---

# --- CONFIGURE MANDATORY SUBSCRIPTION CHANNELS HERE ---
# Users must be subscribed to these channels to use the bot.
# 'id' can be '@channelusername' or the channel's numeric ID.
# 'link' is the invitation link. 'name' is for display.
MANDATORY_CHANNELS = [
    {"id": "@kinoxada1", "link": "https://t.me/kinoxada1", "name": "Kino Xada 1"}
    # Add more channels if needed:
    # {"id": "@another_channel", "link": "https://t.me/another_channel", "name": "Another Channel Name"}
]
# --- END MANDATORY SUBSCRIPTION CONFIG ---

# Initialize Bot and Dispatcher
# CRITICAL FIX for aiogram 3.7.0+: parse_mode is now passed via DefaultBotProperties
if not BOT_TOKEN:
    print("CRITICAL ERROR: BOT_TOKEN environment variable is not set. Exiting.")
    exit(1) # Exit if bot token is not available

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage()) # MemoryStorage for FSM states (resets on bot restart)


# Define FSM States for Admin Movie Addition process
class AddMovieStates(StatesGroup):
    waiting_for_movie_file = State() # Admin sends the video/document file
    waiting_for_movie_code = State() # Admin inputs the movie code (e.g., "1", "avatar")
    waiting_for_movie_name = State() # Admin inputs the movie display name

# Define FSM States for Admin Movie Deletion process
class DeleteMovieStates(StatesGroup):
    waiting_for_delete_code = State() # Admin inputs the movie code to delete


# Initialize Firebase globally when the bot starts
# This will ensure 'db' is set up before any Firebase operations are attempted.
print("Attempting to initialize Firebase for main movie bot...")
init_firebase() # Call the initialization function from firebase_utils.py


# --- SUBSCRIPTION CHECK FUNCTIONS AND DECORATOR ---

async def check_all_subscriptions(user_id: int) -> tuple[bool, list[dict]]:
    """
    Checks if a user is a member of ALL specified mandatory channels.
    Returns (True, []) if subscribed to all, otherwise (False, [list of unsubscribed channels]).
    """
    unsubscribed_channels = []
    for channel in MANDATORY_CHANNELS:
        try:
            chat_member = await bot.get_chat_member(chat_id=channel["id"], user_id=user_id)
            if chat_member.status not in ["member", "administrator", "creator"]:
                unsubscribed_channels.append(channel)
        except Exception as e:
            # Log the error but continue checking other channels.
            # Treat as unsubscribed if there's an error getting chat member status.
            print(f"Error checking subscription for user {user_id} in channel {channel['id']}: {e}")
            unsubscribed_channels.append(channel) # Ensure this channel is listed if an error occurs

    return len(unsubscribed_channels) == 0, unsubscribed_channels

def subscription_required(func):
    """
    A decorator to ensure a user is subscribed to all mandatory channels.
    If not subscribed, it sends a message with subscription links and a check button.
    Admins defined in ADMIN_USER_IDS bypass this check.
    """
    @wraps(func) # Preserves original function's metadata
    async def wrapper(message: types.Message, *args, **kwargs):
        # Admins bypass the subscription check
        if message.from_user.id in ADMIN_USER_IDS:
            return await func(message, *args, **kwargs)

        is_subscribed, unsubscribed_channels = await check_all_subscriptions(message.from_user.id)

        if not is_subscribed:
            # Build the inline keyboard for subscription links and a check button
            markup = InlineKeyboardBuilder()
            response_text = (
                "Botdan foydalanish uchun avval quyidagi kanallarga obuna bo'lishingiz shart:\n\n"
            )
            for channel in unsubscribed_channels:
                response_text += f"• <b>{channel['name']}</b>: <a href='{channel['link']}'>{channel['link']}</a>\n"
                markup.button(text=f"A'zo Bo'lish: {channel['name']}", url=channel['link'])

            # Add a "Tekshirish" (Check) button for users to re-verify subscription
            markup.button(text="✅ A'zolikni Tekshirish", callback_data="check_my_subscription")
            markup.adjust(1) # Arrange buttons in a single column

            await message.answer(
                response_text,
                reply_markup=markup.as_markup(),
                disable_web_page_preview=True # Prevents link previews from cluttering the message
            )
            return # Stop processing the original message, as user needs to subscribe
        return await func(message, *args, **kwargs) # If subscribed, execute original function
    return wrapper

# Callback handler for the "✅ A'zolikni Tekshirish" button
@dp.callback_query(F.data == "check_my_subscription")
async def process_check_subscription_callback(callback_query: types.CallbackQuery):
    """
    Handles the callback query when a user clicks the 'Check Subscription' button.
    It re-checks their subscription status and updates the message.
    """
    user_id = callback_query.from_user.id
    is_subscribed, unsubscribed_channels = await check_all_subscriptions(user_id)

    if is_subscribed:
        # If subscribed, delete the old message and send a welcome message with main keyboard
        await callback_query.message.delete()
        await callback_query.message.answer(
            "🥳 Tabriklaymiz! Siz barcha kanallarga obuna bo'ldingiz. Endi botdan to'liq foydalanishingiz mumkin. \n\n /start",
            reply_markup=get_user_main_keyboard(),
            protect_content=True
        )
    else:
        # If still not subscribed, update the message to reflect the channels they are missing
        markup = InlineKeyboardBuilder()
        response_text = "Afsuski, siz quyidagi kanallarga obuna bo'lmagansiz:\n\n"
        for channel in unsubscribed_channels:
            response_text += f"• <b>{channel['name']}</b>: <a href='{channel['link']}'>{channel['link']}</a>\n"
            markup.button(text=f"A'zo Bo'lish: {channel['name']}", url=channel['link'])
        markup.button(text="✅ A'zolikni Tekshirish", callback_data="check_my_subscription")
        markup.adjust(1)

        await callback_query.message.edit_text(
            response_text,
            reply_markup=markup.as_markup(),
            disable_web_page_preview=True,
            protect_content=True
        )
    await callback_query.answer() # Always answer the callback query to dismiss the loading animation


# --- Utility Functions ---

def get_next_available_code():
    """
    Determines the next sequential integer code available in Firebase.
    It fetches all existing movie codes and returns the smallest positive integer
    that is not currently in use.
    """
    all_movies_raw = get_all_movies_data() # Fetch all movies from Firebase
    all_movies = {} # Initialize as an empty dictionary

    # Ensure all_movies is a dictionary for consistent processing
    if all_movies_raw:
        if isinstance(all_movies_raw, dict):
            all_movies = all_movies_raw
        elif isinstance(all_movies_raw, list):
            # This handles cases where Firebase might store data as an array for sequential integer keys
            # or for robustness against unexpected data structures.
            for i, item in enumerate(all_movies_raw):
                if item is not None:
                    all_movies[str(i)] = item

    numerical_codes = []
    # Extract only integer-like codes
    for code in all_movies.keys():
        if code.isdigit():
            numerical_codes.append(int(code))

    if not numerical_codes:
        return 1 # If no numerical codes exist, start from 1
    else:
        numerical_codes.sort() # Sort the existing codes
        for i, code in enumerate(numerical_codes):
            if i + 1 != code:
                return i + 1 # Return the first missing number in the sequence
        return numerical_codes[-1] + 1 # If sequence is full, return the next number


# --- User Reply Keyboard ---
def get_user_main_keyboard():
    """
    Returns a ReplyKeyboardMarkup for regular users with main navigation buttons.
    """
    builder = ReplyKeyboardBuilder()
    builder.button(text="🎬 Filmlar Ro'yxati") # Button to list all movies
    builder.button(text="Yordam ❓") # Button for help message
    # Add other general user buttons here if needed
    return builder.as_markup(resize_keyboard=True)


# --- Admin Commands ---

@dp.message(Command("myid"))
async def get_my_id(message: types.Message):
    """
    Admin helper command to quickly get their Telegram User ID.
    Useful for configuring ADMIN_USER_IDS.
    """
    await message.answer(f"Sizning Telegram User IDingiz: `{message.from_user.id}`", parse_mode=ParseMode.MARKDOWN_V2)


@dp.message(Command("adminhelp"))
async def admin_help_command(message: types.Message):
    """
    Admin command to list all available admin commands and their usage.
    Only accessible by users in ADMIN_USER_IDS.
    """
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q.")
        return

    help_text = (
        "<b>Admin Buyruqlari Ro'yxati:</b>\n\n"
        "• <b>/addmovie</b>\n"
        "  Yangi film qo'shish jarayonini boshlaydi. Sizdan film fayli, kodi va sarlavhasi so'raladi.\n\n"
        "• <b>/deletemovie</b>\n"
        "  Film kodini o'chiradi. Sizdan film kodi so'raladi.\n\n"
        "• <b>/listallmovies</b>\n"
        "  Firebase'da saqlangan barcha filmlar kodlari va sarlavhalarini ro'yxatini ko'rsatadi.\n\n"
        "• <b>/myid</b>\n"
        "  Sizning Telegram User IDingizni ko'rsatadi (admin IDsni sozlash uchun foydali).\n\n"
        "• <b>/cancel</b>\n"
        "  Agar film qo'shish yoki o'chirish jarayonida bo'lsangiz, uni bekor qiladi.\n\n"
        "<b>Dasturlash eslatmasi (Deployment):</b>\n"
        "<code>git add .</code>\n"
        "<code>git commit -m \"Biror nima o'zgarish\"</code>\n"
        "<code>git push heroku main</code> (or `git push heroku master` depending on your branch)\n\n"
        "<b>Yordam uchun:</b> @jan_gustau" # Replace with your actual admin username
    )
    await message.answer(help_text, protect_content=True)


@dp.message(Command("addmovie"))
async def add_movie_start(message: types.Message, state: FSMContext):
    """
    Starts the process of adding a new movie.
    Prompts the admin to send the movie file and suggests the next available code.
    Sets the FSM state to waiting_for_movie_file.
    """
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q.")
        return

    next_code_suggestion = get_next_available_code() # Get a suggested code from Firebase data

    await message.answer(
        "Yangi film qo'shish uchun, iltimos, film faylini (video yoki hujjat) menga yuboring yoki o'tkazing."
        f"\n\nSizga keyingi bo'sh kod sifatida <b>{next_code_suggestion}</b> taklif qilinadi."
        "\n\nJarayonni bekor qilish uchun /cancel buyrug'ini yuboring."
    )
    # Store the suggested code in FSM context for later use
    await state.update_data(suggested_code_from_sequence=str(next_code_suggestion))
    await state.set_state(AddMovieStates.waiting_for_movie_file)


@dp.message(Command("deletemovie"))
async def delete_movie_start(message: types.Message, state: FSMContext):
    """
    Starts the process of deleting a movie.
    Prompts the admin to send the movie code to be deleted.
    Sets the FSM state to waiting_for_delete_code.
    """
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q.")
        return

    await message.answer(
        "O'chirmoqchi bo'lgan filmning kodini yuboring."
        "\n\nJarayonni bekor qilish uchun /cancel buyrug'ini yuboring."
    )
    await state.set_state(DeleteMovieStates.waiting_for_delete_code)


@dp.message(DeleteMovieStates.waiting_for_delete_code, F.text)
async def process_delete_movie_code(message: types.Message, state: FSMContext):
    """
    Handles the movie code provided by the admin for deletion.
    It attempts to delete the movie from Firebase based on the given code.
    """
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q.")
        await state.clear() # Clear state if unauthorized user somehow gets here
        return

    movie_code = message.text.strip().lower() # Normalize input code

    existing_movie = get_movie_data(movie_code) # Check if movie exists in Firebase
    if existing_movie:
        delete_movie_code(movie_code) # Delete movie from Firebase
        await message.answer(
            f"Film <b>'{existing_movie.get('name', 'Nomsiz Film')}'</b> (kod: <b>{movie_code}</b>) muvaffaqiyatli o'chirildi."
        )
    else:
        await message.answer(
            f"<b>'{movie_code}'</b> kodli film topilmadi. Iltimos, to'g'ri kodni kiriting yoki /cancel."
        )
    await state.clear() # Clear state after successful deletion or not found


@dp.message(Command("listallmovies")) # This command now serves both admin and user
@subscription_required # Apply the decorator to user-facing commands to enforce subscription
async def list_all_movies(message: types.Message):
    """
    Lists all movies stored in Firebase with their codes and names.
    Sorts numerical codes numerically and non-numerical codes alphabetically.
    Handles messages longer than Telegram's 4096 character limit by splitting.
    """
    movies_data_raw = get_all_movies_data() # Fetch all movies from Firebase
    movies_data = {} # Initialize as an empty dictionary

    # Ensure movies_data is a dictionary for consistent processing
    if movies_data_raw:
        if isinstance(movies_data_raw, dict):
            movies_data = movies_data_raw
        elif isinstance(movies_data_raw, list):
            for i, item in enumerate(movies_data_raw):
                if item is not None:
                    movies_data[str(i)] = item

    if movies_data:
        response_text = "<b>Barcha Filmlar Ro'yxati:</b>\n\n"
        try:
            # Sort codes: numerical first (as integers), then alphabetical for others
            sorted_codes = sorted(movies_data.keys(), key=lambda x: (int(x) if x.isdigit() else float('inf'), x))
        except ValueError:
            # Fallback for unexpected non-digit codes if error occurs during int conversion
            sorted_codes = sorted(movies_data.keys())

        for code in sorted_codes:
            movie_info = movies_data.get(code)
            if isinstance(movie_info, dict):
                movie_name = movie_info.get('name', 'Nomsiz Film') # Fallback name if 'name' key is missing
                response_text += f"Kod: <b>{code}</b> - {movie_name}\n"
            else:
                response_text += f"Kod: <b>{code}</b> (Ma'lumot topilmadi yoki xato formatda)\n"

        # Split long messages into chunks to comply with Telegram API limits
        if len(response_text) > 4096: # Telegram's message character limit
            chunks = [response_text[i:i + 4096] for i in range(0, len(response_text), 4096)]
            for chunk in chunks:
                await message.answer(chunk, protect_content=True)
        else:
            await message.answer(response_text, protect_content=True)
    else:
        await message.answer("Hozircha hech qanday film qo'shilmagan. Adminlar hali film qo'shmaganlar.")


@dp.message(Command("cancel"), StateFilter(AddMovieStates, DeleteMovieStates))
async def cancel_handler(message: types.Message, state: FSMContext):
    """
    Allows an admin to cancel the current FSM process (movie addition or deletion).
    Clears the current state for the user.
    """
    # Admins only for this specific cancel, as it clears admin FSM states.
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q.")
        return

    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Hech qanday faol jarayon yo'q.")
        return

    await state.clear() # Clear the FSM state
    await message.answer("Jarayon bekor qilindi.")


# --- Admin Movie Addition Handlers (FSM) ---

@dp.message(AddMovieStates.waiting_for_movie_file, F.video | F.document)
async def process_movie_file(message: types.Message, state: FSMContext):
    """
    Handles the movie file (video or document) sent by the admin.
    Extracts the file_id and attempts to parse suggested code/name from the caption.
    Transitions to waiting_for_movie_code state.
    """
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q.")
        await state.clear()
        return

    file_id = None
    file_type_display = "hujjat" # Default display type

    if message.video:
        file_id = message.video.file_id
        file_type_display = "video"

    elif message.document:
        # Check if document is a video (e.g., .mp4 sent as document)
        if message.document.mime_type and message.document.mime_type.startswith('video/'):
            file_id = message.document.file_id
            file_type_display = "video (hujjat sifatida)"
        else:
            file_id = message.document.file_id # For other document types, keep as document
            file_type_display = "hujjat"

    if file_id:
        await state.update_data(file_id=file_id)

        potential_caption = message.caption.strip() if message.caption else ""
        caption_suggested_code = ""
        caption_suggested_name = ""

        # Attempt to parse code and name from message caption
        lines = potential_caption.split('\n')
        for line in lines:
            code_match = re.search(r'(?:kod|code)\s*[:=]?\s*(\S+)', line, re.IGNORECASE)
            if code_match:
                caption_suggested_code = code_match.group(1).strip().lower()

            name_match = re.search(r'(?:nomi|sarlavha|title)\s*[:=]?\s*(.+)', line, re.IGNORECASE)
            if name_match:
                caption_suggested_name = name_match.group(1).strip()

        data = await state.get_data()
        sequence_suggested_code = data.get("suggested_code_from_sequence")

        builder = InlineKeyboardBuilder()
        prompt_message = (
            f"Film fayli qabul qilindi ({file_type_display}).\n"
            "Endi, iltimos, ushbu film uchun <b>kodni</b> yuboring (Masalan: '1' yoki 'avatar')."
        )

        # Offer suggested codes via inline buttons
        if sequence_suggested_code:
            prompt_message += f"\n\nTaklif qilingan kod (navbatdagi): <code>{sequence_suggested_code}</code>"
            builder.button(text=f"✅ Kodni qabul qilish: {sequence_suggested_code}",
                           callback_data=f"confirm_code:{sequence_suggested_code}")

        if caption_suggested_code and caption_suggested_code != sequence_suggested_code:
            # Only add if different from sequence suggestion
            prompt_message += f"\nSarlavhadan aniqlangan kod: <code>{caption_suggested_code}</code>"
            builder.button(text=f"✅ Kodni qabul qilish: {caption_suggested_code}",
                           callback_data=f"confirm_code:{caption_suggested_code}")

        # Store suggested name for next step
        if caption_suggested_name:
            prompt_message += f"\nSarlavhadan aniqlangan sarlavha: <i>{caption_suggested_name}</i>"
            await state.update_data(suggested_name=caption_suggested_name)

        await message.answer(prompt_message, reply_markup=builder.as_markup())
        await state.set_state(AddMovieStates.waiting_for_movie_code)

    else:
        await message.answer(
            "Menga film fayli (video yoki hujjat) yuborilmadi. Iltimos, qaytadan urinib ko'ring.\n"
            "Jarayonni bekor qilish uchun /cancel buyrug'ini yuboring."
        )


@dp.message(AddMovieStates.waiting_for_movie_file)
async def process_invalid_file_type(message: types.Message, state: FSMContext):
    """
    Handles non-movie messages (like text or photos) when the bot expects a movie file.
    """
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q.")
        await state.clear()
        return
    await message.answer(
        "Menga film fayli (video yoki hujjat) kerak. Siz matn yoki boshqa turdagi fayl yubordingiz.\n"
        "Iltimos, qaytadan urinib ko'ring yoki /cancel buyrug'ini yuboring."
    )


@dp.callback_query(F.data.startswith("confirm_code:"), AddMovieStates.waiting_for_movie_code)
async def process_confirm_code_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Handles callback queries for confirming a suggested movie code from inline keyboard.
    Checks for code uniqueness and transitions to waiting_for_movie_name.
    """
    if callback_query.from_user.id not in ADMIN_USER_IDS:
        await callback_query.answer("Sizda bu amalni bajarishga ruxsat yo'q.", show_alert=True)
        return

    confirmed_code = callback_query.data.split(":")[1]
    data = await state.get_data()
    file_id = data.get("file_id")
    suggested_name = data.get("suggested_name")

    if not file_id:
        await callback_query.message.answer(
            "Xatolik: Film fayli IDsi topilmadi. Iltimos, /addmovie buyrug'i bilan qayta boshlang."
        )
        await state.clear()
        await callback_query.answer()
        return

    existing_movie = get_movie_data(confirmed_code)
    if existing_movie:
        await callback_query.message.answer(
            f"<b>Xatolik:</b> Siz tanlagan kod (<b>{confirmed_code}</b>) allaqachon mavjud.\n"
            f"Mavjud film sarlavhasi: '{existing_movie.get('name', 'Nomsiz')}'\n"
            "Iltimos, boshqa kod kiriting yoki jarayonni bekor qilish uchun /cancel."
        )
        await callback_query.answer()
        return

    await state.update_data(final_movie_code=confirmed_code)

    prompt_name_message = (
        f"Film kodi <b>'{confirmed_code}'</b> qabul qilindi.\n"
        "Endi, iltimas, filmning <b>to'liq sarlavhasini</b> yuboring (Masalan: 'Avatar: Suv Yo'li')."
    )
    if suggested_name:
        builder = InlineKeyboardBuilder()
        builder.button(text=f"✅ Sarlavhani qabul qilish: {suggested_name}",
                       callback_data=f"confirm_name:{suggested_name}")
        await callback_query.message.answer(prompt_name_message, reply_markup=builder.as_markup())
    else:
        await callback_query.message.answer(prompt_name_message)

    await state.set_state(AddMovieStates.waiting_for_movie_name)
    await callback_query.answer("Kod qabul qilindi.")


@dp.message(AddMovieStates.waiting_for_movie_code, F.text)
async def process_movie_code_input(message: types.Message, state: FSMContext):
    """
    Handles the movie code text input from admin.
    Checks for code uniqueness and transitions to waiting_for_movie_name.
    """
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q.")
        await state.clear()
        return

    user_input_code = message.text.strip().lower()
    data = await state.get_data()
    file_id = data.get("file_id")
    suggested_name = data.get("suggested_name")

    if not file_id:
        await message.answer(
            "Xatolik: Film fayli IDsi topilmadi. Iltimos, /addmovie buyrug'i bilan qayta boshlang."
        )
        await state.clear()
        return

    movie_code_to_use = user_input_code

    existing_movie = get_movie_data(movie_code_to_use)
    if existing_movie:
        await message.answer(
            f"<b>Xatolik:</b> Siz kiritgan kod (<b>{movie_code_to_use}</b>) allaqallon mavjud.\n"
            f"Mavjud film sarlavhasi: '{existing_movie.get('name', 'Nomsiz')}'\n"
            "Iltimos, boshqa kod kiriting yoki jarayonni bekor qilish uchun /cancel."
        )
        return

    await state.update_data(final_movie_code=movie_code_to_use)

    prompt_name_message = (
        f"Film kodi <b>'{movie_code_to_use}'</b> qabul qilindi.\n"
        "Endi, iltimas, filmning <b>to'liq sarlavhasini</b> yuboring (Masalan: 'Avatar: Suv Yo'li')."
    )
    if suggested_name:
        builder = InlineKeyboardBuilder()
        builder.button(text=f"✅ Sarlavhani qabul qilish: {suggested_name}",
                       callback_data=f"confirm_name:{suggested_name}")
        await message.answer(prompt_name_message, reply_markup=builder.as_markup())
    else:
        await message.answer(prompt_name_message)

    await state.set_state(AddMovieStates.waiting_for_movie_name)


@dp.callback_query(F.data.startswith("confirm_name:"), AddMovieStates.waiting_for_movie_name)
async def process_confirm_name_callback(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Handles callback queries for confirming a suggested movie name from inline keyboard.
    Saves the movie data to Firebase and clears the state.
    """
    if callback_query.from_user.id not in ADMIN_USER_IDS:
        await callback_query.answer("Sizda bu amalni bajarishga ruxsat yo'q.", show_alert=True)
        return

    confirmed_name = callback_query.data.split(":")[1]
    data = await state.get_data()
    file_id = data.get("file_id")
    final_movie_code = data.get("final_movie_code")

    if not file_id or not final_movie_code:
        await callback_query.message.answer(
            "Xatolik: Film fayli IDsi yoki kodi topilmadi. Iltimos, /addmovie buyrug'i bilan qayta boshlang."
        )
        await state.clear()
        await callback_query.answer()
        return

    try:
        save_movie_data(final_movie_code, file_id, confirmed_name)
        await callback_query.message.answer(
            f"Film muvaffaqiyatli saqlandi!\n"
            f"Kod: `{final_movie_code}`\nSarlavha: <b>{confirmed_name}</b>\n"
            f"File ID: <code>{file_id}</code>\n\n"
            "Siz endi yangi film qo'shishingiz yoki botni ishlatishingiz mumkin."
        )
        await state.clear()
    except Exception as e:
        await callback_query.message.answer(f"Firebase'ga saqlashda kutilmagan xatolik yuz berdi: {e}\n"
                                            "Iltimos, qaytadan urinib ko'ring yoki /cancel.")
        print(f"Error saving movie data to Firebase: {e}")
    await callback_query.answer("Sarlavha qabul qilindi.")


@dp.message(AddMovieStates.waiting_for_movie_name, F.text)
async def process_movie_name_input(message: types.Message, state: FSMContext):
    """
    Handles the movie name text input from admin.
    Saves the movie data to Firebase and clears the state.
    """
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q.")
        await state.clear()
        return

    user_input_name = message.text.strip()
    data = await state.get_data()
    file_id = data.get("file_id")
    final_movie_code = data.get("final_movie_code")

    if not file_id or not final_movie_code:
        await message.answer(
            "Xatolik: Film fayli IDsi yoki kodi topilmadi. Iltimos, /addmovie buyrug'i bilan qayta boshlang."
        )
        await state.clear()
        return

    movie_name_to_save = user_input_name

    try:
        save_movie_data(final_movie_code, file_id, movie_name_to_save)
        await message.answer(
            f"Film muvaffaqiyatli saqlandi!\n"
            f"Kod: `{final_movie_code}`\nSarlavha: <b>{movie_name_to_save}</b>\n"
            f"File ID: <code>{file_id}</code>\n\n"
            "Siz endi yangi film qo'shishingiz yoki botni ishlatishingiz mumkin."
        )
        await state.clear()
    except Exception as e:
        await message.answer(f"Firebase'ga saqlashda kutilmagan xatolik yuz berdi: {e}\n"
                             "Iltimos, qaytadan urinib ko'ring yoki /cancel.")
        print(f"Error saving movie data to Firebase: {e}")


@dp.message(AddMovieStates.waiting_for_movie_name)
async def process_invalid_name_input(message: types.Message, state: FSMContext):
    """
    Handles non-text messages when the bot expects a movie name.
    """
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q.")
        await state.clear()
        return
    await message.answer(
        "Faqat matnli sarlavhani yuboring. Iltimos, film sarlavhasini kiriting yoki /cancel buyrug'ini yuboring."
    )


# --- User Commands and General Message Handlers ---

@dp.message(Command("start"))
@subscription_required # Apply the decorator here to enforce subscription for /start
async def handle_start(message: types.Message):
    """
    This handler will be called when the user sends the /start command.
    It adds the user to stats, sends a welcome message, and the user keyboard.
    """
    user_id = str(message.from_user.id)  # Convert to string for Firebase keys
    add_user_to_stats(user_id)  # Add user to the stats collection or update last_seen

    total_users = get_user_count()  # Get the current total user count

    welcome_message = (
        "<b>Assalomu alaykum!</b> 👋\n\n"
        "Men sizga filmlar kodini topishga yordam beruvchi botman. "
        "Film kodini yuboring yoki uning sarlavhasini kiriting va men sizga filmni topib beraman.\n\n"
        "Misol uchun, agar sizda '1' kodli film kerak bo'lsa, shunchaki '1' deb yuboring."
        "\n\nBoshqa buyruqlar uchun /userhelp buyrug'ini bosing."
        f"\n\n🥳 Baxtli foydalanuvchilar soni: <b>{total_users}</b>"
    )

    if message.from_user.id in ADMIN_USER_IDS:
        welcome_message += "\n\n<i>Siz adminsiz! Admin buyruqlariga kirish uchun /adminhelp ni bosing.</i>"

    await message.answer(welcome_message, reply_markup=get_user_main_keyboard(), protect_content=True)


@dp.message(Command("userhelp"))
@subscription_required # Apply the decorator here to enforce subscription for /userhelp
async def user_help_command(message: types.Message):
    """Provides help to regular users."""
    help_text = (
        "<b>Qanday foydalanish mumkin:</b>\n\n"
        "• <b>Film kodini yuboring:</b> Agar sizda filmning kodi bo'lsa (masalan, '123'), shunchaki shu kodni yuboring.\n"
        "• <b>Film sarlavhasini kiriting:</b> Agar kodni bilmasangiz, filmning sarlavhasini (masalan, 'Avatar') kiriting. Bot mos keladigan filmlarni topishga harakat qiladi.\n"
        "• <b>/listallmovies buyrug'i:</b> Mavjud filmlar ro'yxatini ko'rish uchun <b>'🎬 Filmlar Ro'yxati'</b> tugmasini bosing yoki /listallmovies buyrug'ini yuboring.\n"
        "• <b>/start buyrug'i:</b> Botni qayta ishga tushirish uchun.\n\n"
        "<b>Taklif uchun:</b> @nurillomavlonzoda\n" # Replace with actual contact
        "<b>Yordam uchun:</b> @jan_gustau" # Replace with actual contact
    )
    await message.answer(help_text, reply_markup=get_user_main_keyboard(), protect_content=True)


@dp.message(F.text == "🎬 Filmlar Ro'yxati") # This still works for button click, will internally call list_all_movies which has the decorator
@subscription_required # Apply the decorator here to enforce subscription
async def show_all_movies_user(message: types.Message):
    """
    Allows users to see a list of available movie codes and their names via button click.
    This function calls the shared list_all_movies logic.
    """
    await list_all_movies(message) # Delegates to the shared listing function


@dp.message(F.text == "❓ Yordam") # Handles the "Yordam" button click
@subscription_required # Apply the decorator here to enforce subscription
async def show_user_help_button(message: types.Message):
    """
    Allows users to see the help message via button click.
    """
    await user_help_command(message) # Delegates to the shared help function


@dp.message(F.text)  # This general handler only triggers for text messages not caught by other commands/states
@subscription_required # Apply the decorator here to enforce subscription for general text messages
async def handle_code_or_name(message: types.Message):
    """
    This handler processes incoming text messages that are not commands or FSM steps.
    It attempts to find a movie by exact code or by partial name match.
    If multiple matches are found, it provides inline buttons for selection.
    """
    # Prevent processing admin text if they are in an FSM state (e.g., adding/deleting movie)
    current_state = await dp.fsm.get_context(bot, user_id=message.from_user.id, chat_id=message.chat.id).get_state()
    if current_state: # If user is in ANY FSM state, do not process as general text input
        # Note: Valid FSM inputs are handled by their respective handlers.
        # This prevents accidental triggers for other states.
        return

    # Filter out commands that didn't match a specific Command() filter (e.g., /invalidcommand)
    if message.text.startswith('/'):
        await message.answer("Men tushunmadim. Iltimos, film kodi, nomi yoki buyruqlardan birini kiriting.",
                             reply_markup=get_user_main_keyboard())

        return

    query = message.text.strip().lower()  # Normalize query for case-insensitive matching

    movie_data = None
    found_code = None
    matched_movies = []  # To store all potential matches for name search

    # 1. Try to find by exact code first
    retrieved_data_by_code = get_movie_data(query)
    if retrieved_data_by_code and isinstance(retrieved_data_by_code, dict):
        movie_data = retrieved_data_by_code
        found_code = query  # The code is the query itself
    else:
        # 2. If not found by exact code, try to find by movie name (case-insensitive, partial match)
        all_movies_raw = get_all_movies_data()  # Fetch all movies from Firebase
        all_movies = {}  # Initialize as empty dict

        # Ensure all_movies is a dictionary for consistent processing
        if all_movies_raw:
            if isinstance(all_movies_raw, dict):
                all_movies = all_movies_raw
            elif isinstance(all_movies_raw, list):
                for i, item in enumerate(all_movies_raw):
                    if item is not None:
                        all_movies[str(i)] = item

        if all_movies:  # Now work with the guaranteed dictionary
            for code, data in all_movies.items():
                if isinstance(data, dict) and 'name' in data and query in data['name'].lower():
                    matched_movies.append({'code': code, 'data': data})

    if movie_data:  # If found by exact code
        try:
            movie_file_id = movie_data['file_id']
            movie_name = movie_data.get('name', f"Kod {found_code}") # Use code as fallback name
            await message.answer_video(
                video=movie_file_id,
                caption=f"🎬 Siz so'ragan film: <b>{movie_name}</b> (Kod: {found_code})",
                protect_content=True
            )
        except Exception as e:
            print(f"Error sending movie with file_id {movie_data.get('file_id')} for query '{query}': {e}")
            await message.answer(
                f"Xatolik yuz berdi: Film yuborilmadi. Iltimos, keyinroq urinib ko'ring.\n\n"
                "<i>Agar bu xatolik tez-tez takrorlansa, bot egasiga murojaat qiling.</i>",
                reply_markup=get_user_main_keyboard(),
                protect_content=True
            )
    elif len(matched_movies) == 1:  # Found by name, exactly one match
        movie_data = matched_movies[0]['data']
        found_code = matched_movies[0]['code']
        try:
            movie_file_id = movie_data['file_id']
            movie_name = movie_data.get('name', f"Kod {found_code}")
            await message.answer_video(
                video=movie_file_id,
                caption=f"🎬 Siz so'ragan film: <b>{movie_name}</b> (Kod: {found_code})",
                protect_content=True
            )
        except Exception as e:
            print(f"Error sending movie by name with file_id {movie_data.get('file_id')} for query '{query}': {e}")
            await message.answer(
                f"Xatolik yuz berdi: Film yuborilmadi. Iltimos, keyinroq urinib ko'ring.\n\n"
                "<i>Agar bu xatolik tez-tez takrorlansa, bot egasiga murojaat qiling.</i>",
                reply_markup=get_user_main_keyboard(),
                protect_content=True
            )
    elif len(matched_movies) > 1:  # Found by name, multiple matches
        builder = InlineKeyboardBuilder()
        response_text = "Bir nechta film topildi. Qaysi biri kerak?\n\n"
        # Sort matched movies by name for consistent display
        matched_movies_sorted = sorted(matched_movies, key=lambda x: x['data'].get('name', '').lower())
        for match in matched_movies_sorted:
            code = match['code']
            name = match['data'].get('name', 'Nomsiz Film')
            response_text += f"Kod: <b>{code}</b> - {name}\n"
            builder.button(text=f"{name} (Kod: {code})", callback_data=f"select_movie:{code}")

        builder.adjust(1)  # Arrange buttons in a single column
        await message.answer(response_text, reply_markup=builder.as_markup())
    else:  # No movie found by code or name
        await message.answer(
            f"Kechirasiz, <b>'{message.text}'</b> kodli yoki sarlavhali film topilmadi. "
            "Iltimos, boshqa kod yoki sarlavha kiriting.",
            reply_markup=get_user_main_keyboard(),
            protect_content=True
        )

# Callback handler for selecting a movie from multiple matches
@dp.callback_query(F.data.startswith("select_movie:"))
@subscription_required # Apply the decorator here to enforce subscription
async def process_select_movie_callback(callback_query: types.CallbackQuery):
    """
    Handles the inline keyboard callback when a user selects a movie from multiple search results.
    Retrieves and sends the selected movie.
    """
    selected_code = callback_query.data.split(":")[1]
    movie_data = get_movie_data(selected_code)

    if movie_data:
        try:
            movie_file_id = movie_data['file_id']
            movie_name = movie_data.get('name', f"Kod {selected_code}")
            await callback_query.message.answer_video(
                video=movie_file_id,
                caption=f"🎬 Siz tanlagan film: <b>{movie_name}</b> (Kod: {selected_code})",
                protect_content=True
            )
        except Exception as e:
            print(f"Error sending selected movie with file_id {movie_data.get('file_id')} for code '{selected_code}': {e}")
            await callback_query.message.answer(
                f"Xatolik yuz berdi: Film yuborilmadi. Iltimos, keyinroq urinib ko'ring.\n\n"
                "<i>Agar bu xatolik tez-tez takrorlansa, bot egasiga murojaat qiling.</i>",
                reply_markup=get_user_main_keyboard(),
                protect_content=True
            )
    else:
        await callback_query.message.answer("Tanlangan film topilmadi. Ma'lumotlar o'chirilgan bo'lishi mumkin.")

    await callback_query.answer() # Always answer the callback query


@dp.message() # Catch-all handler for any other messages not explicitly handled
async def handle_unrecognized_message(message: types.Message):
    """
    This handler catches any messages that weren't caught by more specific handlers (commands, FSM states, F.text filters).
    It informs the user that the input was not understood and provides the main keyboard.
    """
    # This handler will be called only if no other filter/handler matches.
    # The subscription_required decorator is NOT applied here because we want to
    # respond even if they are not subscribed (e.g., if they send random text).
    # However, if a command like /start or /listallmovies is sent, the decorator on those
    # specific handlers will take precedence.

    await message.answer(
        "Kechirasiz, men sizning buyrug'ingizni tushunmadim. Iltimos, film kodini, sarlavhasini kiriting "
        "yoki pastdagi tugmalardan foydalaning.",
        reply_markup=get_user_main_keyboard(),
        protect_content=True
    )


# Main function to run the bot
async def main():
    # Ensure BOT_TOKEN is available before starting polling
    if not BOT_TOKEN:
        print("CRITICAL ERROR: BOT_TOKEN environment variable not set. Bot cannot start.")
        exit(1) # Exit if token is missing

    print("Starting bot polling...")
    # This function will start the bot and keep it running, listening for updates.
    await dp.start_polling(bot)

async def on_startup(app):
    # Set Telegram webhook
    webhook_url = os.getenv("WEBHOOK_URL")  # You'll set this env var in Render
    if webhook_url:
        await bot.set_webhook(url=webhook_url)
        print(f"Webhook set to {webhook_url}")
    else:
        print("ERROR: WEBHOOK_URL environment variable not set")

async def on_shutdown(app):
    await bot.delete_webhook()
    await bot.session.close()

# Create Aiohttp app
app = web.Application()
setup_application(app, dp, bot=bot)

app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

@app.get("/")
async def healthcheck(request):
    return web.Response(text="Bot is running!")

if __name__ == "__main__":
    web.run_app(app, port=int(os.environ.get("PORT", 5000)))
