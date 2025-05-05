
import logging
import os
import random
import json
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

SONGS_FOLDER = "songs"
SESSIONS_FOLDER = "user_sessions"
AUTHORIZED_USERS = ["1918624551"]

os.makedirs(SONGS_FOLDER, exist_ok=True)
os.makedirs(SESSIONS_FOLDER, exist_ok=True)

def get_keyboard():
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("▶️ Next", callback_data="next"),
        InlineKeyboardButton("📜 Playlist", callback_data="playlist")
    )
    return kb

def get_session_path(user_id):
    return os.path.join(SESSIONS_FOLDER, f"{user_id}.json")

def save_user_session(user_id, group_id):
    with open(get_session_path(user_id), "w") as f:
        json.dump({"group_id": group_id}, f)

def load_user_session(user_id):
    path = get_session_path(user_id)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f).get("group_id")
    return None

def extract_metadata(file_path, fallback_title):
    try:
        audio = MP3(file_path, ID3=EasyID3)
        title = audio.get("title", [fallback_title])[0]
        artist = audio.get("artist", ["$SQUONK"])[0]
    except Exception:
        title, artist = fallback_title, "$SQUONK"
    return title, artist

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    if not message.chat.type == "private":
        return
    if str(message.from_user.id) not in AUTHORIZED_USERS:
        return await message.reply("⛔️ Only the Squonk Overlord can use this bot.")
    await message.reply("👋 Welcome to Squonk Radio V0.4.3!
Use /setup to link your group.")

@dp.message_handler(commands=["setup"])
async def setup(message: types.Message):
    if not message.chat.type == "private":
        return
    if str(message.from_user.id) not in AUTHORIZED_USERS:
        return await message.reply("⛔️ Not allowed.")
    await message.reply("📩 Send me `GroupID: <your_group_id>` to link a group.")

@dp.message_handler(lambda msg: msg.text and msg.text.startswith("GroupID:"))
async def receive_group_id(message: types.Message):
    if str(message.from_user.id) not in AUTHORIZED_USERS:
        return await message.reply("⛔️ Not allowed.")
    group_id = message.text.replace("GroupID:", "").strip()
    if not group_id.lstrip("-").isdigit():
        return await message.reply("❌ Invalid group ID format. Use `GroupID: 123456789`")
    save_user_session(message.from_user.id, group_id)
    await message.reply(f"✅ Group ID `{group_id}` saved. Now send me .mp3 files!")

@dp.message_handler(content_types=types.ContentType.AUDIO)
async def handle_audio(message: types.Message):
    if str(message.from_user.id) not in AUTHORIZED_USERS:
        return await message.reply("⛔️ You are not authorized to upload music.")
    group_id = load_user_session(message.from_user.id)
    if not group_id:
        return await message.reply("❗ Please first send `GroupID: <your_group_id>`.")

    group_folder = os.path.join(SONGS_FOLDER, group_id)
    os.makedirs(group_folder, exist_ok=True)

    song_id = message.audio.file_unique_id
    file_path = os.path.join(group_folder, f"{song_id}.mp3")
    await message.audio.download(destination_file=file_path)

    fallback_title = os.path.splitext(message.audio.file_name or "Unknown")[0]
    title, artist = extract_metadata(file_path, fallback_title)

    with open(file_path + ".json", "w") as f:
        json.dump({"file": file_path, "title": title, "artist": artist}, f)

    await message.reply(f"✅ Saved `{title}` for group {group_id}")

@dp.message_handler(commands=["play"])
async def play(message: types.Message):
    group_id = str(message.chat.id)
    folder = os.path.join(SONGS_FOLDER, group_id)
    if not os.path.exists(folder):
        return await message.reply("❌ No songs found for this group.")
    songs = [f for f in os.listdir(folder) if f.endswith(".mp3")]
    if not songs:
        return await message.reply("❌ No audio files found.")

    chosen = random.choice(songs)
    meta_path = os.path.join(folder, chosen + ".json")
    title, artist = os.path.splitext(chosen)[0], "$SQUONK"
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
            title = meta.get("title", title)
            artist = meta.get("artist", "$SQUONK")

    await message.reply_audio(
        open(os.path.join(folder, chosen), "rb"),
        title=title,
        performer=artist,
        caption="🎶 Squonking time!",
        reply_markup=get_keyboard()
    )

@dp.message_handler(commands=["playlist"])
async def playlist(message: types.Message):
    group_id = str(message.chat.id)
    folder = os.path.join(SONGS_FOLDER, group_id)
    if not os.path.exists(folder):
        return await message.reply("❌ No songs found.")
    songs = [f for f in os.listdir(folder) if f.endswith(".mp3")]
    if not songs:
        return await message.reply("❌ Playlist is empty.")

    kb = InlineKeyboardMarkup(row_width=1)
    text = "🎵 Playlist:
"
    for f in songs:
        meta_path = os.path.join(folder, f + ".json")
        title = os.path.splitext(f)[0]
        if os.path.exists(meta_path):
            with open(meta_path) as meta:
                m = json.load(meta)
                title = m.get("title", title)
        text += f"• {title}
"
        kb.add(InlineKeyboardButton(f"▶️ {title}", callback_data=f"play:{f}"))
    await message.reply(text, reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("play:"))
async def callback_play_specific(call: types.CallbackQuery):
    group_id = str(call.message.chat.id)
    song_file = call.data.split(":", 1)[1]
    folder = os.path.join(SONGS_FOLDER, group_id)
    path = os.path.join(folder, song_file)
    meta_path = path + ".json"
    title, artist = os.path.splitext(song_file)[0], "$SQUONK"
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
            title = meta.get("title", title)
            artist = meta.get("artist", "$SQUONK")

    await bot.send_audio(
        call.message.chat.id,
        open(path, "rb"),
        title=title,
        performer=artist,
        caption="🎧 Playing selected track!",
        reply_markup=get_keyboard()
    )
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "next")
async def callback_buttons(call: types.CallbackQuery):
    group_id = str(call.message.chat.id)
    folder = os.path.join(SONGS_FOLDER, group_id)
    songs = [f for f in os.listdir(folder) if f.endswith(".mp3")]
    if not songs:
        return await call.answer("❌ No songs available.", show_alert=True)

    chosen = random.choice(songs)
    meta_path = os.path.join(folder, chosen + ".json")
    title, artist = os.path.splitext(chosen)[0], "$SQUONK"
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
            title = meta.get("title", title)
            artist = meta.get("artist", "$SQUONK")

    await bot.send_audio(
        call.message.chat.id,
        open(os.path.join(folder, chosen), "rb"),
        title=title,
        performer=artist,
        caption="▶️ Next beat!",
        reply_markup=get_keyboard()
    )
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "playlist")
async def callback_playlist(call: types.CallbackQuery):
    await playlist(call.message)
    await call.answer()
