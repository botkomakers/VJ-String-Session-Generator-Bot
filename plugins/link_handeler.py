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

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"]

def get_extension_from_url(url):
    parsed = urlparse(url)
    ext = os.path.splitext(parsed.path)[1]
    return ext if ext else ".bin"

async def download_file(url, filename, progress_message):
    headers = {"User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to fetch: {resp.status}")
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(filename, 'wb') as f:
                while True:
                    chunk = await resp.content.read(1024 * 512)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        percent = downloaded * 100 / total
                        try:
                            await progress_message.edit_text(f"**Downloading...** `{percent:.2f}%`")
                        except:
                            pass
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
    urls = message.text.strip().split()
    reply = await message.reply_text("**Analyzing and processing...**")

    valid_urls = []
    for url in urls:
        if url.lower().startswith("http"):
            ext = get_extension_from_url(url)
            valid_urls.append((url, ext))

    if not valid_urls:
        return await reply.edit("No valid downloadable links found.")

    await reply.edit(f"Found {len(valid_urls)} file(s). Starting download...")

    for index, (url, ext) in enumerate(valid_urls, start=1):
        filename = f"/tmp/file_{index}{ext}"
        try:
            progress_message = await message.reply_text(f"**Downloading:** `{url}`")
            await download_file(url, filename, progress_message)

            if not os.path.exists(filename):
                raise Exception("File download failed.")

            caption = f"**Downloaded from:** `{url}`"

            if ext.lower() in VIDEO_EXTENSIONS:
                duration, width, height = extract_metadata(filename)
                thumb = generate_thumbnail(filename)

                video_kwargs = {
                    "video": filename,
                    "caption": caption,
                }
                if isinstance(duration, (int, float)) and duration > 0:
                    video_kwargs["duration"] = int(duration)
                if isinstance(width, int) and width > 0:
                    video_kwargs["width"] = width
                if isinstance(height, int) and height > 0:
                    video_kwargs["height"] = height
                if thumb:
                    video_kwargs["thumb"] = thumb

                await progress_message.edit_text("**Uploading video...** Please wait.")
                await message.reply_video(**video_kwargs)

            else:
                await progress_message.edit_text("**Uploading file...** Please wait.")
                await message.reply_document(document=filename, caption=caption)

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
            await progress_message.delete()

    await reply.delete()