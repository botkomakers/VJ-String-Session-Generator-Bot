import asyncio
import os
import mimetypes
import requests
from pyrogram import Client, filters
from pyrogram.types import Message
from config import temp

download_queue = asyncio.Queue()
is_processing = False

@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def queue_video_handler(bot: Client, message: Message):
    url = message.text.strip()

    if not url.lower().startswith("http"):
        return

    await download_queue.put((bot, message, url))
    await message.reply_text("✅ Added to processing queue. Please wait...")

    if not temp.get("is_downloading", False):
        asyncio.create_task(process_download_queue())


async def process_download_queue():
    temp["is_downloading"] = True

    while not download_queue.empty():
        bot, message, url = await download_queue.get()
        status = await message.reply_text("⏳ Processing your video...")

        try:
            response = requests.get(url, stream=True, timeout=10)
            content_type = response.headers.get("content-type", "")

            if not content_type.startswith("video/"):
                if not any(url.lower().endswith(ext) for ext in [".mp4", ".mkv", ".mov", ".avi", ".webm"]):
                    await status.edit("This link does not seem to be a valid video.")
                    continue

            ext = mimetypes.guess_extension(content_type.split(";")[0]) or os.path.splitext(url)[-1] or ".mp4"
            filename = "video" + ext

            await status.edit("⬇️ Downloading...")

            with open(filename, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 1024 * 4):  # Increased chunk size for faster download
                    if chunk:
                        f.write(chunk)

            await status.edit("⬆️ Uploading to Telegram...")

            await message.reply_video(
                video=filename,
                caption=f"**Downloaded from:** `{url}`"
            )

            await status.delete()

        except Exception as e:
            await status.edit(f"❌ Failed: `{e}`")

        finally:
            if os.path.exists(filename):
                os.remove(filename)

    temp["is_downloading"] = False