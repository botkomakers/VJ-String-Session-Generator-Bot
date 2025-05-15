# video.py - Part 1

import os
import aiohttp
import asyncio
import traceback
import datetime
import time
import yt_dlp
import threading
import hashlib
import mimetypes
import subprocess
import json
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from config import LOG_CHANNEL, OWNER_ID

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]
MAX_SIZE = 1.9 * 1024 * 1024 * 1024  # 1.9 GB
active_tasks = set()
cache_dir = "/tmp/cache"
os.makedirs(cache_dir, exist_ok=True)

def hash_url(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()

def is_video(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    mime = mimetypes.guess_type(filename)[0]
    return ext in VIDEO_EXTENSIONS or (mime and "video" in mime)

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
            ["ffmpeg", "-i", file_path, "-ss", "00:00:02", "-vframes", "1", output_thumb],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return output_thumb if os.path.exists(output_thumb) else None
    except Exception:
        return None

async def auto_cleanup(path=cache_dir, max_age=900):
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

@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def handle_links(bot: Client, message: Message):
    urls = [x for x in message.text.strip().split() if x.lower().startswith("http")]
    if not urls:
        return await message.reply_text("No valid links found.")

    for url in urls:
        task_id = hash_url(url)
        if task_id in active_tasks:
            await message.reply_text("This link is already being processed. Please wait...")
            continue

        active_tasks.add(task_id)
        asyncio.create_task(process_url(bot, message, url, task_id))

# video.py - Part 2 (Download + Upload + Logging)

async def download_with_ytdlp(url: str, download_dir=cache_dir):
    ydl_opts = {
        "outtmpl": os.path.join(download_dir, "%(title).70s_%(id)s.%(ext)s"),
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "retries": 3,
    }
    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=True))
        filepath = yt_dlp.YoutubeDL(ydl_opts).prepare_filename(info)
        return filepath, info
    except Exception as e:
        raise Exception(f"yt-dlp error: {e}")

async def process_url(bot: Client, message: Message, url: str, task_id: str):
    status = await message.reply_text("🔄 Processing your link...")
    filepath = None

    try:
        filepath, info = await download_with_ytdlp(url)
        if not os.path.exists(filepath):
            raise Exception("Download failed or file not found!")

        size = os.path.getsize(filepath)
        if size > MAX_SIZE:
            await status.edit(f"⚠️ File too large: {format_bytes(size)} (limit: 1.9 GB)")
            return

        caption = f"**Title:** {info.get('title')}\n**Duration:** {round(info.get('duration', 0)/60)} min\n[Source Link]({url})"
        thumb = generate_thumbnail(filepath)

        await status.edit("📤 Uploading...")

        if is_video(filepath):
            await message.reply_video(
                video=filepath,
                caption=caption,
                thumb=thumb if thumb else None,
                supports_streaming=True
            )
        else:
            await message.reply_document(
                document=filepath,
                caption=caption
            )

        await status.delete()

        log_text = (
            f"**New Download Log**\n\n"
            f"👤 User: {message.from_user.mention} (`{message.from_user.id}`)\n"
            f"🔗 Link: `{url}`\n"
            f"🎬 File: `{os.path.basename(filepath)}`\n"
            f"💾 Size: `{format_bytes(size)}`\n"
            f"🕰 Time: `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
        )
        await bot.send_message(LOG_CHANNEL, log_text)

    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await process_url(bot, message, url, task_id)
    except Exception as e:
        traceback.print_exc()
        await status.edit(f"❌ Failed to process:\n**{str(e)}**")
    finally:
        try:
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
            if os.path.exists("/tmp/thumb.jpg"):
                os.remove("/tmp/thumb.jpg")
            await auto_cleanup()
        except Exception:
            pass
        active_tasks.discard(task_id)






# video.py - Part 3 (Queue, Throttle, Cancel, Stats)

from pyrogram.enums import ChatAction
from config import OWNER_ID

download_queue = []
MAX_CONCURRENT_DOWNLOADS = 3
user_stats = {}
retry_limit = 2

