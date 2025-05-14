import os
import aiohttp
import subprocess
import json
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InputFile
from pyrogram.errors import FloodWait
from urllib.parse import urlparse

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]
DOWNLOAD_DIR = "/tmp"

def get_extension_from_url(url):
    parsed = urlparse(url)
    ext = os.path.splitext(parsed.path)[1]
    return ext if ext else ".bin"

async def download_video(url, filename):
    headers = {"User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to fetch: {resp.status}")
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

        if "streams" not in data or not data["streams"]:
            return 0.0, 0, 0

        stream = data["streams"][0]
        duration = float(stream.get("duration", 0.0))
        width = int(stream.get("width", 0))
        height = int(stream.get("height", 0))

        return duration, width, height
    except Exception as e:
        print(f"Metadata extraction error: {e}")
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

async def safe_reply(func, *args, **kwargs):
    while True:
        try:
            return await func(*args, **kwargs)
        except FloodWait as e:
            print(f"[FloodWait] Waiting for {e.value} seconds...")
            await asyncio.sleep(e.value)
        except Exception as e:
            print(f"Reply error: {e}")
            break

@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def direct_video_handler(bot: Client, message: Message):
    urls = message.text.strip().split()
    msg = await safe_reply(message.reply_text, "Analyzing links...")

    valid_urls = []
    for url in urls:
        if not url.lower().startswith("http"):
            continue
        ext = get_extension_from_url(url)
        valid_urls.append((url, ext))

    if not valid_urls:
        return await safe_reply(msg.edit, "No valid file links found.")

    await safe_reply(msg.edit, f"Downloading {len(valid_urls)} file(s)...")

    for index, (url, ext) in enumerate(valid_urls, start=1):
        filename = os.path.join(DOWNLOAD_DIR, f"file_{index}{ext}")
        try:
            await download_video(url, filename)

            if not os.path.exists(filename):
                raise Exception("Downloaded file not found!")

            if ext.lower() in VIDEO_EXTENSIONS:
                duration, width, height = extract_metadata(filename)
                thumb = generate_thumbnail(filename)

                await safe_reply(
                    message.reply_video,
                    video=filename,
                    caption=f"**Downloaded from:** `{url}`",
                    duration=int(duration) if duration else None,
                    width=width if width else None,
                    height=height if height else None,
                    thumb=InputFile(thumb) if thumb else None
                )
            else:
                await safe_reply(
                    message.reply_document,
                    document=filename,
                    caption=f"**Downloaded from:** `{url}`"
                )
        except Exception as e:
            await safe_reply(message.reply_text, f"Failed to process: `{url}`\n\nError: `{e}`")
        finally:
            if os.path.exists(filename):
                os.remove(filename)
            thumb_path = "/tmp/thumb.jpg"
            if os.path.exists(thumb_path):
                os.remove(thumb_path)

    await safe_reply(msg.delete)