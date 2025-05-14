import os
import aiohttp
import asyncio
import traceback
import subprocess
import json
import time
import datetime
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import Message
from urllib.parse import urlparse
from config import LOG_CHANNEL  # Ensure LOG_CHANNEL is set in config.py

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]

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
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
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
    except:
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

def format_bytes(size):
    power = 1024
    n = 0
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    while size > power and n < len(units) - 1:
        size /= power
        n += 1
    return f"{size:.2f} {units[n]}"

async def auto_cleanup(path="/tmp", max_age=180):
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
async def direct_link_handler(bot: Client, message: Message):
    urls = message.text.strip().split()
    try:
        notice = await message.reply_text("**Analyzing and processing...**")
    except FloodWait as e:
        await asyncio.sleep(e.value)
        notice = await message.reply_text("**Analyzing and processing...**")

    valid_urls = []
    for url in urls:
        if url.lower().startswith("http"):
            ext = get_extension_from_url(url)
            valid_urls.append((url, ext))

    if not valid_urls:
        return await notice.edit("No valid downloadable links found.")

    await notice.edit(f"Found {len(valid_urls)} file(s). Starting download...")

    for index, (url, ext) in enumerate(valid_urls, start=1):
        filename = f"/tmp/file_{index}{ext}"
        try:
            await notice.delete()
            downloading = await message.reply_text(f"**Downloading:**\n{url}")
            await download_file(url, filename)

            if not os.path.exists(filename):
                raise Exception("File download failed.")

            caption = f"**Downloaded from:**\n{url}"

            if ext.lower() in VIDEO_EXTENSIONS:
                duration, width, height = extract_metadata(filename)
                thumb = generate_thumbnail(filename)

                video_kwargs = {
                    "video": filename,
                    "caption": caption
                }
                if duration > 0:
                    video_kwargs["duration"] = int(duration)
                if width > 0 and height > 0:
                    video_kwargs["width"] = width
                    video_kwargs["height"] = height
                if thumb:
                    video_kwargs["thumb"] = thumb

                await downloading.delete()
                await message.reply_video(**video_kwargs)

            else:
                await downloading.delete()
                await message.reply_document(document=filename, caption=caption)

            # Send log to LOG_CHANNEL
            if os.path.exists(filename):
                file_size = format_bytes(os.path.getsize(filename))
                user = message.from_user
                log_text = (
                    f"**New Download Event**\n\n"
                    f"**User:** {user.mention} (`{user.id}`)\n"
                    f"**Link:** `{url}`\n"
                    f"**File Name:** `{os.path.basename(filename)}`\n"
                    f"**Size:** `{file_size}`\n"
                    f"**Type:** `{'Video' if ext.lower() in VIDEO_EXTENSIONS else 'Document'}`\n"
                    f"**Time:** `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
                )
                try:
                    await bot.send_message(LOG_CHANNEL, log_text)
                except Exception:
                    pass

        except FloodWait as e:
            await asyncio.sleep(e.value)
            continue
        except Exception as e:
            traceback.print_exc()
            await message.reply_text(f"❌ Error with `{url}`\n\n**{e}**")
        finally:
            try:
                if os.path.exists(filename):
                    os.remove(filename)
                if os.path.exists("/tmp/thumb.jpg"):
                    os.remove("/tmp/thumb.jpg")
                await auto_cleanup()
            except:
                pass