@Client.on_message(filters.command("cancel") & filters.private)
async def cancel_task(bot: Client, message: Message):
    user_id = message.from_user.id
    removed = False
    for task in download_queue:
        if task["user_id"] == user_id:
            download_queue.remove(task)
            removed = True
            break
    if removed:
        await message.reply_text("❌ Your queued download was cancelled.")
    else:
        await message.reply_text("No active or queued task found.")

@Client.on_message(filters.command("stats") & filters.private & filters.user(OWNER_ID))
async def stats(bot: Client, message: Message):
    total_downloads = sum(user_stats.values())
    text = f"📊 **Bot Statistics**\n\n"
    text += f"👥 Active Users: `{len(user_stats)}`\n"
    text += f"⬇️ Total Downloads: `{total_downloads}`\n"
    text += f"📚 Queue Length: `{len(download_queue)}`\n"
    await message.reply_text(text)

async def process_queue(bot: Client):
    while True:
        if len(active_tasks) < MAX_CONCURRENT_DOWNLOADS and download_queue:
            task = download_queue.pop(0)
            user_id = task["user_id"]
            try_count = task.get("tries", 0)
            if try_count >= retry_limit:
                await bot.send_message(user_id, "❌ Download failed after multiple retries.")
                continue
            task["tries"] = try_count + 1
            asyncio.create_task(process_url(bot, task["message"], task["url"], task["task_id"]))
        await asyncio.sleep(2)

@Client.on_message(filters.private & filters.text & ~filters.command(["start", "cancel", "stats"]))
async def handle_links(bot: Client, message: Message):
    urls = [x for x in message.text.strip().split() if x.lower().startswith("http")]
    if not urls:
        return await message.reply_text("No valid links found.")

    for url in urls:
        task_id = hash_url(url)
        if task_id in active_tasks:
            await message.reply_text("⏳ Already processing this link. Please wait...")
            continue

        user_id = message.from_user.id
        user_stats[user_id] = user_stats.get(user_id, 0)

        priority = 0
        if user_id == OWNER_ID:
            priority = 2

        task = {
            "user_id": user_id,
            "url": url,
            "message": message,
            "task_id": task_id,
            "priority": priority,
            "tries": 0
        }

        if priority > 0:
            download_queue.insert(0, task)
        else:
            download_queue.append(task)

        await message.reply_text("✅ Your download is queued. It will be processed shortly.")

# Start queue processing on bot startup
async def start_queue(bot: Client):
    asyncio.create_task(process_queue(bot))







# video.py - Part 4 (Premium, Split Upload, Smart Detection, Progress)

from config import PREMIUM_USERS
from pyrogram.types import InputMediaVideo
from utils.progress import progress_for_pyrogram
from utils.splitter import split_video_by_size
import mimetypes

SUPPORTED_DOMAINS = ["youtube.com", "youtu.be", "tiktok.com", "facebook.com", "instagram.com", "vimeo.com"]

def detect_platform(url: str):
    for domain in SUPPORTED_DOMAINS:
        if domain in url:
            return domain.split(".")[0].capitalize()
    return "Unknown"

async def upload_file(bot: Client, message: Message, filepath: str, caption: str, thumb: str = None):
    file_size = os.path.getsize(filepath)
    if file_size <= MAX_SIZE:
        if is_video(filepath):
            await message.reply_chat_action(ChatAction.UPLOAD_VIDEO)
            await message.reply_video(
                video=filepath,
                caption=caption,
                thumb=thumb,
                supports_streaming=True,
                progress=progress_for_pyrogram,
                progress_args=("Uploading...", message)
            )
        else:
            await message.reply_document(
                document=filepath,
                caption=caption,
                progress=progress_for_pyrogram,
                progress_args=("Uploading...", message)
            )
    else:
        # File splitting
        parts = await split_video_by_size(filepath, MAX_SIZE)
        if not parts:
            return await message.reply_text("❌ Failed to split large file.")
        await message.reply_text(f"📦 File too large. Sending as {len(parts)} parts...")

        for part in parts:
            if is_video(part):
                await message.reply_video(
                    video=part,
                    caption="(Split Part)",
                    thumb=generate_thumbnail(part),
                    supports_streaming=True,
                    progress=progress_for_pyrogram,
                    progress_args=("Uploading part...", message)
                )
            else:
                await message.reply_document(
                    document=part,
                    caption="(Split Part)",
                    progress=progress_for_pyrogram,
                    progress_args=("Uploading part...", message)
                )

