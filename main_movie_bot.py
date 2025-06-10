import asyncio
import os
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

# Import your Firebase utility functions. This file MUST exist alongside main_movie_bot.py
from firebase_utils import init_firebase, save_movie_data, get_movie_data, get_all_movies_data, delete_movie_code, \
    add_user_to_stats, get_user_count

# Load environment variables from .env file
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- CONFIGURE YOUR ADMINS HERE ---
ADMIN_USER_IDS = [
    7602415296,  # Your first Admin User ID
    1648071876,  # Your second Admin User ID (from previous logs)
    1529476219,  # New Admin User ID
]
# --- END ADMIN CONFIG ---

# Initialize Bot and Dispatcher
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage())


# Define FSM States for Admin Movie Addition process
class AddMovieStates(StatesGroup):
    waiting_for_movie_file = State()
    waiting_for_movie_code = State()
    waiting_for_movie_name = State()


# Define FSM States for Admin Movie Deletion process
class DeleteMovieStates(StatesGroup):
    waiting_for_delete_code = State()


# Initialize Firebase globally when the bot starts
init_firebase()
print("Firebase initialized for main movie bot.")


# --- Utility Functions ---

def get_next_available_code():
    """Determines the next sequential integer code available in Firebase."""
    all_movies_raw = get_all_movies_data()
    all_movies = {}  # Initialize as an empty dictionary

    # Ensure all_movies is a dictionary
    if all_movies_raw:  # Check if it's not None or empty
        if isinstance(all_movies_raw, dict):
            all_movies = all_movies_raw
        elif isinstance(all_movies_raw, list):
            # This handles cases where Firebase might store data as an array for sequential integer keys
            # and get_all_movies_data might not have fully converted it, or for robustness.
            for i, item in enumerate(all_movies_raw):
                if item is not None:
                    all_movies[str(i)] = item

    numerical_codes = []
    # Now, all_movies is guaranteed to be a dictionary (or empty)
    for code in all_movies.keys():
        if code.isdigit():
            numerical_codes.append(int(code))

    if not numerical_codes:
        return 1
    else:
        numerical_codes.sort()
        for i, code in enumerate(numerical_codes):
            if i + 1 != code:
                return i + 1
        return numerical_codes[-1] + 1


# --- User Reply Keyboard ---
def get_user_main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="🎬 Filmlar Ro'yxati")  # This will trigger /listallmovies
    builder.button(text="❓ Yordam")  # This will trigger /userhelp
    return builder.as_markup(resize_keyboard=True)


# --- Admin Commands ---

@dp.message(Command("myid"))
async def get_my_id(message: types.Message):
    """Admin helper to find their Telegram User ID."""
    await message.answer(f"Sizning Telegram User IDingiz: `{message.from_user.id}`")


@dp.message(Command("adminhelp"))
async def admin_help_command(message: types.Message):
    """Admin command to list all admin commands and their usage."""
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
        "<code>git push heroku master</code>\n\n"
        "<b>Yordam uchun:</b> @jan_gustau"
    )
    await message.answer(help_text)


@dp.message(Command("addmovie"))
async def add_movie_start(message: types.Message, state: FSMContext):
    """Starts the process of adding a new movie from admin side, suggesting next available code."""
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q.")
        return

    next_code_suggestion = get_next_available_code()

    await message.answer(
        "Yangi film qo'shish uchun, iltimos, film faylini (video yoki hujjat) menga yuboring yoki o'tkazing."
        f"\n\nSizga keyingi bo'sh kod sifatida <b>{next_code_suggestion}</b> taklif qilinadi."
        "\n\nJarayonni bekor qilish uchun /cancel buyrug'ini yuboring."
    )
    await state.update_data(suggested_code_from_sequence=str(next_code_suggestion))
    await state.set_state(AddMovieStates.waiting_for_movie_file)


@dp.message(Command("deletemovie"))
async def delete_movie_start(message: types.Message, state: FSMContext):
    """Starts the process of deleting a movie by code."""
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
    """Handles the movie code for deletion."""
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q.")
        await state.clear()
        return

    movie_code = message.text.strip().lower()

    existing_movie = get_movie_data(movie_code)
    if existing_movie:
        delete_movie_code(movie_code)
        await message.answer(
            f"Film <b>'{existing_movie.get('name', 'Nomsiz Film')}'</b> (kod: <b>{movie_code}</b>) muvaffaqiyatli o'chirildi."
        )
    else:
        await message.answer(
            f"<b>'{movie_code}'</b> kodli film topilmadi. Iltimos, to'g'ri kodni kiriting yoki /cancel."
        )
    await state.clear()


@dp.message(Command("listallmovies"))  # This command now serves both admin and user
async def list_all_movies(message: types.Message):  # Renamed function to be more general
    """Lists all movies with their codes and names."""
    movies_data_raw = get_all_movies_data()
    movies_data = {}  # Initialize as an empty dictionary

    # Ensure movies_data is a dictionary
    if movies_data_raw:  # Check if it's not None or empty
        if isinstance(movies_data_raw, dict):
            movies_data = movies_data_raw
        elif isinstance(movies_data_raw, list):
            for i, item in enumerate(movies_data_raw):
                if item is not None:
                    movies_data[str(i)] = item

    # Now, movies_data is guaranteed to be a dictionary (or empty)
    if movies_data:
        response_text = "<b>Barcha Filmlar Ro'yxati:</b>\n\n"
        try:
            # Safely use .keys() because movies_data is now guaranteed to be a dict
            sorted_codes = sorted(movies_data.keys(), key=lambda x: int(x) if x.isdigit() else x)
        except ValueError:
            sorted_codes = sorted(movies_data.keys())

        for code in sorted_codes:
            movie_info = movies_data.get(code)
            if isinstance(movie_info, dict):
                movie_name = movie_info.get('name', 'Nomsiz Film')
                response_text += f"Kod: <b>{code}</b> - {movie_name}\n"  # Simplified for user view
            else:
                response_text += f"Kod: <b>{code}</b> (Ma'lumot topilmadi yoki xato formatda)\n"

        if len(response_text) > 4000:
            chunks = [response_text[i:i + 4000] for i in range(0, len(response_text), 4000)]
            for chunk in chunks:
                await message.answer(chunk)
        else:
            await message.answer(response_text)
    else:
        await message.answer("Hozircha hech qanday film qo'shilmagan. Adminlar hali film qo'shmaganlar.")


