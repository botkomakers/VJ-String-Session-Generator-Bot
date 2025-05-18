import os
import aiohttp
import asyncio
import traceback
import datetime
import time
import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
from config import LOG_CHANNEL, ADMIN_ID
from db import add_premium, remove_premium, is_premium, list_premium_users
from collections import deque

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]
AUDIO_EXTENSIONS = [".mp3", ".m4a", ".webm", ".aac", ".ogg"]
DEFAULT_THUMB = "https://i.ibb.co/Xk4Hbg8h/photo-2025-05-07-15-52-21-7505459490108473348.jpg"

queue = deque()
processing_users = set()
MAX_PROCESS = 10

def format_bytes(size):
    power = 1024
    n = 0
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    while size > power and n < len(units) - 1:
        size /= power
        n += 1
    return f"{size:.2f} {units[n]}"

def generate_thumbnail(file_path, output_thumb="/tmp/thumb.jpg"):
    try:
        import subprocess
        subprocess.run(["ffmpeg", "-i", file_path, "-ss", "00:00:01.000", "-vframes", "1", output_thumb],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_thumb if os.path.exists(output_thumb) else None
    except:
        return None

def make_progress_bar(current, total, length=20):
    percent = current / total
    filled_length = int(length * percent)
    bar = '■' * filled_length + '▩' + '□' * (length - filled_length - 1)
    return f"{int(percent * 100)}%\n{bar}"

async def progress_callback(current, total, message: Message, action="Downloading"):
    try:
        progress_text = make_progress_bar(current, total)
        await message.edit_text(f"{action}: {progress_text}")
    except:
        pass

async def auto_cleanup(path="/tmp", max_age=300):
    now = time.time()
    for filename in os.listdir(path):
        file_path = os.path.join(path, filename)
        if os.path.isfile(file_path) and now - os.path.getmtime(file_path) > max_age:
            try:
                os.remove(file_path)
            except:
                pass

def get_cookie_file(url):
    if "instagram.com" in url:
        return "cookies/instagram.txt"
    elif "youtube.com" in url or "youtu.be" in url:
        return "cookies/youtube.txt"
    return None

def is_direct_link(url):
    return url.lower().endswith(tuple(VIDEO_EXTENSIONS + AUDIO_EXTENSIONS))

def download_with_ytdlp(url, download_dir="/tmp", message=None, audio_only=False):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def hook(d):
        if d['status'] == 'downloading' and message:
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            if total:
                asyncio.run_coroutine_threadsafe(progress_callback(downloaded, total, message, "Downloading"), loop)

    ydl_opts = {
        "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
        "format": "bestaudio/best" if audio_only else "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "progress_hooks": [hook]
    }

    cookie_file = get_cookie_file(url)
    if cookie_file and os.path.exists(cookie_file):
        ydl_opts["cookiefile"] = cookie_file

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if audio_only and not filename.endswith(".mp3"):
            audio_file = filename.rsplit(".", 1)[0] + ".mp3"
            os.system(f"ffmpeg -i '{filename}' -vn -ab 128k -ar 44100 -y '{audio_file}'")
            os.remove(filename)
            filename = audio_file
        return filename, info

@Client.on_message(filters.command("add_premium"))
async def add_premium_cmd(bot, message):
    if message.from_user.id != ADMIN_ID:
        return
    if not message.reply_to_message:
        return await message.reply("Reply to user to add.")
    add_premium(message.reply_to_message.from_user.id)
    await message.reply("User added to premium list.")

@Client.on_message(filters.command("remove_premium"))
async def remove_premium_cmd(bot, message):
    if message.from_user.id != ADMIN_ID:
        return
    if not message.reply_to_message:
        return await message.reply("Reply to user to remove.")
    remove_premium(message.reply_to_message.from_user.id)
    await message.reply("User removed from premium list.")

@Client.on_message(filters.command("premium_list"))
async def premium_list_cmd(bot, message):
    if message.from_user.id != ADMIN_ID:
        return
    premium_users = list_premium()
    await message.reply("Premium Users:\n" + "\n".join(map(str, premium_users)))

@Client.on_message(filters.private & ~filters.command("start"))
async def handle_link(bot: Client, message: Message):
    if message.from_user.is_bot or not message.text:
        return

    url = message.text.strip().split()[0]
    user_id = message.from_user.id

    if len(processing_users) >= MAX_PROCESS and not is_premium(user_id):
        return await message.reply(
            "⚠️ Already 10/10 Process Running\n\n"
            "👉 Bot is Overloaded. So, Try after a few minutes.\n"
            "Interested users can Upgrade to Paid Bot, To avoid Waiting Time and Process limits. @MultiUsageBot"
        )

    if is_direct_link(url):
        mode = "audio" if url.lower().endswith(tuple(AUDIO_EXTENSIONS)) else "video"
        return await start_download(bot, message, url, mode)

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("Video", callback_data=f"video|{url}"),
         InlineKeyboardButton("Audio", callback_data=f"audio|{url}")]
    ])
    await message.reply("Do you want to download as Video or Audio?", reply_markup=buttons)