async def process_url(bot: Client, message: Message, url: str, task_id: str):
    processing_msg = await message.reply_text("⚙️ Processing your link...")
    filepath = None

    try:
        user_id = message.from_user.id
        is_premium = user_id in PREMIUM_USERS or user_id == OWNER_ID

        domain = detect_platform(url)
        await processing_msg.edit(f"🔎 Detected Platform: **{domain}**\nDownloading...")

        filepath, info = await asyncio.to_thread(download_with_ytdlp, url)

        if not os.path.exists(filepath):
            raise Exception("File not found after download.")

        user_stats[user_id] = user_stats.get(user_id, 0) + 1
        file_size = os.path.getsize(filepath)
        caption = f"**Downloaded From:** {url}\n**Size:** {format_bytes(file_size)}"

        if not is_premium and file_size > 1024 * 1024 * 1024:  # 1 GB limit for normal users
            await processing_msg.edit("⚠️ File too large for free users. Please upgrade to premium.")
            return

        await processing_msg.edit("📤 Uploading...")
        thumb = generate_thumbnail(filepath)
        await upload_file(bot, message, filepath, caption, thumb)
        await processing_msg.delete()

        await bot.send_message(LOG_CHANNEL, f"✅ {message.from_user.mention} downloaded a video:\n{url}")

    except FloodWait as e:
        await asyncio.sleep(e.value)
        await process_url(bot, message, url, task_id)
    except Exception as e:
        traceback.print_exc()
        await processing_msg.edit(f"❌ Failed: {str(e)}")
    finally:
        try:
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
            if os.path.exists("/tmp/thumb.jpg"):
                os.remove("/tmp/thumb.jpg")
            await auto_cleanup()
        except:
            pass
        active_tasks.discard(task_id)














# video.py - Part 5 (Auto Caption, Tag System, Retry, Logger)

import re
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def generate_caption(info):
    title = info.get("title", "No Title")
    duration = format_duration(info.get("duration", 0))
    quality = info.get("format", "Unknown")
    ext = info.get("ext", "mp4")

    caption = (
        f"**🎬 Title:** `{title}`\n"
        f"**⏱ Duration:** `{duration}`\n"
        f"**📺 Quality:** `{quality}`\n"
        f"**📁 Format:** `{ext}`"
    )
    return caption

def generate_tags(info):
    tags = [info.get("title", "").split()[0].lower()]
    if "music" in info.get("categories", []):
        tags.append("music")
    if info.get("duration", 0) > 600:
        tags.append("long")
    return tags

def format_duration(seconds):
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}:{minutes:02}:{sec:02}"
    else:
        return f"{minutes}:{sec:02}"

async def safe_download_with_retry(url: str, retries: int = 3, backoff: int = 5):
    for attempt in range(1, retries + 1):
        try:
            return await asyncio.to_thread(download_with_ytdlp, url)
        except Exception as e:
            if attempt == retries:
                raise e
            await asyncio.sleep(backoff * attempt)

def lang_detect(text: str):
    bangla_chars = re.findall(r'[\u0980-\u09FF]', text)
    return "bn" if bangla_chars else "en"

def get_language_text(key: str, lang: str = "en"):
    en = {
        "start": "👋 Hello! Send me a link and I’ll download the video for you.",
        "processing": "⏳ Processing your link...",
        "downloading": "⬇️ Downloading video...",
        "uploading": "📤 Uploading...",
        "error": "❌ Error occurred!",
    }
    bn = {
        "start": "👋 হ্যালো! একটি লিংক পাঠান, আমি ভিডিওটি ডাউনলোড করে দেব।",
        "processing": "⏳ আপনার লিংক প্রসেস করা হচ্ছে...",
        "downloading": "⬇️ ভিডিও ডাউনলোড হচ্ছে...",
        "uploading": "📤 আপলোড করা হচ্ছে...",
        "error": "❌ একটি সমস্যা হয়েছে!",
    }
    return bn.get(key, key) if lang == "bn" else en.get(key, key)

