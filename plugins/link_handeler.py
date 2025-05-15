import os
import math
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message
from config import LOG_CHANNEL
from helpers import download_with_progress

MAX_PART_SIZE = 1.5 * 1024 * 1024 * 1024  # 1.5 GB

@Client.on_message(filters.regex(r'^https?://.*') & filters.private)
async def auto_download_handler(client, message: Message):
    url = message.text.strip()
    filename = "/tmp/downloaded_file"

    try:
        # HEAD request to get size
        async with aiohttp.ClientSession() as session:
            async with session.head(url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                total_size = int(resp.headers.get("Content-Length", 0))
                if total_size == 0:
                    await message.reply("❌ Couldn't fetch file size.")
                    return

        await message.reply(f"📥 File size: {round(total_size / (1024**2), 2)} MB\nSplitting by 1.5GB parts...")

        # Downloading file
        await download_with_progress(url, filename, message)

        # Calculate number of parts
        total_parts = math.ceil(total_size / MAX_PART_SIZE)

        for i in range(total_parts):
            start_byte = int(i * MAX_PART_SIZE)
            end_byte = int(min((i + 1) * MAX_PART_SIZE, total_size))
            part_path = f"/tmp/part_{i+1}.mp4"

            with open(filename, "rb") as src, open(part_path, "wb") as dest:
                src.seek(start_byte)
                dest.write(src.read(end_byte - start_byte))

            try:
                await message.reply_video(part_path, caption=f"**Part {i+1}/{total_parts}**", supports_streaming=True)
            except Exception as e:
                await message.reply(f"❌ Failed to send part {i+1}: {e}")

            os.remove(part_path)

        os.remove(filename)

    except Exception as e:
        await message.reply(f"❌ Error: {e}")