@dp.message(Command("cancel"), StateFilter(AddMovieStates, DeleteMovieStates))
async def cancel_handler(message: types.Message, state: FSMContext):
    """Allows admin to cancel the movie addition or deletion process."""
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q.")
        return

    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Hech qanday faol jarayon yo'q.")
        return

    await state.clear()
    await message.answer("Jarayon bekor qilindi.")


# --- Admin Movie Addition Handlers (FSM) ---

@dp.message(AddMovieStates.waiting_for_movie_file, F.video | F.document)
async def process_movie_file(message: types.Message, state: FSMContext):
    """Handles the forwarded/sent movie file from admin."""
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q.")
        await state.clear()
        return

    file_id = None
    file_type_display = "hujjat"
    if message.video:
        file_id = message.video.file_id
        file_type_display = "video"
    elif message.document:
        if message.document.mime_type and message.document.mime_type.startswith('video/'):
            file_id = message.document.file_id
            file_type_display = "video (hujjat sifatida)"
        else:
            file_id = message.document.file_id
            file_type_display = "hujjat"

    if file_id:
        await state.update_data(file_id=file_id)

        potential_caption = message.caption.strip() if message.caption else ""
        caption_suggested_code = ""
        caption_suggested_name = ""

        lines = potential_caption.split('\n')
        for line in lines:
            code_match = re.search(r'(?:kod|code)\s*(\d+|\w+)', line, re.IGNORECASE)
            if code_match:
                caption_suggested_code = code_match.group(1).strip().lower()

            name_match = re.search(r'(?:nomi|title):\s*(.+)', line, re.IGNORECASE)
            if name_match:
                caption_suggested_name = name_match.group(1).strip()

        data = await state.get_data()
        sequence_suggested_code = data.get("suggested_code_from_sequence")

        builder = InlineKeyboardBuilder()
        prompt_message = (
            f"Film fayli qabul qilindi ({file_type_display}).\n"
            "Endi, iltimos, ushbu film uchun <b>kodni</b> yuboring (Masalan: '1' yoki 'avatar')."
        )

        if sequence_suggested_code:
            prompt_message += f"\n\nTaklif qilingan kod: <code>{sequence_suggested_code}</code>"
            builder.button(text=f"✅ Kodni qabul qilish: {sequence_suggested_code}",
                           callback_data=f"confirm_code:{sequence_suggested_code}")

        if caption_suggested_code and caption_suggested_code != sequence_suggested_code:
            prompt_message += f"\nSarlavhadan aniqlangan kod: <code>{caption_suggested_code}</code>"
            builder.button(text=f"✅ Kodni qabul qilish: {caption_suggested_code}",
                           callback_data=f"confirm_code:{caption_suggested_code}")

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
    """Handles non-movie messages during waiting_for_movie_file state."""
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
    """Handles the movie code input from admin and checks for duplicates."""
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
    """Handles the movie name input from admin and saves all data."""
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
    """Handles non-text messages during waiting_for_movie_name state."""
    if message.from_user.id not in ADMIN_USER_IDS:
        await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q.")
        await state.clear()
        return
    await message.answer(
        "Faqat matnli sarlavhani yuboring. Iltimos, film sarlavhasini kiriting yoki /cancel buyrug'ini yuboring."
    )


# --- User Commands and General Message Handlers ---

@dp.message(Command("start"))
async def handle_start(message: types.Message):
    """
    This handler will be called when the user sends the /start command.
    It adds the user to stats, sends a welcome message, and the user keyboard.
    """
    user_id = str(message.from_user.id)  # Convert to string for Firebase keys
    add_user_to_stats(user_id)  # Add user to the stats collection

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

    await message.answer(welcome_message, reply_markup=get_user_main_keyboard())


# This is the problematic handler
@dp.message(Command("userhelp")) # REMOVED F.text == "❓ Yordam" here
async def user_help_command(message: types.Message):
    """Provides help to regular users."""
    help_text = (
        "<b>Qanday foydalanish mumkin:</b>\n\n"
        "• <b>Film kodini yuboring:</b> Agar sizda filmning kodi bo'lsa (masalan, '123'), shunchaki shu kodni yuboring.\n"
        "• <b>Film sarlavhasini kiriting:</b> Agar kodni bilmasangiz, filmning sarlavhasini (masalan, 'Avatar') kiriting. Bot mos keladigan filmlarni topishga harakat qiladi.\n"
        "• <b>/listallmovies buyrug'i:</b> Mavjud filmlar ro'yxatini ko'rish uchun <b>'🎬 Filmlar Ro'yxati'</b> tugmasini bosing yoki /listallmovies buyrug'ini yuboring.\n"
        "• <b>/start buyrug'i:</b> Botni qayta ishga tushirish uchun.\n\n"
        "<b>Taklif uchun:</b> @nurillomavlonzoda\n"
        "<b>Yordam uchun:</b> @jan_gustau"

    )
    await message.answer(help_text, reply_markup=get_user_main_keyboard())


# This handler now explicitly uses /listallmovies and the button text
@dp.message(F.text == "🎬 Filmlar Ro'yxati") # Removed Command("listallmovies") as it's not needed for button
async def show_all_movies_user(message: types.Message):
    """
    Allows users to see a list of available movie codes and their names.
    This function calls the shared list_all_movies logic.
    """
    # This check ensures that if the user explicitly types /listallmovies, it still works.
    # If the user clicks the button, the F.text filter will catch it.
    if message.text == "🎬 Filmlar Ro'yxati" or message.text == "/listallmovies":
        await list_all_movies(message)  # Call the common function