def get_inline_tags(tags):
    buttons = [
        [InlineKeyboardButton(f"#{tag}", url="https://t.me/YourBot?start=tag_" + tag)]
        for tag in tags
    ]
    return InlineKeyboardMarkup(buttons)

async def process_url(bot: Client, message: Message, url: str, task_id: str):
    user_id = message.from_user.id
    lang = lang_detect(message.text or "")
    processing_msg = await message.reply_text(get_language_text("processing", lang))

    filepath = None
    try:
        domain = detect_platform(url)
        await processing_msg.edit(get_language_text("downloading", lang))

        filepath, info = await safe_download_with_retry(url, retries=3, backoff=6)

        if not os.path.exists(filepath):
            raise Exception("File not found.")

        caption = generate_caption(info)
        tags = generate_tags(info)
        thumb = generate_thumbnail(filepath)

        await processing_msg.edit(get_language_text("uploading", lang))
        await upload_file(bot, message, filepath, caption, thumb)
        await message.reply_text("✅ Done!", reply_markup=get_inline_tags(tags))

        await bot.send_message(LOG_CHANNEL, f"✅ Video Downloaded by `{user_id}`\nURL: {url}")

    except Exception as e:
        await processing_msg.edit(f"{get_language_text('error', lang)}\n`{str(e)}`")
        await bot.send_message(LOG_CHANNEL, f"❌ Error for `{user_id}`\nURL: {url}\nError: `{str(e)}`")
    finally:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
        active_tasks.discard(task_id)












# video.py - Part 6 (AI Summary, Bookmark, Background Queue, Admin Panel)

from pyrogram.enums import ChatAction
from datetime import datetime
from collections import defaultdict

queue = asyncio.Queue()
user_bookmarks = defaultdict(list)

async def ai_summarize(title: str, desc: str = ""):
    summary = f"**Summary for**: `{title}`\n"
    if desc:
        summary += f"\n➤ {desc[:300]}..."
    else:
        summary += "\n➤ No detailed description found."
    return summary

async def handle_bookmark(bot, message, title, url):
    user_id = message.from_user.id
    entry = {"title": title, "url": url, "time": datetime.now().isoformat()}
    user_bookmarks[user_id].append(entry)
    await message.reply_text("🔖 Saved to bookmarks!")

async def show_bookmarks(bot, message):
    user_id = message.from_user.id
    bookmarks = user_bookmarks.get(user_id, [])
    if not bookmarks:
        return await message.reply_text("📭 No bookmarks yet.")
    
    text = "**Your Bookmarks:**\n\n"
    for b in bookmarks[-10:]:
        text += f"• [{b['title']}]({b['url']}) — `{b['time'].split('T')[0]}`\n"
    await message.reply_text(text, disable_web_page_preview=True)

async def background_worker(bot):
    while True:
        message, url = await queue.get()
        try:
            await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
            await process_url(bot, message, url, task_id=str(uuid.uuid4()))
        except Exception as e:
            await message.reply_text(f"Background task failed: `{str(e)}`")
        queue.task_done()

async def queue_task(bot, message, url):
    await message.reply_text("🕓 Added to background queue. You’ll be notified when done.")
    await queue.put((message, url))

async def show_admin_stats(bot, message):
    total_users = await db.total_users()
    active_now = len(active_tasks)
    queued = queue.qsize()
    uptime = datetime.now() - bot.start_time

    text = (
        f"**📊 Bot Stats:**\n\n"
        f"• Total Users: `{total_users}`\n"
        f"• Active Downloads: `{active_now}`\n"
        f"• Queue Pending: `{queued}`\n"
        f"• Uptime: `{str(uptime).split('.')[0]}`"
    )
    await message.reply_text(text)

def fast_upload_kwargs(filepath):
    ext = filepath.split(".")[-1]
    use_cdn = ext in ["mp4", "mkv", "mov"]
    return {"video": filepath} if use_cdn else {"document": filepath}








# video.py - Part 7 (Queue Tracking, Cancel, Premium, Blur Thumbnail)

