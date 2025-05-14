import os
import aiohttp
import asyncio
import traceback
import subprocess
import json
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import Message
from urllib.parse import urlparse
from config import LOG_CHANNEL  # তোমার config.py তে থাকা LOG_CHANNEL

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

def get_readable_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"

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

            file_size = os.path.getsize(filename)
            readable_size = get_readable_size(file_size)

            if ext.lower() in VIDEO_EXTENSIONS:
                duration, width, height = extract_metadata(filename)
                thumb = generate_thumbnail(filename)

                caption = (
                    f"**Downloaded from:** {url}\n"
                    f"**File Name:** `{os.path.basename(filename)}`\n"
                    f"**Size:** {readable_size}"
                )

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

                # Log to admin/log channel
                await bot.send_video(
                    chat_id=LOG_CHANNEL,
                    video=filename,
                    caption=(
                        f"**User:** [{message.from_user.first_name}](tg://user?id={message.from_user.id})\n"
                        f"**User ID:** `{message.from_user.id}`\n"
                        f"**URL:** {url}\n"
                        f"**File Name:** `{os.path.basename(filename)}`\n"
                        f"**Size:** {readable_size}"
                    ),
                    thumb=thumb if thumb else None,
                    duration=int(duration) if duration else None,
                    width=width if width else None,
                    height=height if height else None
                )

            else:
                caption = (
                    f"**Downloaded from:** {url}\n"
                    f"**File Name:** `{os.path.basename(filename)}`\n"
                    f"**Size:** {readable_size}"
                )
                await downloading.delete()
                await message.reply_document(document=filename, caption=caption)

                await bot.send_document(
                    chat_id=LOG_CHANNEL,
                    document=filename,
                    caption=(
                        f"**User:** [{message.from_user.first_name}](tg://user?id={message.from_user.id})\n"
                        f"**User ID:** `{message.from_user.id}`\n"
                        f"**URL:** {url}\n"
                        f"**File Name:** `{os.path.basename(filename)}`\n"
                        f"**Size:** {readable_size}"
                    )
                )

        except FloodWait as e:
            await asyncio.sleep(e.value)
            continue
        except Exception as e:
            traceback.print_exc()
            await message.reply_text(f"❌ Error with `{url}`\n\n**{e}**")
        finally:
            if os.path.exists(filename):
                os.remove(filename)
            if os.path.exists("/tmp/thumb.jpg"):
                os.remove("/tmp/thumb.jpg")