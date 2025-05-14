import os
import aiohttp
import asyncio
import subprocess
from pyrogram import Client, filters
from pyrogram.types import Message
from urllib.parse import urlparse

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]

def get_extension_from_url(url):
    parsed = urlparse(url)
    ext = os.path.splitext(parsed.path)[1]
    return ext if ext.lower() in VIDEO_EXTENSIONS else ".mp4"

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
        import cv2
        cap = cv2.VideoCapture(file_path)
        duration = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        return duration, width, height
    except:
        return 0, 0, 0

def generate_thumbnail(file_path, output_thumb="thumb.jpg"):
    try:
        subprocess.run(
            ["ffmpeg", "-i", file_path, "-ss", "00:00:01.000", "-vframes", "1", output_thumb],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return output_thumb if os.path.exists(output_thumb) else None
    except:
        return None

@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def direct_video_handler(bot: Client, message: Message):
    urls = message.text.strip().split()
    msg = await message.reply_text("Analyzing links...")

    valid_urls = []
    for url in urls:
        if not url.lower().startswith("http"):
            continue
        ext = get_extension_from_url(url)
        valid_urls.append((url, ext))

    if not valid_urls:
        return await msg.edit("No valid video links found.")

    await msg.edit(f"Downloading {len(valid_urls)} video(s)...")

    for index, (url, ext) in enumerate(valid_urls, start=1):
        filename = f"video_{index}{ext}"
        try:
            await download_video(url, filename)
            duration, width, height = extract_metadata(filename)
            thumb = generate_thumbnail(filename)

            await message.reply_video(
                video=filename,
                caption=f"**Downloaded from:** `{url}`",
                duration=duration if duration else None,
                width=width if width else None,
                height=height if height else None,
                thumb=thumb if thumb else None
            )
        except Exception as e:
            await message.reply_text(f"Failed to process: `{url}`\n\nError: `{e}`")
        finally:
            if os.path.exists(filename):
                os.remove(filename)
            if os.path.exists("thumb.jpg"):
                os.remove("thumb.jpg")

    await msg.delete()