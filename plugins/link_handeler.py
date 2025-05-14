import os
import aiohttp
import subprocess
import json
import asyncio
from urllib.parse import urlparse
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]

def get_extension_from_url(url):
    parsed = urlparse(url)
    ext = os.path.splitext(parsed.path)[1]
    return ext.lower() if ext else ""

async def download_file(url, filename):
    headers = {"User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to download: {resp.status}")
            with open(filename, 'wb') as f:
                while True:
                    chunk = await resp.content.read(1024 * 1024)
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
        stream = data.get("streams", [{}])[0]
        duration = float(stream.get("duration", 0))
        width = int(stream.get("width", 0))
        height = int(stream.get("height", 0))
        return duration, width, height
    except Exception as e:
        print(f"Metadata error: {e}")
        return 0.0, 0, 0

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
async def auto_downloader(client: Client, message: Message):
    urls = [u for u in message.text.strip().split() if u.startswith("http")]
    if not urls:
        return await message.reply_text("No valid link found.")
    
    status = await message.reply_text("Analyzing your links...")

    for index, url in enumerate(urls, start=1):
        ext = get_extension_from_url(url)
        filename = f"/tmp/file_{index}{ext if ext else '.bin'}"
        
        try:
            await status.edit(f"Downloading: `{url}`")
            await download_file(url, filename)

            if ext in VIDEO_EXTENSIONS:
                await message.reply_chat_action("upload_video")
                duration, width, height = extract_metadata(filename)
                thumb = generate_thumbnail(filename)

                try:
                    await message.reply_video(
                        video=filename,
                        duration=int(duration) if duration else None,
                        width=width if width else None,
                        height=height if height else None,
                        thumb=thumb if thumb else None,
                        caption=f"**Downloaded from:** `{url}`"
                    )
                except FloodWait as e:
                    await asyncio.sleep(e.value + 1)
                    await message.reply_video(
                        video=filename,
                        duration=int(duration) if duration else None,
                        width=width if width else None,
                        height=height if height else None,
                        thumb=thumb if thumb else None,
                        caption=f"**Downloaded from:** `{url}`"
                    )
            else:
                await message.reply_chat_action("upload_document")
                try:
                    await message.reply_document(
                        document=filename,
                        caption=f"**Downloaded from:** `{url}`"
                    )
                except FloodWait as e:
                    await asyncio.sleep(e.value + 1)
                    await message.reply_document(
                        document=filename,
                        caption=f"**Downloaded from:** `{url}`"
                    )

            await asyncio.sleep(1)  # fallback cooldown
        except Exception as e:
            await message.reply_text(f"Error with `{url}`\n\n{e}")
        finally:
            if os.path.exists(filename):
                os.remove(filename)
            if os.path.exists("/tmp/thumb.jpg"):
                os.remove("/tmp/thumb.jpg")

    await status.delete()