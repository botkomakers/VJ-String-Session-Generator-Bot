import os
import aiohttp
import asyncio
import traceback
import subprocess
import json
from pyrogram import Client, filters
from pyrogram.types import Message
from urllib.parse import urlparse
from collections import defaultdict
import aioredis

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]

# Redis Init
redis = None

async def init_redis():
    global redis
    redis = await aioredis.from_url("redis://localhost")

# Rate limiter
async def is_rate_limited(user_id: int, limit: int = 1, window: int = 60):
    key = f"rate_limit:{user_id}"
    current = await redis.get(key)
    if current and int(current) >= limit:
        return True
    else:
        await redis.incr(key)
        await redis.expire(key, window)
        return False

# Lock system
async def acquire_lock(user_id, ttl=30):
    key = f"user_lock:{user_id}"
    if await redis.setnx(key, "locked"):
        await redis.expire(key, ttl)
        return True
    return False

async def release_lock(user_id):
    await redis.delete(f"user_lock:{user_id}")

# Task queue system
user_queues = defaultdict(asyncio.Queue)

async def queue_task(user_id, coro):
    q = user_queues[user_id]
    await q.put(coro)
    if q.qsize() == 1:
        await process_user_queue(user_id)

async def process_user_queue(user_id):
    q = user_queues[user_id]
    while not q.empty():
        coro = await q.get()
        try:
            await coro
        except Exception as e:
            print("Task error:", e)
        q.task_done()

# Utilities
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
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration",
            "-of", "json", file_path
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

@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def direct_link_handler(bot: Client, message: Message):
    user_id = message.from_user.id

    await init_redis()
    if await is_rate_limited(user_id):
        return await message.reply_text("Too many requests. Please wait a bit.")

    await queue_task(user_id, process_download(bot, message))

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