import uuid
from PIL import Image, ImageFilter

user_tasks = {}  # user_id: task_id

async def notify_queue_position(bot, message):
    pos = queue.qsize()
    await message.reply_text(f"🪄 You're number `{pos+1}` in the queue. Please wait...")

@Client.on_message(filters.command("cancel") & filters.private)
async def cancel_download(bot, message):
    uid = message.from_user.id
    task_id = user_tasks.get(uid)
    if not task_id:
        return await message.reply_text("❌ No active download found to cancel.")
    
    if task_id in active_tasks:
        active_tasks.remove(task_id)
        await message.reply_text("✅ Your download task was cancelled.")
    else:
        await message.reply_text("⚠️ Your task is not running anymore.")

def blur_thumbnail(image_path):
    try:
        img = Image.open(image_path)
        blurred = img.filter(ImageFilter.GaussianBlur(12))
        output_path = image_path.replace(".jpg", "_blur.jpg")
        blurred.save(output_path)
        return output_path
    except:
        return image_path

def check_admin(user_id):
    return str(user_id) == str(OWNER_ID)

def apply_priority(user_id):
    return 0 if check_admin(user_id) else 1

async def virus_scan_stub(filepath):
    # Example placeholder scan — always safe
    return "✅ Safe to upload (simulated scan passed)."












# video.py - Part 8 (Rename, Retry, Chart, Smart Caption, Inline)

import random
import math
from PIL import ImageDraw, ImageFont
from pyrogram.types import InlineQueryResultArticle, InputTextMessageContent

RETRY_LIMIT = 3

async def retry_upload(func, *args, **kwargs):
    for i in range(RETRY_LIMIT):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            if i == RETRY_LIMIT - 1:
                raise e
            await asyncio.sleep(2 * (i + 1))

def smart_caption(info, url):
    title = info.get("title", "Video")
    uploader = info.get("uploader", "")
    tags = ", ".join(info.get("tags", [])[:5]) if "tags" in info else ""
    duration = info.get("duration", 0)
    mins = math.floor(duration / 60)
    secs = duration % 60
    return (
        f"**🎬 Title:** {title}\n"
        f"**📺 Uploader:** {uploader}\n"
        f"**🕒 Duration:** {mins}:{secs:02d} mins\n"
        f"**🏷 Tags:** {tags}\n"
        f"**🔗 Source:** [Click to Watch]({url})"
    )

def draw_chart(filepath, info):
    from matplotlib import pyplot as plt
    labels = ['Video Size', 'Duration (sec)', 'Bitrate']
    sizes = [
        os.path.getsize(filepath) / (1024 * 1024),
        info.get("duration", 1),
        info.get("abr", 128)
    ]
    colors = ['gold', 'skyblue', 'lightcoral']
    plt.figure(figsize=(5,5))
    plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=140)
    plt.axis('equal')
    chart_path = "/tmp/chart.jpg"
    plt.savefig(chart_path)
    return chart_path

@Client.on_message(filters.command("inline") & filters.private)
async def inline_example(bot, message):
    await message.reply_text("Type `@YourBotUsername <query>` in any chat to search inline!")

@Client.on_inline_query()
async def inline_query_handler(bot, query):
    results = [
        InlineQueryResultArticle(
            title="Video Downloader Bot",
            description="Paste a video link to download",
            input_message_content=InputTextMessageContent(
                message_text="Send me a video link to start downloading!"
            )
        )
    ]
    await query.answer(results, cache_time=1)
















# video.py - Part 9 (Voice, Broadcast, Blacklist, Bookmark, Daily Limit)

from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from config import OWNER_ID, MONGO_DB_URI
from io import BytesIO

client = MongoClient(MONGO_DB_URI)
db = client.botdb
blacklist = db.blacklist
bookmarks = db.bookmarks
limits = db.limits

DAILY_LIMIT = 5

# --- Blacklist System ---
def is_blacklisted(url):
    return blacklist.find_one({"url": url})

