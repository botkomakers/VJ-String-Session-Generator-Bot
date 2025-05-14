import os
import aiohttp
import asyncio
import mimetypes
import subprocess
import json
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait

from config import temp

def safe_float(value):
    try:
        return float(value)
    except:
        return 0.0

async def safe_send(func, *args, **kwargs):
    try:
        return await func(*args, **kwargs)
    except FloodWait as e:
        print(f"[universal_video_bot] Waiting for {e.value} seconds before continuing (required by {func.__name__})")
        await asyncio.sleep(e.value)
        return await func(*args, **kwargs)

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
        duration = safe_float(stream.get("duration"))
        width = int(stream.get("width", 0))
        height = int(stream.get("height", 0))
        return duration, width, height
    except Exception as e:
        print(f"Metadata error: {e}")
        return 0.0, 0, 0

@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def direct_video_handler(client, message: Message):
    urls = [word for word in message.text.split() if word.startswith("http")]
    if not urls:
        return await safe_send(message.reply_text, "No valid link found.")
    
    msg = await safe_send(message.reply_text, "Analyzing links...")
    
    for i, url in enumerate(urls):
        filename = f"video_{i+1}"
        ext = os.path.splitext(url)[1]
        if not ext:
            ext = mimetypes.guess_extension("video/mp4") or ".mp4"
        file_path = f"{filename}{ext}"
        
        try:
            await safe_send(msg.edit, f"Downloading: `{url}`")
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        with open(file_path, "wb") as f:
                            f.write(await resp.read())
                    else:
                        await safe_send(msg.edit, f"Failed to download: {url}")
                        continue

            duration, width, height = extract_metadata(file_path)

            await safe_send(msg.edit, f"Uploading `{os.path.basename(file_path)}` to Telegram...")
            await safe_send(message.reply_video, video=file_path, duration=int(duration), width=width, height=height, caption="Here's your video!")

        except Exception as e:
            await safe_send(message.reply_text, f"Failed to process: {url}\n\nError: {e}")
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

    await safe_send(msg.delete)