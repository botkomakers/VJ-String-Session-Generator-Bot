import os
import aiohttp
import asyncio
import traceback
import datetime
import time
import yt_dlp
import subprocess
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
from config import LOG_CHANNEL, ADMIN_ID

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]
DEFAULT_THUMB = "default_audio.jpg"  # Ensure this file exists in working directory

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
        subprocess.run(
            ["ffmpeg", "-i", file_path, "-ss", "00:00:01.000", "-vframes", "1", output_thumb],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
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
        text = f"{action}: {progress_text}"
        await message.edit_text(text)
    except:
        pass

async def auto_cleanup(path="/tmp", max_age=300):
    now = time.time()
    for filename in os.listdir(path):
        file_path = os.path.join(path, filename)
        if os.path.isfile(file_path):
            age = now - os.path.getmtime(file_path)
            if age > max_age:
                try:
                    os.remove(file_path)
                except:
                    pass

def is_google_drive_link(url):
    return "drive.google.com" in url

def fix_google_drive_url(url):
    if "uc?id=" in url or "export=download" in url:
        return url
    if "/file/d/" in url:
        file_id = url.split("/file/d/")[1].split("/")[0]
        return f"https://drive.google.com/uc?id={file_id}&export=download"
    return url

def is_mega_link(url):
    return "mega.nz" in url or "mega.co.nz" in url

def get_cookie_file(url):
    if "instagram.com" in url:
        return "cookies/instagram.txt"
    elif "youtube.com" in url or "youtu.be" in url:
        return "cookies/youtube.txt"
    return None

def download_mega_file(url, download_dir="/tmp"):
    from mega import Mega
    mega = Mega()
    m = mega.login()
    file = m.download_url(url, dest_path=download_dir)
    return file.name, {
        "title": file.name,
        "ext": os.path.splitext(file.name)[1].lstrip(".")
    }

def download_with_ytdlp(url, download_dir="/tmp", message=None):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def hook(d):
        if d['status'] == 'downloading' and message:
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            if total:
                asyncio.run_coroutine_threadsafe(
                    progress_callback(downloaded, total, message, "Downloading"),
                    loop
                )

    ydl_opts = {
        "outtmpl": os.path.join(download_dir, "%(title)s.%(ext)s"),
        "format": "best[ext=mp4]/bestaudio/best",
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
        return filename, info

@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def handle_download_request(bot: Client, message: Message):
    if message.from_user.is_bot or message.reply_to_message:
        return
    urls = [url for url in message.text.strip().split() if url.startswith("http")]
    if not urls:
        return await message.reply_text("কোনো বৈধ লিংক পাওয়া যায়নি।")

    for url in urls:
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎥 ভিডিও", callback_data=f"video|{url}"),
             InlineKeyboardButton("🎧 অডিও", callback_data=f"audio|{url}")]
        ])
        await message.reply_text("আপনি কী ডাউনলোড করতে চান?", reply_markup=buttons)

@Client.on_callback_query()
async def handle_choice(bot: Client, query: CallbackQuery):
    data = query.data
    if data.startswith("delete_"):
        try:
            await bot.delete_messages(query.message.chat.id, query.message.id)
            await query.answer("ডিলিট করা হয়েছে।", show_alert=False)
        except:
            await query.answer("ডিলিট করা যায়নি।", show_alert=True)
        return

    try:
        action, url = data.split("|", 1)
        await query.answer()
        msg = await query.message.edit_text(f"{action.capitalize()} ডাউনলোড শুরু হচ্ছে...")

        if is_google_drive_link(url):
            url = fix_google_drive_url(url)

        if is_mega_link(url):
            filepath, info = await asyncio.to_thread(download_mega_file, url)
            filepath = os.path.join("/tmp", filepath)
        else:
            filepath, info = await asyncio.to_thread(download_with_ytdlp, url, "/tmp", msg)

        if not os.path.exists(filepath):
            raise Exception("ডাউনলোড ব্যর্থ হয়েছে।")

        ext = os.path.splitext(filepath)[1].lower()
        caption = (
            "**⚠️ এই ফাইল ৫ মিনিট পর স্বয়ংক্রিয়ভাবে মুছে যাবে!**\n\n"
            "ফাইলটি সংরক্ষণ করতে চাইলে এটি আপনার **Saved Messages**-এ ফরোয়ার্ড করুন।\n\n"
            f"[Source Link]({url})"
        )
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Source Link", url=url)],
            [InlineKeyboardButton("❌ Delete Now", callback_data=f"delete_{query.message.id}")]
        ])

        thumb = generate_thumbnail(filepath) or (DEFAULT_THUMB if os.path.exists(DEFAULT_THUMB) else None)

        if action == "audio":
            audio_path = filepath.rsplit(".", 1)[0] + ".mp3"
            os.system(f'ffmpeg -i "{filepath}" -vn -ab 128k -ar 44100 -y "{audio_path}"')
            await query.message.reply_audio(
                audio=audio_path,
                caption=caption,
                thumb=thumb,
                reply_markup=buttons
            )
            os.remove(audio_path)
        else:
            if ext in VIDEO_EXTENSIONS:
                await query.message.reply_video(
                    video=filepath,
                    caption=caption,
                    thumb=thumb,
                    supports_streaming=True,
                    reply_markup=buttons
                )
            else:
                await query.message.reply_document(
                    document=filepath,
                    caption=caption,
                    reply_markup=buttons
                )

        await msg.delete()
        asyncio.create_task(auto_delete_message(bot, query.message.chat.id, query.message.id, 300))

        user = query.from_user
        file_size = format_bytes(os.path.getsize(filepath))
        log_text = (
            f"**New Download Event**\n\n"
            f"**User:** {user.mention} (`{user.id}`)\n"
            f"**Link:** `{url}`\n"
            f"**File Name:** `{os.path.basename(filepath)}`\n"
            f"**Size:** `{file_size}`\n"
            f"**Type:** `{action}`\n"
            f"**Time:** `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
        )

        if action == "video" and ext in VIDEO_EXTENSIONS:
            await bot.send_video(LOG_CHANNEL, video=filepath, caption=log_text, thumb=thumb, supports_streaming=True)
        else:
            await bot.send_document(LOG_CHANNEL, document=filepath, caption=log_text)

        if any(x in url.lower() for x in ["porn", "sex", "xxx"]):
            alert = f"⚠️ **Porn link detected**\n**User:** {user.mention} (`{user.id}`)\n**Link:** {url}"
            await bot.send_message(ADMIN_ID, alert)

        if os.path.exists(filepath):
            os.remove(filepath)
        if os.path.exists("/tmp/thumb.jpg"):
            os.remove("/tmp/thumb.jpg")
        await auto_cleanup()

    except Exception as e:
        traceback.print_exc()
        await query.message.reply_text(f"❌ ডাউনলোডে সমস্যা হয়েছে:\n{e}")

async def auto_delete_message(bot, chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try:
        await bot.delete_messages(chat_id, message_id)
    except:
        pass