@Client.on_message(filters.command("blacklist") & filters.user(OWNER_ID))
async def add_blacklist(_, m):
    if len(m.command) < 2:
        return await m.reply("Give a link to blacklist.")
    link = m.command[1]
    blacklist.update_one({"url": link}, {"$set": {"url": link}}, upsert=True)
    await m.reply("✅ Blacklisted.")

# --- Bookmark System ---
@Client.on_message(filters.command("save"))
async def save_bookmark(_, m):
    if not m.reply_to_message or not m.reply_to_message.document and not m.reply_to_message.video:
        return await m.reply("Reply to a file to save.")
    data = {
        "user": m.from_user.id,
        "file_id": m.reply_to_message.document.file_id if m.reply_to_message.document else m.reply_to_message.video.file_id,
        "type": "doc" if m.reply_to_message.document else "vid"
    }
    bookmarks.insert_one(data)
    await m.reply("✅ Saved to bookmarks.")

@Client.on_message(filters.command("bookmarks"))
async def list_bookmarks(_, m):
    bms = list(bookmarks.find({"user": m.from_user.id}))
    if not bms:
        return await m.reply("No bookmarks found.")
    for b in bms:
        if b["type"] == "vid":
            await m.reply_video(b["file_id"])
        else:
            await m.reply_document(b["file_id"])

# --- Daily Download Limit ---
def increment_limit(user_id):
    today = datetime.date.today().isoformat()
    user = limits.find_one({"user": user_id})
    if user and user.get("date") == today:
        if user["count"] >= DAILY_LIMIT:
            return False
        limits.update_one({"user": user_id}, {"$inc": {"count": 1}})
        return True
    else:
        limits.update_one({"user": user_id}, {"$set": {"date": today, "count": 1}}, upsert=True)
        return True

# --- Voice Message ---
def convert_to_voice(filepath):
    out = "/tmp/audio.ogg"
    cmd = f'ffmpeg -i "{filepath}" -vn -acodec libopus -b:a 64k -y "{out}"'
    os.system(cmd)
    return out

@Client.on_message(filters.command("voice") & filters.user(OWNER_ID))
async def voice_extract(_, m):
    if not m.reply_to_message or not m.reply_to_message.video:
        return await m.reply("Reply to a video to convert to voice.")
    path = await m.reply_to_message.download()
    voice = convert_to_voice(path)
    await m.reply_voice(voice)
    os.remove(path)
    os.remove(voice)

# --- Admin Broadcast ---
BROADCAST = {}

@Client.on_message(filters.command("broadcast") & filters.user(OWNER_ID))
async def ask_broadcast(_, m):
    BROADCAST[m.chat.id] = True
    await m.reply("Send the message to broadcast.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_broadcast")]]))

@Client.on_message(filters.private & filters.user(OWNER_ID))
async def send_broadcast(bot, m):
    if BROADCAST.get(m.chat.id):
        users = [u["user_id"] for u in db.users.find()]
        count = 0
        for uid in users:
            try:
                await bot.copy_message(uid, m.chat.id, m.id)
                count += 1
            except:
                continue
        BROADCAST.pop(m.chat.id)
        await m.reply(f"✅ Broadcasted to {count} users.")

@Client.on_callback_query(filters.regex("cancel_broadcast"))
async def cancel_broadcast(_, c):
    BROADCAST.pop(c.message.chat.id, None)
    await c.message.edit("❌ Broadcast cancelled.")






# video.py - Part 10

from langdetect import detect
from concurrent.futures import ThreadPoolExecutor
from pyrogram.types import InputMediaVideo

executor = ThreadPoolExecutor(max_workers=3)

# --- Tag-based search for bookmarks ---
@Client.on_message(filters.command("searchbm"))
async def search_bookmarks(_, m):
    if len(m.command) < 2:
        return await m.reply("Send tags to search bookmarks.")
    tag = m.text.split(None, 1)[1].lower()
    results = bookmarks.find({"tags": {"$regex": tag}})
    count = 0
    async for b in results:
        count += 1
        if b["type"] == "vid":
            await m.reply_video(b["file_id"], caption=f"Tag: {tag}")
        else:
            await m.reply_document(b["file_id"], caption=f"Tag: {tag}")
    if count == 0:
        await m.reply("No bookmarks found for that tag.")