@dp.message(F.text)  # This general handler only triggers for text messages not caught by other commands/states
async def handle_code_or_name(message: types.Message):
    """
    This handler processes incoming messages that are not commands or FSM steps.
    It checks if the message text is a movie code OR a movie name and responds accordingly.
    """
    current_state = await dp.fsm.get_context(bot, user_id=message.from_user.id, chat_id=message.chat.id).get_state()
    if current_state and message.from_user.id in ADMIN_USER_IDS:
        return

    if message.text.startswith('/'):  # Prevents processing commands that didn't match a Command() filter
        # This handles cases where a user might type a command that isn't explicitly
        # caught by a decorator, e.g., an invalid command like /asdf
        await message.answer("Men tushunmadim. Iltimos, film kodi, nomi yoki buyruqlardan birini kiriting.",
                             reply_markup=get_user_main_keyboard())
        return

    # Handle direct text input from the reply keyboard buttons
    # These are now direct calls to the functions
    if message.text == "🎬 Filmlar Ro'yxati":
        await show_all_movies_user(message) # This will in turn call list_all_movies
        return
    if message.text == "❓ Yordam":
        await user_help_command(message)
        return

    query = message.text.strip().lower()  # Normalize query for case-insensitive matching

    movie_data = None
    found_code = None
    matched_movies = []  # To store all potential matches for name search

    # 1. Try to find by exact code
    retrieved_data_by_code = get_movie_data(query)
    if retrieved_data_by_code and isinstance(retrieved_data_by_code, dict):
        movie_data = retrieved_data_by_code
        found_code = query  # The code is the query itself
    else:
        # 2. If not found by code, try to find by movie name (case-insensitive, partial match)
        all_movies_raw = get_all_movies_data()  # Fetch all movies
        all_movies = {}  # Initialize as empty dict

        # Ensure all_movies is a dictionary
        if all_movies_raw:  # Check if not None or empty
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
            movie_name = movie_data.get('name', f"Kod {found_code}")
            await message.answer_video(
                video=movie_file_id,
                caption=f"🎬 Siz so'ragan film: <b>{movie_name}</b> (Kod: {found_code})"
            )
        except Exception as e:
            print(f"Error sending movie with file_id {movie_data.get('file_id')} for query '{query}': {e}")
            await message.answer(
                f"Xatolik yuz berdi: Film yuborilmadi. Iltimos, keyinroq urinib ko'ring.\n\n"
                "<i>Agar bu xatolik tez-tez takrorlansa, bot egasiga murojaat qiling.</i>",
                reply_markup=get_user_main_keyboard()
            )
    elif len(matched_movies) == 1:  # Found by name, exactly one match
        movie_data = matched_movies[0]['data']
        found_code = matched_movies[0]['code']
        try:
            movie_file_id = movie_data['file_id']
            movie_name = movie_data.get('name', f"Kod {found_code}")
            await message.answer_video(
                video=movie_file_id,
                caption=f"🎬 Siz so'ragan film: <b>{movie_name}</b> (Kod: {found_code})"
            )
        except Exception as e:
            print(f"Error sending movie by name with file_id {movie_data.get('file_id')} for query '{query}': {e}")
            await message.answer(
                f"Xatolik yuz berdi: Film yuborilmadi. Iltimos, keyinroq urinib ko'ring.\n\n"
                "<i>Agar bu xatolik tez-tez takrorlansa, bot egasiga murojaat qiling.</i>",
                reply_markup=get_user_main_keyboard()
            )
    elif len(matched_movies) > 1:  # Found by name, multiple matches
        builder = InlineKeyboardBuilder()
        response_text = "Bir nechta film topildi. Qaysi biri kerak?\n\n"
        for match in matched_movies:
            code = match['code']
            name = match['data'].get('name', 'Nomsiz Film')
            response_text += f"Kod: <b>{code}</b> - {name}\n"
            builder.button(text=f"{name} (Kod: {code})", callback_data=f"select_movie:{code}")

        builder.adjust(1)  # Arrange buttons in a single column
        await message.answer(response_text, reply_markup=builder.as_markup())
    else:  # No movie found by code or name
        await message.answer(
            "🎬 Ushbu kodga yoki sarlavhaga mos film topilmadi. Iltimos, to'g'ri kod yoki sarlavhani kiriting.",
            reply_markup=get_user_main_keyboard())


@dp.callback_query(F.data.startswith("select_movie:"))
async def process_selected_movie_callback(callback_query: types.CallbackQuery):
    """Handles user selection of a movie from multiple search results."""
    selected_code = callback_query.data.split(":")[1]
    movie_data = get_movie_data(selected_code)

    if movie_data and 'file_id' in movie_data:
        try:
            movie_file_id = movie_data['file_id']
            movie_name = movie_data.get('name', f"Kod {selected_code}")
            await callback_query.message.answer_video(
                video=movie_file_id,
                caption=f"🎬 Siz tanlagan film: <b>{movie_name}</b> (Kod: {selected_code})",
                reply_markup=get_user_main_keyboard()
            )
        except Exception as e:
            print(
                f"Error sending selected movie with file_id {movie_data.get('file_id')} for code '{selected_code}': {e}")
            await callback_query.message.answer(
                f"Xatolik yuz berdi: Film yuborilmadi. Iltimos, keyinroq urinib ko'ring.\n\n"
                "<i>Agar bu xatolik tez-tez takrorlansa, bot egasiga murojaat qiling.</i>",
                reply_markup=get_user_main_keyboard()
            )
    else:
        await callback_query.message.answer("Uzr, bu film topilmadi yoki ma'lumotlari buzilgan.",
                                            reply_markup=get_user_main_keyboard())
    await callback_query.answer()


async def main():
    """
    Starts the main bot and keeps it running to listen for updates.
    """
    print("--- MOVIE BOT STARTING ---")
    await dp.start_polling(bot)
    print("--- MOVIE BOT STOPPED ---")


if __name__ == "__main__":
    asyncio.run(main())





