@Client.on_callback_query()
async def handle_callback(bot: Client, cb: CallbackQuery):
    data = cb.data
    if "|" not in data:
        return
    mode, url = data.split("|", 1)
    await cb.message.delete()
    await start_download(bot, cb.message, url, mode)

async def start_download(bot, message, url, mode):
    user_id = message.from_user.id
    processing_users.add(user_id)
    filepath = None
    try:
        status = await message.reply("Starting download...")
        filepath, info = await asyncio.to_thread(download_with_ytdlp, url, "/tmp", status, mode == 'audio')

        if not os.path.exists(filepath):
            raise Exception("File not found.")

        thumb = generate_thumbnail(filepath)
        if not thumb and filepath.endswith(tuple(AUDIO_EXTENSIONS)):
            thumb = DEFAULT_THUMB

        caption = (
            "⚠️ This file will be automatically deleted in 5 minutes!\n\n"
            "Please save this file by forwarding it to your Saved Messages."
        )

        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Source Link", url=url)]
        ])

        if filepath.endswith(tuple(VIDEO_EXTENSIONS)):
            sent = await message.reply_video(
                video=filepath,
                caption=caption,
                thumb=thumb if os.path.exists(str(thumb)) else None,
                supports_streaming=True,
                reply_markup=buttons
            )
        else:
            sent = await message.reply_document(
                document=filepath,
                caption=caption,
                thumb=thumb if os.path.exists(str(thumb)) else None,
                reply_markup=buttons
            )

        await status.delete()
        asyncio.create_task(auto_delete_message(bot, sent.chat.id, sent.id, 300))

        user = message.from_user
        file_size = format_bytes(os.path.getsize(filepath))
        log = (
            f"New Download\nUser: {user.mention} ({user.id})\nURL: {url}\n"
            f"Name: {os.path.basename(filepath)}\nSize: {file_size}\n"
            f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        await bot.send_document(LOG_CHANNEL, document=filepath, caption=log)

        if any(x in url.lower() for x in ["porn", "sex", "xxx"]):
            await bot.send_message(ADMIN_ID, f"⚠️ Porn Link Alert:\n{user.mention} ({user.id})\n{url}")

    except Exception as e:
        traceback.print_exc()
        await message.reply_text(f"❌ Failed to download:\n{url}\n\n**{e}**")
    finally:
        processing_users.discard(user_id)
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
        if os.path.exists("/tmp/thumb.jpg"):
            os.remove("/tmp/thumb.jpg")
        await auto_cleanup()

async def auto_delete_message(bot, chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try:
        await bot.delete_messages(chat_id, message_id)
    except:
        pass




@Client.on_message(filters.command("add_premium") & filters.user(ADMIN_ID))
async def add_premium_user(bot, message):
    if len(message.command) < 2:
        return await message.reply("Usage: /add_premium <user_id>")
    user_id = int(message.command[1])
    add_premium(user_id)
    await message.reply(f"✅ Added {user_id} as Premium.")

@Client.on_message(filters.command("remove_premium") & filters.user(ADMIN_ID))
async def remove_premium_user(bot, message):
    if len(message.command) < 2:
        return await message.reply("Usage: /remove_premium <user_id>")
    user_id = int(message.command[1])
    remove_premium(user_id)
    await message.reply(f"❌ Removed {user_id} from Premium.")

@Client.on_message(filters.command("premium_list") & filters.user(ADMIN_ID))
async def list_premium(bot, message):
    users = list_premium_users()
    await message.reply("👑 Premium Users:\n" + "\n".join([str(u) for u in users]) or "No premium users.")