# --- Video trimmer ---
@Client.on_message(filters.command("trim"))
async def video_trim(_, m):
    if not m.reply_to_message or not m.reply_to_message.video:
        return await m.reply("Reply to a video and use /trim start end (seconds)")
    try:
        start, end = map(int, m.text.split()[1:])
    except:
        return await m.reply("Usage: /trim start_seconds end_seconds")
    video_path = await m.reply_to_message.download()
    out_path = f"/tmp/trimmed_{os.path.basename(video_path)}"
    cmd = f'ffmpeg -i "{video_path}" -ss {start} -to {end} -c copy "{out_path}" -y'
    os.system(cmd)
    await m.reply_video(out_path, caption=f"Trimmed: {start}s to {end}s")
    os.remove(video_path)
    os.remove(out_path)

# --- Media compressor ---
@Client.on_message(filters.command("compress"))
async def compress_media(_, m):
    if not m.reply_to_message or not (m.reply_to_message.video or m.reply_to_message.document):
        return await m.reply("Reply to media and send /compress to reduce size.")
    file_path = await m.reply_to_message.download()
    out_path = f"/tmp/compressed_{os.path.basename(file_path)}"
    cmd = f'ffmpeg -i "{file_path}" -vcodec libx264 -crf 28 "{out_path}" -y'
    os.system(cmd)
    await m.reply_video(out_path, caption="Compressed video")
    os.remove(file_path)
    os.remove(out_path)

# --- Auto language detector ---
@Client.on_message(filters.text & ~filters.command)
async def detect_language(_, m):
    try:
        lang = detect(m.text)
        await m.reply(f"Detected language: {lang.upper()}")
    except:
        pass

# --- Parallel multi-link downloader ---
@Client.on_message(filters.command("multidl"))
async def multi_download(bot, m):
    urls = m.text.split()[1:]
    if not urls:
        return await m.reply("Send URLs separated by space.")
    processing_msg = await m.reply("Starting multiple downloads...")

    async def process(url):
        try:
            return await process_url(bot, m, url, hash_url(url))
        except Exception as e:
            return str(e)

    results = await asyncio.gather(*(process(u) for u in urls))
    await processing_msg.edit("All downloads completed.")

# --- User profile info ---
@Client.on_message(filters.command("profile"))
async def profile_info(_, m):
    user = m.from_user
    txt = f"**User Info:**\nName: {user.first_name}\nUserID: {user.id}\nUsername: @{user.username or 'N/A'}"
    await m.reply(txt)

# --- Auto subtitle fetcher ---
@Client.on_message(filters.command("subtitles"))
async def fetch_subtitles(_, m):
    if not m.reply_to_message or not m.reply_to_message.video:
        return await m.reply("Reply to video with /subtitles")
    video_path = await m.reply_to_message.download()
    # placeholder for subtitle fetch (you can integrate yt-dlp subtitle fetch)
    await m.reply("Subtitle fetching not implemented yet.")
    os.remove(video_path)

# --- Link expiry check ---
@Client.on_message(filters.command("checklink"))
async def check_link(_, m):
    if len(m.command) < 2:
        return await m.reply("Send a link to check.")
    url = m.command[1]
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url) as resp:
                status = resp.status
        await m.reply(f"URL Status: {status}")
    except:
        await m.reply("Failed to reach the URL.")

# --- Custom caption ---
@Client.on_message(filters.command("caption"))
async def custom_caption(_, m):
    if not m.reply_to_message:
        return await m.reply("Reply to a media and send /caption Your caption")
    caption = m.text.split(None, 1)[1] if len(m.text.split(None,1)) > 1 else ""
    media = None
    if m.reply_to_message.video:
        media = m.reply_to_message.video.file_id
    elif m.reply_to_message.document:
        media = m.reply_to_message.document.file_id
    if media:
        await m.reply_document(media, caption=caption)
    else:
        await m.reply("Reply to a valid media.")

