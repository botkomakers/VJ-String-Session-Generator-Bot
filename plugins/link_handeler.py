import os
import aiohttp
import asyncio
import traceback
import subprocess
import json
from pyrogram import Client, filters
from pyrogram.types import Message
from urllib.parse import urlparse
from pymongo import MongoClient
from datetime import datetime, timedelta
from config import MONGO_DB_URI  # Import MongoDB URI from config

# MongoDB কনফিগারেশন
client = MongoClient(MONGO_DB_URI)  # Using URI from config.py
db = client['video_downloader']
rate_limit_collection = db['rate_limit']
lock_collection = db['locks']
task_collection = db['tasks']

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]

# Rate limiting ফাংশন
async def is_rate_limited(user_id: int, limit: int = 1, window: int = 60):
    current_time = datetime.utcnow()
    user_data = rate_limit_collection.find_one({"user_id": user_id})
    
    if not user_data:
        # যদি ইউজারের ডেটা না থাকে, নতুন রেকর্ড তৈরি
        rate_limit_collection.insert_one({
            "user_id": user_id,
            "last_request_time": current_time,
            "request_count": 1,
            "expires_at": current_time + timedelta(seconds=window)
        })
        return False

    # চেক করা হচ্ছে কিভাবে লিমিট পরবর্তীতে রেট লিমিটেড হতে পারে
    time_difference = current_time - user_data['last_request_time']
    if time_difference < timedelta(seconds=window):
        # যদি রেট লিমিট ছাড়িয়ে যায়
        if user_data['request_count'] >= limit:
            return True
        else:
            # রিকোয়েস্ট বাড়ানো
            rate_limit_collection.update_one(
                {"user_id": user_id},
                {"$inc": {"request_count": 1}},
                upsert=True
            )
            return False
    else:
        # নতুন রিকোয়েস্টে সময় পুনরায় সেট
        rate_limit_collection.update_one(
            {"user_id": user_id},
            {"$set": {"last_request_time": current_time, "request_count": 1}},
            upsert=True
        )
        return False

# Lock সিস্টেম ফাংশন
async def acquire_lock(user_id, ttl=30):
    key = f"user_lock:{user_id}"
    current_time = datetime.utcnow()
    lock_expiry = current_time + timedelta(seconds=ttl)

    lock_data = {
        "user_id": user_id,
        "lock_expiry": lock_expiry
    }

    result = lock_collection.find_one_and_update(
        {"user_id": user_id},
        {"$setOnInsert": lock_data},
        upsert=True
    )

    if result and result.get("lock_expiry", 0) > current_time:
        return False  # Lock already acquired
    
    lock_collection.update_one(
        {"user_id": user_id},
        {"$set": {"lock_expiry": lock_expiry}}
    )
    return True

async def release_lock(user_id):
    lock_collection.delete_one({"user_id": user_id})

# Task Queue সিস্টেম
async def queue_task(user_id, coro):
    task_data = {
        "user_id": user_id,
        "task_id": f"task_{user_id}_{time.time()}",
        "status": "pending",
        "created_at": datetime.utcnow()
    }
    task_collection.insert_one(task_data)
    await process_user_queue(user_id, coro)

async def process_user_queue(user_id, coro):
    task_data = task_collection.find_one({"user_id": user_id, "status": "pending"})
    if task_data:
        try:
            await coro
            task_collection.update_one(
                {"_id": task_data["_id"]},
                {"$set": {"status": "completed"}}
            )
        except Exception as e:
            print(f"Error processing task: {e}")
            task_collection.update_one(
                {"_id": task_data["_id"]},
                {"$set": {"status": "failed"}}
            )

# ইউটিলিটি ফাংশনস
def get_extension_from_url(url):
    parsed = urlparse(url)
    ext = os.path.splitext(parsed.path)[1]
    return ext if ext else ".bin"

async def download_file(url, filename):
    headers = {"User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to fetch: {resp.status}")
            with open(filename, 'wb') as f:
                while True:
                    chunk = await resp.content.read(1024 * 512)
                    if not chunk:
                        break
                    f.write(chunk)
    return filename

def extract_metadata(file_path):
    try:
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,duration", "-of", "json", file_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        data = json.loads(result.stdout)
        if "streams" not in data or not data["streams"]:
            return 0, 0, 0
        stream = data["streams"][0]
        duration = float(stream.get("duration", "0") or 0)
        width = int(stream.get("width", 0))
        height = int(stream.get("height", 0))
        return duration, width, height
    except Exception:
        return 0, 0, 0

def generate_thumbnail(file_path, output_thumb="/tmp/thumb.jpg"):
    try:
        subprocess.run(
            ["ffmpeg", "-i", file_path, "-ss", "00:00:01.000", "-vframes", "1", output_thumb],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return output_thumb if os.path.exists(output_thumb) else None
    except:
        return None

# Pyrogram Client সেটআপ
@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def direct_link_handler(bot: Client, message: Message):
    user_id = message.from_user.id

    if await is_rate_limited(user_id):
        return await message.reply_text("Too many requests. Please wait a bit.")

    await queue_task(user_id, process_download(bot, message))

# ডাউনলোড প্রসেস ফাংশন
async def process_download(bot: Client, message: Message):
    user_id = message.from_user.id
    urls = message.text.strip().split()
    valid_urls = []

    for url in urls:
        if url.lower().startswith("http"):
            ext = get_extension_from_url(url)
            valid_urls.append((url, ext))

    if not valid_urls:
        return await message.reply_text("No valid downloadable links found.")

    for index, (url, ext) in enumerate(valid_urls, start=1):
        filename = f"/tmp/file_{user_id}_{index}{ext}"
        try:
            status = await message.reply_text(f"Downloading: {url}")
            await asyncio.sleep(2)
            await status.delete()

            await download_file(url, filename)

            if not os.path.exists(filename):
                raise Exception("File download failed.")

            caption = f"Downloaded from: {url}"

            if ext.lower() in VIDEO_EXTENSIONS:
                duration, width, height = extract_metadata(filename)
                thumb = generate_thumbnail(filename)

                video_kwargs = {
                    "video": filename,
                    "caption": caption,
                }
                if duration: video_kwargs["duration"] = int(duration)
                if width: video_kwargs["width"] = width
                if height: video_kwargs["height"] = height
                if thumb: video_kwargs["thumb"] = thumb

                msg = await message.reply_text("Uploading video... Please wait.")
                await message.reply_video(**video_kwargs)
                await msg.delete()
            else:
                msg = await message.reply_text("Uploading file... Please wait.")
                await message.reply_document(document=filename, caption=caption)
                await msg.delete()

        except Exception as e:
            traceback.print_exc()
            await message.reply_text(f"❌ Error with `{url}`\n\n**{e}**")
        finally:
            if os.path.exists(filename):
                os.remove(filename)
            if os.path.exists("/tmp/thumb.jpg"):
                os.remove("/tmp/thumb.jpg")