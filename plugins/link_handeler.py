import os
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message
from config import temp
from helpers.progress import progress_bar
import mimetypes
import asyncio

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm"]

@Client.on_message(filters.text & ~filters.command(["start"]))
async def direct_video_handler(bot: Client, message: Message):
    url = message.text.strip()

    if not url.lower().startswith("http"):
        return

    processing = await message.reply("Checking the video link...")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                content_type = resp.headers.get("Content-Type", "").lower()
                content_length = int(resp.headers.get("Content-Length", 0))

                # Detect if it is a video link
                if not content_type.startswith("video/") and not any(url.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
                    return await processing.edit("This doesn't look like a direct video link.")

                ext = mimetypes.guess_extension(content_type.split(";")[0]) or os.path.splitext(url)[-1] or ".mp4"
                filename = "video" + ext

                await processing.edit("Downloading video...")

                downloaded = 0
                with open(filename, "wb") as f:
                    async for chunk in resp.content.iter_chunked(1024 * 1024):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            await progress_bar(
                                current=downloaded,
                                total=content_length,
                                message=processing,
                                stage="Downloading"
                            )

        await progress_bar(content_length, content_length, processing, "Download Complete!")
        await processing.edit("Uploading to Telegram...")

        await message.reply_video(
            video=filename,
            caption=f"**Downloaded from:** `{url}`"
        )
        await processing.delete()

    except Exception as e:
        await processing.edit(f"Error: `{e}`")

    finally:
        if os.path.exists(filename):
            os.remove(filename)