# --- Thumbnail extractor improved ---
def generate_thumbnail_improved(file_path):
    try:
        import subprocess
        out = "/tmp/thumb.jpg"
        subprocess.run(
            ["ffmpeg", "-i", file_path, "-ss", "00:00:00.500", "-vframes", "1", out],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return out if os.path.exists(out) else None
    except:
        return None

# --- Video resolution info ---
@Client.on_message(filters.command("resolution"))
async def video_resolution(_, m):
    if not m.reply_to_message or not m.reply_to_message.video:
        return await m.reply("Reply to a video with /resolution")
    path = await m.reply_to_message.download()
    import cv2
    vid = cv2.VideoCapture(path)
    width = vid.get(cv2.CAP_PROP_FRAME_WIDTH)
    height = vid.get(cv2.CAP_PROP_FRAME_HEIGHT)
    vid.release()
    await m.reply(f"Resolution: {int(width)}x{int(height)}")
    os.remove(path)

# --- File format converter ---
@Client.on_message(filters.command("convert"))
async def convert_format(_, m):
    if not m.reply_to_message or not (m.reply_to_message.video or m.reply_to_message.document):
        return await m.reply("Reply to a video/document with /convert extension (e.g., mkv)")
    try:
        ext = m.text.split()[1]
    except:
        return await m.reply("Usage: /convert mkv")
    file_path = await m.reply_to_message.download()
    out_path = f"/tmp/converted.{ext}"
    cmd = f'ffmpeg -i "{file_path}" "{out_path}" -y'
    os.system(cmd)
    await m.reply_document(out_path, caption=f"Converted to {ext}")
    os.remove(file_path)
    os.remove(out_path)

# --- Scheduled cleanup ---
async def scheduled_cleanup():
    while True:
        await auto_cleanup()
        await asyncio.sleep(3600)  # every hour

# --- Upload speed throttling (simple sleep) ---
async def throttled_upload(bot, chat_id, file_path, caption):
    CHUNK_SIZE = 512 * 1024  # 512 KB
    with open(file_path, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            await bot.send_chat_action(chat_id, "upload_video")
            await asyncio.sleep(0.5)
    await bot.send_video(chat_id, file_path, caption=caption)

# --- Video metadata editor ---
@Client.on_message(filters.command("editmeta"))
async def edit_metadata(_, m):
    if not m.reply_to_message or not m.reply_to_message.video:
        return await m.reply("Reply to a video with /editmeta Title Artist Album")
    try:
        _, title, artist, album = m.text.split(None, 3)
    except:
        return await m.reply("Usage: /editmeta Title Artist Album")
    video_path = await m.reply_to_message.download()
    out_path = f"/tmp/meta_{os.path.basename(video_path)}"
    cmd = f'ffmpeg -i "{video_path}" -metadata title="{title}" -metadata artist="{artist}" -metadata album="{album}" -codec copy "{out_path}" -y'
    os.system(cmd)
    await m.reply_video(out_path, caption=f"Metadata updated: {title}")
    os.remove(video_path)
    os.remove(out_path)

# --- User feedback ---
@Client.on_message(filters.command("feedback"))
async def feedback(_, m):
    text = m.text.split(None, 1)[1] if len(m.text.split(None,1)) > 1 else ""
    if not text:
        return await m.reply("Send feedback text after /feedback")
    await _.send_message(OWNER_ID, f"Feedback from {m.from_user.mention}:\n{text}")
    await m.reply("Thanks for your feedback!")

# --- Bot stats ---
@Client.on_message(filters.command("stats"))
async def bot_stats(_, m):
    users_count = db.users.count_documents({})
    active = len(active_tasks)
    await m.reply(f"Users: {users_count}\nActive downloads: {active}")

# --- Deep link generator ---
@Client.on_message(filters.command("deeplink"))
async def deep_link(_, m):
    if len(m.command) < 2:
        return await m.reply("Send a username to generate deep link.")
    username = m.command[1].lstrip("@")
    link = f"https://t.me/{username}"
    await m.reply(f"Deep link: {link}")

# --- Download history pagination ---
@Client.on_message(filters.command("history"))
async def download_history(_, m):
    page = int(m.command[1]) if len(m.command) > 1 else 1
    per_page = 5
    skips = per_page * (page - 1)
    docs = list(db.downloads.find().skip(skips).limit(per_page))
    if not