# import asyncio
# import os
# import re
# from aiogram import Bot, Dispatcher, types, F
# from aiogram.enums import ParseMode
# from aiogram.fsm.context import FSMContext
# from aiogram.fsm.state import State, StatesGroup
# from aiogram.fsm.storage.memory import MemoryStorage
# from dotenv import load_dotenv
# from aiogram.client.default import DefaultBotProperties
# from aiogram.filters import Command, StateFilter
# from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
#
# # Import your Firebase utility functions. This file MUST exist alongside main_movie_bot.py
# from firebase_utils import init_firebase, save_movie_data, get_movie_data, get_all_movies_data, delete_movie_code, \
#     add_user_to_stats, get_user_count
#
# # Load environment variables from .env file
# load_dotenv()
# BOT_TOKEN = os.getenv("BOT_TOKEN")
#
# # --- CONFIGURE YOUR ADMINS HERE ---
# ADMIN_USER_IDS = [
#     7602415296,  # Your first Admin User ID
#     1648071876,  # Your second Admin User ID (from previous logs)
#     1529476219,  # New Admin User ID
# ]
# # --- END ADMIN CONFIG ---
#
# # Initialize Bot and Dispatcher
# bot = Bot(
#     token=BOT_TOKEN,
#     default=DefaultBotProperties(parse_mode=ParseMode.HTML)
# )
# dp = Dispatcher(storage=MemoryStorage())
#
#
# # Define FSM States for Admin Movie Addition process
# class AddMovieStates(StatesGroup):
#     waiting_for_movie_file = State()
#     waiting_for_movie_code = State()
#     waiting_for_movie_name = State()
#
#
# # Define FSM States for Admin Movie Deletion process
# class DeleteMovieStates(StatesGroup):
#     waiting_for_delete_code = State()
#
#
# # Initialize Firebase globally when the bot starts
# init_firebase()
# print("Firebase initialized for main movie bot.")
#
#
# # --- Utility Functions ---
#
# def get_next_available_code():
#     """Determines the next sequential integer code available in Firebase."""
#     all_movies_raw = get_all_movies_data()
#     all_movies = {}  # Initialize as an empty dictionary
#
#     # Ensure all_movies is a dictionary
#     if all_movies_raw:  # Check if it's not None or empty
#         if isinstance(all_movies_raw, dict):
#             all_movies = all_movies_raw
#         elif isinstance(all_movies_raw, list):
#             # This handles cases where Firebase might store data as an array for sequential integer keys
#             # and get_all_movies_data might not have fully converted it, or for robustness.
#             for i, item in enumerate(all_movies_raw):
#                 if item is not None:
#                     all_movies[str(i)] = item
#
#     numerical_codes = []
#     # Now, all_movies is guaranteed to be a dictionary (or empty)
#     for code in all_movies.keys():
#         if code.isdigit():
#             numerical_codes.append(int(code))
#
#     if not numerical_codes:
#         return 1
#     else:
#         numerical_codes.sort()
#         for i, code in enumerate(numerical_codes):
#             if i + 1 != code:
#                 return i + 1
#         return numerical_codes[-1] + 1
#
#
# # --- User Reply Keyboard ---
# def get_user_main_keyboard():
#     builder = ReplyKeyboardBuilder()
#     builder.button(text="🎬 Filmlar Ro'yxati")  # This will trigger /listallmovies
#     builder.button(text="❓ Yordam")  # This will trigger /userhelp
#     return builder.as_markup(resize_keyboard=True)
#
#
# # --- Admin Commands ---
#
# @dp.message(Command("myid"))
# async def get_my_id(message: types.Message):
#     """Admin helper to find their Telegram User ID."""
#     await message.answer(f"Sizning Telegram User IDingiz: `{message.from_user.id}`")
#
#
# @dp.message(Command("adminhelp"))
# async def admin_help_command(message: types.Message):
#     """Admin command to list all admin commands and their usage."""
#     if message.from_user.id not in ADMIN_USER_IDS:
#         await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q.")
#         return
#
#     help_text = (
#         "<b>Admin Buyruqlari Ro'yxati:</b>\n\n"
#         "• <b>/addmovie</b>\n"
#         "  Yangi film qo'shish jarayonini boshlaydi. Sizdan film fayli, kodi va sarlavhasi so'raladi.\n\n"
#         "• <b>/deletemovie</b>\n"
#         "  Film kodini o'chiradi. Sizdan film kodi so'raladi.\n\n"
#         "• <b>/listallmovies</b>\n"
#         "  Firebase'da saqlangan barcha filmlar kodlari va sarlavhalarini ro'yxatini ko'rsatadi.\n\n"
#         "• <b>/myid</b>\n"
#         "  Sizning Telegram User IDingizni ko'rsatadi (admin IDsni sozlash uchun foydali).\n\n"
#         "• <b>/cancel</b>\n"
#         "  Agar film qo'shish yoki o'chirish jarayonida bo'lsangiz, uni bekor qiladi.\n\n"
#         "<b>Dasturlash eslatmasi (Deployment):</b>\n"
#         "<code>git add .</code>\n"
#         "<code>git commit -m \"Biror nima o'zgarish\"</code>\n"
#         "<code>git push heroku master</code>\n\n"
#         "<b>Yordam uchun:</b> @jan_gustau"
#     )
#     await message.answer(help_text)
#
#
# @dp.message(Command("addmovie"))
# async def add_movie_start(message: types.Message, state: FSMContext):
#     """Starts the process of adding a new movie from admin side, suggesting next available code."""
#     if message.from_user.id not in ADMIN_USER_IDS:
#         await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q.")
#         return
#
#     next_code_suggestion = get_next_available_code()
#
#     await message.answer(
#         "Yangi film qo'shish uchun, iltimos, film faylini (video yoki hujjat) menga yuboring yoki o'tkazing."
#         f"\n\nSizga keyingi bo'sh kod sifatida <b>{next_code_suggestion}</b> taklif qilinadi."
#         "\n\nJarayonni bekor qilish uchun /cancel buyrug'ini yuboring."
#     )
#     await state.update_data(suggested_code_from_sequence=str(next_code_suggestion))
#     await state.set_state(AddMovieStates.waiting_for_movie_file)
#
#
# @dp.message(Command("deletemovie"))
# async def delete_movie_start(message: types.Message, state: FSMContext):
#     """Starts the process of deleting a movie by code."""
#     if message.from_user.id not in ADMIN_USER_IDS:
#         await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q.")
#         return
#
#     await message.answer(
#         "O'chirmoqchi bo'lgan filmning kodini yuboring."
#         "\n\nJarayonni bekor qilish uchun /cancel buyrug'ini yuboring."
#     )
#     await state.set_state(DeleteMovieStates.waiting_for_delete_code)
#
#
# @dp.message(DeleteMovieStates.waiting_for_delete_code, F.text)
# async def process_delete_movie_code(message: types.Message, state: FSMContext):
#     """Handles the movie code for deletion."""
#     if message.from_user.id not in ADMIN_USER_IDS:
#         await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q.")
#         await state.clear()
#         return
#
#     movie_code = message.text.strip().lower()
#
#     existing_movie = get_movie_data(movie_code)
#     if existing_movie:
#         delete_movie_code(movie_code)
#         await message.answer(
#             f"Film <b>'{existing_movie.get('name', 'Nomsiz Film')}'</b> (kod: <b>{movie_code}</b>) muvaffaqiyatli o'chirildi."
#         )
#     else:
#         await message.answer(
#             f"<b>'{movie_code}'</b> kodli film topilmadi. Iltimos, to'g'ri kodni kiriting yoki /cancel."
#         )
#     await state.clear()
#
#
# @dp.message(Command("listallmovies"))  # This command now serves both admin and user
# async def list_all_movies(message: types.Message):  # Renamed function to be more general
#     """Lists all movies with their codes and names."""
#     movies_data_raw = get_all_movies_data()
#     movies_data = {}  # Initialize as an empty dictionary
#
#     # Ensure movies_data is a dictionary
#     if movies_data_raw:  # Check if it's not None or empty
#         if isinstance(movies_data_raw, dict):
#             movies_data = movies_data_raw
#         elif isinstance(movies_data_raw, list):
#             for i, item in enumerate(movies_data_raw):
#                 if item is not None:
#                     movies_data[str(i)] = item
#
#     # Now, movies_data is guaranteed to be a dictionary (or empty)
#     if movies_data:
#         response_text = "<b>Barcha Filmlar Ro'yxati:</b>\n\n"
#         try:
#             # Safely use .keys() because movies_data is now guaranteed to be a dict
#             sorted_codes = sorted(movies_data.keys(), key=lambda x: int(x) if x.isdigit() else x)
#         except ValueError:
#             sorted_codes = sorted(movies_data.keys())
#
#         for code in sorted_codes:
#             movie_info = movies_data.get(code)
#             if isinstance(movie_info, dict):
#                 movie_name = movie_info.get('name', 'Nomsiz Film')
#                 response_text += f"Kod: <b>{code}</b> - {movie_name}\n"  # Simplified for user view
#             else:
#                 response_text += f"Kod: <b>{code}</b> (Ma'lumot topilmadi yoki xato formatda)\n"
#
#         if len(response_text) > 4000:
#             chunks = [response_text[i:i + 4000] for i in range(0, len(response_text), 4000)]
#             for chunk in chunks:
#                 await message.answer(chunk)
#         else:
#             await message.answer(response_text)
#     else:
#         await message.answer("Hozircha hech qanday film qo'shilmagan. Adminlar hali film qo'shmaganlar.")
#
#
# @dp.message(Command("cancel"), StateFilter(AddMovieStates, DeleteMovieStates))
# async def cancel_handler(message: types.Message, state: FSMContext):
#     """Allows admin to cancel the movie addition or deletion process."""
#     if message.from_user.id not in ADMIN_USER_IDS:
#         await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q.")
#         return
#
#     current_state = await state.get_state()
#     if current_state is None:
#         await message.answer("Hech qanday faol jarayon yo'q.")
#         return
#
#     await state.clear()
#     await message.answer("Jarayon bekor qilindi.")
#
#
# # --- Admin Movie Addition Handlers (FSM) ---
#
# @dp.message(AddMovieStates.waiting_for_movie_file, F.video | F.document)
# async def process_movie_file(message: types.Message, state: FSMContext):
#     """Handles the forwarded/sent movie file from admin."""
#     if message.from_user.id not in ADMIN_USER_IDS:
#         await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q.")
#         await state.clear()
#         return
#
#     file_id = None
#     file_type_display = "hujjat"
#     if message.video:
#         file_id = message.video.file_id
#         file_type_display = "video"
#     elif message.document:
#         if message.document.mime_type and message.document.mime_type.startswith('video/'):
#             file_id = message.document.file_id
#             file_type_display = "video (hujjat sifatida)"
#         else:
#             file_id = message.document.file_id
#             file_type_display = "hujjat"
#
#     if file_id:
#         await state.update_data(file_id=file_id)
#
#         potential_caption = message.caption.strip() if message.caption else ""
#         caption_suggested_code = ""
#         caption_suggested_name = ""
#
#         lines = potential_caption.split('\n')
#         for line in lines:
#             code_match = re.search(r'(?:kod|code)\s*(\d+|\w+)', line, re.IGNORECASE)
#             if code_match:
#                 caption_suggested_code = code_match.group(1).strip().lower()
#
#             name_match = re.search(r'(?:nomi|title):\s*(.+)', line, re.IGNORECASE)
#             if name_match:
#                 caption_suggested_name = name_match.group(1).strip()
#
#         data = await state.get_data()
#         sequence_suggested_code = data.get("suggested_code_from_sequence")
#
#         builder = InlineKeyboardBuilder()
#         prompt_message = (
#             f"Film fayli qabul qilindi ({file_type_display}).\n"
#             "Endi, iltimos, ushbu film uchun <b>kodni</b> yuboring (Masalan: '1' yoki 'avatar')."
#         )
#
#         if sequence_suggested_code:
#             prompt_message += f"\n\nTaklif qilingan kod: <code>{sequence_suggested_code}</code>"
#             builder.button(text=f"✅ Kodni qabul qilish: {sequence_suggested_code}",
#                            callback_data=f"confirm_code:{sequence_suggested_code}")
#
#         if caption_suggested_code and caption_suggested_code != sequence_suggested_code:
#             prompt_message += f"\nSarlavhadan aniqlangan kod: <code>{caption_suggested_code}</code>"
#             builder.button(text=f"✅ Kodni qabul qilish: {caption_suggested_code}",
#                            callback_data=f"confirm_code:{caption_suggested_code}")
#
#         if caption_suggested_name:
#             prompt_message += f"\nSarlavhadan aniqlangan sarlavha: <i>{caption_suggested_name}</i>"
#             await state.update_data(suggested_name=caption_suggested_name)
#
#         await message.answer(prompt_message, reply_markup=builder.as_markup())
#         await state.set_state(AddMovieStates.waiting_for_movie_code)
#
#     else:
#         await message.answer(
#             "Menga film fayli (video yoki hujjat) yuborilmadi. Iltimos, qaytadan urinib ko'ring.\n"
#             "Jarayonni bekor qilish uchun /cancel buyrug'ini yuboring."
#         )
#
#
# @dp.message(AddMovieStates.waiting_for_movie_file)
# async def process_invalid_file_type(message: types.Message, state: FSMContext):
#     """Handles non-movie messages during waiting_for_movie_file state."""
#     if message.from_user.id not in ADMIN_USER_IDS:
#         await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q.")
#         await state.clear()
#         return
#     await message.answer(
#         "Menga film fayli (video yoki hujjat) kerak. Siz matn yoki boshqa turdagi fayl yubordingiz.\n"
#         "Iltimos, qaytadan urinib ko'ring yoki /cancel buyrug'ini yuboring."
#     )
#
#
# @dp.callback_query(F.data.startswith("confirm_code:"), AddMovieStates.waiting_for_movie_code)
# async def process_confirm_code_callback(callback_query: types.CallbackQuery, state: FSMContext):
#     if callback_query.from_user.id not in ADMIN_USER_IDS:
#         await callback_query.answer("Sizda bu amalni bajarishga ruxsat yo'q.", show_alert=True)
#         return
#
#     confirmed_code = callback_query.data.split(":")[1]
#     data = await state.get_data()
#     file_id = data.get("file_id")
#     suggested_name = data.get("suggested_name")
#
#     if not file_id:
#         await callback_query.message.answer(
#             "Xatolik: Film fayli IDsi topilmadi. Iltimos, /addmovie buyrug'i bilan qayta boshlang."
#         )
#         await state.clear()
#         await callback_query.answer()
#         return
#
#     existing_movie = get_movie_data(confirmed_code)
#     if existing_movie:
#         await callback_query.message.answer(
#             f"<b>Xatolik:</b> Siz tanlagan kod (<b>{confirmed_code}</b>) allaqachon mavjud.\n"
#             f"Mavjud film sarlavhasi: '{existing_movie.get('name', 'Nomsiz')}'\n"
#             "Iltimos, boshqa kod kiriting yoki jarayonni bekor qilish uchun /cancel."
#         )
#         await callback_query.answer()
#         return
#
#     await state.update_data(final_movie_code=confirmed_code)
#
#     prompt_name_message = (
#         f"Film kodi <b>'{confirmed_code}'</b> qabul qilindi.\n"
#         "Endi, iltimas, filmning <b>to'liq sarlavhasini</b> yuboring (Masalan: 'Avatar: Suv Yo'li')."
#     )
#     if suggested_name:
#         builder = InlineKeyboardBuilder()
#         builder.button(text=f"✅ Sarlavhani qabul qilish: {suggested_name}",
#                        callback_data=f"confirm_name:{suggested_name}")
#         await callback_query.message.answer(prompt_name_message, reply_markup=builder.as_markup())
#     else:
#         await callback_query.message.answer(prompt_name_message)
#
#     await state.set_state(AddMovieStates.waiting_for_movie_name)
#     await callback_query.answer("Kod qabul qilindi.")
#
#
# @dp.message(AddMovieStates.waiting_for_movie_code, F.text)
# async def process_movie_code_input(message: types.Message, state: FSMContext):
#     """Handles the movie code input from admin and checks for duplicates."""
#     if message.from_user.id not in ADMIN_USER_IDS:
#         await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q.")
#         await state.clear()
#         return
#
#     user_input_code = message.text.strip().lower()
#     data = await state.get_data()
#     file_id = data.get("file_id")
#     suggested_name = data.get("suggested_name")
#
#     if not file_id:
#         await message.answer(
#             "Xatolik: Film fayli IDsi topilmadi. Iltimos, /addmovie buyrug'i bilan qayta boshlang."
#         )
#         await state.clear()
#         return
#
#     movie_code_to_use = user_input_code
#
#     existing_movie = get_movie_data(movie_code_to_use)
#     if existing_movie:
#         await message.answer(
#             f"<b>Xatolik:</b> Siz kiritgan kod (<b>{movie_code_to_use}</b>) allaqallon mavjud.\n"
#             f"Mavjud film sarlavhasi: '{existing_movie.get('name', 'Nomsiz')}'\n"
#             "Iltimos, boshqa kod kiriting yoki jarayonni bekor qilish uchun /cancel."
#         )
#         return
#
#     await state.update_data(final_movie_code=movie_code_to_use)
#
#     prompt_name_message = (
#         f"Film kodi <b>'{movie_code_to_use}'</b> qabul qilindi.\n"
#         "Endi, iltimas, filmning <b>to'liq sarlavhasini</b> yuboring (Masalan: 'Avatar: Suv Yo'li')."
#     )
#     if suggested_name:
#         builder = InlineKeyboardBuilder()
#         builder.button(text=f"✅ Sarlavhani qabul qilish: {suggested_name}",
#                        callback_data=f"confirm_name:{suggested_name}")
#         await message.answer(prompt_name_message, reply_markup=builder.as_markup())
#     else:
#         await message.answer(prompt_name_message)
#
#     await state.set_state(AddMovieStates.waiting_for_movie_name)
#
#
# @dp.callback_query(F.data.startswith("confirm_name:"), AddMovieStates.waiting_for_movie_name)
# async def process_confirm_name_callback(callback_query: types.CallbackQuery, state: FSMContext):
#     if callback_query.from_user.id not in ADMIN_USER_IDS:
#         await callback_query.answer("Sizda bu amalni bajarishga ruxsat yo'q.", show_alert=True)
#         return
#
#     confirmed_name = callback_query.data.split(":")[1]
#     data = await state.get_data()
#     file_id = data.get("file_id")
#     final_movie_code = data.get("final_movie_code")
#
#     if not file_id or not final_movie_code:
#         await callback_query.message.answer(
#             "Xatolik: Film fayli IDsi yoki kodi topilmadi. Iltimos, /addmovie buyrug'i bilan qayta boshlang."
#         )
#         await state.clear()
#         await callback_query.answer()
#         return
#
#     try:
#         save_movie_data(final_movie_code, file_id, confirmed_name)
#         await callback_query.message.answer(
#             f"Film muvaffaqiyatli saqlandi!\n"
#             f"Kod: `{final_movie_code}`\nSarlavha: <b>{confirmed_name}</b>\n"
#             f"File ID: <code>{file_id}</code>\n\n"
#             "Siz endi yangi film qo'shishingiz yoki botni ishlatishingiz mumkin."
#         )
#         await state.clear()
#     except Exception as e:
#         await callback_query.message.answer(f"Firebase'ga saqlashda kutilmagan xatolik yuz berdi: {e}\n"
#                                             "Iltimos, qaytadan urinib ko'ring yoki /cancel.")
#         print(f"Error saving movie data to Firebase: {e}")
#     await callback_query.answer("Sarlavha qabul qilindi.")
#
#
# @dp.message(AddMovieStates.waiting_for_movie_name, F.text)
# async def process_movie_name_input(message: types.Message, state: FSMContext):
#     """Handles the movie name input from admin and saves all data."""
#     if message.from_user.id not in ADMIN_USER_IDS:
#         await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q.")
#         await state.clear()
#         return
#
#     user_input_name = message.text.strip()
#     data = await state.get_data()
#     file_id = data.get("file_id")
#     final_movie_code = data.get("final_movie_code")
#
#     if not file_id or not final_movie_code:
#         await message.answer(
#             "Xatolik: Film fayli IDsi yoki kodi topilmadi. Iltimos, /addmovie buyrug'i bilan qayta boshlang."
#         )
#         await state.clear()
#         return
#
#     movie_name_to_save = user_input_name
#
#     try:
#         save_movie_data(final_movie_code, file_id, movie_name_to_save)
#         await message.answer(
#             f"Film muvaffaqiyatli saqlandi!\n"
#             f"Kod: `{final_movie_code}`\nSarlavha: <b>{movie_name_to_save}</b>\n"
#             f"File ID: <code>{file_id}</code>\n\n"
#             "Siz endi yangi film qo'shishingiz yoki botni ishlatishingiz mumkin."
#         )
#         await state.clear()
#     except Exception as e:
#         await message.answer(f"Firebase'ga saqlashda kutilmagan xatolik yuz berdi: {e}\n"
#                              "Iltimos, qaytadan urinib ko'ring yoki /cancel.")
#         print(f"Error saving movie data to Firebase: {e}")
#
#
# @dp.message(AddMovieStates.waiting_for_movie_name)
# async def process_invalid_name_input(message: types.Message, state: FSMContext):
#     """Handles non-text messages during waiting_for_movie_name state."""
#     if message.from_user.id not in ADMIN_USER_IDS:
#         await message.answer("Sizda bu buyruqni ishlatishga ruxsat yo'q.")
#         await state.clear()
#         return
#     await message.answer(
#         "Faqat matnli sarlavhani yuboring. Iltimos, film sarlavhasini kiriting yoki /cancel buyrug'ini yuboring."
#     )
#
#
# # --- User Commands and General Message Handlers ---
#
# @dp.message(Command("start"))
# async def handle_start(message: types.Message):
#     """
#     This handler will be called when the user sends the /start command.
#     It adds the user to stats, sends a welcome message, and the user keyboard.
#     """
#     user_id = str(message.from_user.id)  # Convert to string for Firebase keys
#     add_user_to_stats(user_id)  # Add user to the stats collection
#
#     total_users = get_user_count()  # Get the current total user count
#
#     welcome_message = (
#         "<b>Assalomu alaykum!</b> 👋\n\n"
#         "Men sizga filmlar kodini topishga yordam beruvchi botman. "
#         "Film kodini yuboring yoki uning sarlavhasini kiriting va men sizga filmni topib beraman.\n\n"
#         "Misol uchun, agar sizda '1' kodli film kerak bo'lsa, shunchaki '1' deb yuboring."
#         "\n\nBoshqa buyruqlar uchun /userhelp buyrug'ini bosing."
#         f"\n\n🥳 Baxtli foydalanuvchilar soni: <b>{total_users}</b>"
#     )
#
#     if message.from_user.id in ADMIN_USER_IDS:
#         welcome_message += "\n\n<i>Siz adminsiz! Admin buyruqlariga kirish uchun /adminhelp ni bosing.</i>"
#
#     await message.answer(welcome_message, reply_markup=get_user_main_keyboard())
#
#
# @dp.message(Command("userhelp"), F.text == "❓ Yordam")
# async def user_help_command(message: types.Message):
#     """Provides help to regular users."""
#     help_text = (
#         "<b>Qanday foydalanish mumkin:</b>\n\n"
#         "• <b>Film kodini yuboring:</b> Agar sizda filmning kodi bo'lsa (masalan, '123'), shunchaki shu kodni yuboring.\n"
#         "• <b>Film sarlavhasini kiriting:</b> Agar kodni bilmasangiz, filmning sarlavhasini (masalan, 'Avatar') kiriting. Bot mos keladigan filmlarni topishga harakat qiladi.\n"
#         "• <b>/listallmovies buyrug'i:</b> Mavjud filmlar ro'yxatini ko'rish uchun <b>'🎬 Filmlar Ro'yxati'</b> tugmasini bosing yoki /listallmovies buyrug'ini yuboring.\n"
#         "• <b>/start buyrug'i:</b> Botni qayta ishga tushirish uchun.\n\n"
#         "<b>Taklif uchun:</b> @nurillomavlonzoda\n"
#         "<b>Yordam uchun:</b> @jan_gustau"
#
#     )
#     await message.answer(help_text, reply_markup=get_user_main_keyboard())
#
#
# # This handler now explicitly uses /listallmovies and the button text
# @dp.message(Command("listallmovies"), F.text == "🎬 Filmlar Ro'yxati")
# async def show_all_movies_user(message: types.Message):  # Renamed to avoid clash with generic list_all_movies
#     """
#     Allows users to see a list of available movie codes and their names.
#     This function calls the shared list_all_movies logic.
#     """
#     await list_all_movies(message)  # Call the common function
#
#
# @dp.message(F.text)  # This general handler only triggers for text messages not caught by other commands/states
# async def handle_code_or_name(message: types.Message):
#     """
#     This handler processes incoming messages that are not commands or FSM steps.
#     It checks if the message text is a movie code OR a movie name and responds accordingly.
#     """
#     current_state = await dp.fsm.get_context(bot, user_id=message.from_user.id, chat_id=message.chat.id).get_state()
#     if current_state and message.from_user.id in ADMIN_USER_IDS:
#         return
#
#     if message.text.startswith('/'):  # Prevents processing commands that didn't match a Command() filter
#         return
#
#     # Handle direct text input from the reply keyboard buttons
#     if message.text == "🎬 Filmlar Ro'yxati":
#         await show_all_movies_user(message)
#         return
#     if message.text == "❓ Yordam":
#         await user_help_command(message)
#         return
#
#     query = message.text.strip().lower()  # Normalize query for case-insensitive matching
#
#     movie_data = None
#     found_code = None
#     matched_movies = []  # To store all potential matches for name search
#
#     # 1. Try to find by exact code
#     retrieved_data_by_code = get_movie_data(query)
#     if retrieved_data_by_code and isinstance(retrieved_data_by_code, dict):
#         movie_data = retrieved_data_by_code
#         found_code = query  # The code is the query itself
#     else:
#         # 2. If not found by code, try to find by movie name (case-insensitive, partial match)
#         all_movies_raw = get_all_movies_data()  # Fetch all movies
#         all_movies = {}  # Initialize as empty dict
#
#         # Ensure all_movies is a dictionary
#         if all_movies_raw:  # Check if not None or empty
#             if isinstance(all_movies_raw, dict):
#                 all_movies = all_movies_raw
#             elif isinstance(all_movies_raw, list):
#                 for i, item in enumerate(all_movies_raw):
#                     if item is not None:
#                         all_movies[str(i)] = item
#
#         if all_movies:  # Now work with the guaranteed dictionary
#             for code, data in all_movies.items():
#                 if isinstance(data, dict) and 'name' in data and query in data['name'].lower():
#                     matched_movies.append({'code': code, 'data': data})
#
#     if movie_data:  # If found by exact code
#         try:
#             movie_file_id = movie_data['file_id']
#             movie_name = movie_data.get('name', f"Kod {found_code}")
#             await message.answer_video(
#                 video=movie_file_id,
#                 caption=f"🎬 Siz so'ragan film: <b>{movie_name}</b> (Kod: {found_code})"
#             )
#         except Exception as e:
#             print(f"Error sending movie with file_id {movie_data.get('file_id')} for query '{query}': {e}")
#             await message.answer(
#                 f"Xatolik yuz berdi: Film yuborilmadi. Iltimos, keyinroq urinib ko'ring.\n\n"
#                 "<i>Agar bu xatolik tez-tez takrorlansa, bot egasiga murojaat qiling.</i>",
#                 reply_markup=get_user_main_keyboard()
#             )
#     elif len(matched_movies) == 1:  # Found by name, exactly one match
#         movie_data = matched_movies[0]['data']
#         found_code = matched_movies[0]['code']
#         try:
#             movie_file_id = movie_data['file_id']
#             movie_name = movie_data.get('name', f"Kod {found_code}")
#             await message.answer_video(
#                 video=movie_file_id,
#                 caption=f"🎬 Siz so'ragan film: <b>{movie_name}</b> (Kod: {found_code})"
#             )
#         except Exception as e:
#             print(f"Error sending movie by name with file_id {movie_data.get('file_id')} for query '{query}': {e}")
#             await message.answer(
#                 f"Xatolik yuz berdi: Film yuborilmadi. Iltimos, keyinroq urinib ko'ring.\n\n"
#                 "<i>Agar bu xatolik tez-tez takrorlansa, bot egasiga murojaat qiling.</i>",
#                 reply_markup=get_user_main_keyboard()
#             )
#     elif len(matched_movies) > 1:  # Found by name, multiple matches
#         builder = InlineKeyboardBuilder()
#         response_text = "Bir nechta film topildi. Qaysi biri kerak?\n\n"
#         for match in matched_movies:
#             code = match['code']
#             name = match['data'].get('name', 'Nomsiz Film')
#             response_text += f"Kod: <b>{code}</b> - {name}\n"
#             builder.button(text=f"{name} (Kod: {code})", callback_data=f"select_movie:{code}")
#
#         builder.adjust(1)  # Arrange buttons in a single column
#         await message.answer(response_text, reply_markup=builder.as_markup())
#     else:  # No movie found by code or name
#         await message.answer(
#             "🎬 Ushbu kodga yoki sarlavhaga mos film topilmadi. Iltimos, to'g'ri kod yoki sarlavhani kiriting.",
#             reply_markup=get_user_main_keyboard())
#
#
# @dp.callback_query(F.data.startswith("select_movie:"))
# async def process_selected_movie_callback(callback_query: types.CallbackQuery):
#     """Handles user selection of a movie from multiple search results."""
#     selected_code = callback_query.data.split(":")[1]
#     movie_data = get_movie_data(selected_code)
#
#     if movie_data and 'file_id' in movie_data:
#         try:
#             movie_file_id = movie_data['file_id']
#             movie_name = movie_data.get('name', f"Kod {selected_code}")
#             await callback_query.message.answer_video(
#                 video=movie_file_id,
#                 caption=f"🎬 Siz tanlagan film: <b>{movie_name}</b> (Kod: {selected_code})",
#                 reply_markup=get_user_main_keyboard()
#             )
#         except Exception as e:
#             print(
#                 f"Error sending selected movie with file_id {movie_data.get('file_id')} for code '{selected_code}': {e}")
#             await callback_query.message.answer(
#                 f"Xatolik yuz berdi: Film yuborilmadi. Iltimos, keyinroq urinib ko'ring.\n\n"
#                 "<i>Agar bu xatolik tez-tez takrorlansa, bot egasiga murojaat qiling.</i>",
#                 reply_markup=get_user_main_keyboard()
#             )
#     else:
#         await callback_query.message.answer("Uzr, bu film topilmadi yoki ma'lumotlari buzilgan.",
#                                             reply_markup=get_user_main_keyboard())
#     await callback_query.answer()
#
#
# async def main():
#     """
#     Starts the main bot and keeps it running to listen for updates.
#     """
#     print("--- MOVIE BOT STARTING ---")
#     await dp.start_polling(bot)
#     print("--- MOVIE BOT STOPPED ---")
#
#
# if __name__ == "__main__":
#     asyncio.run(main())