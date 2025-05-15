# plugins/link_handler.py
import os
import aiohttp
import math
import asyncio
import subprocess
from pyrogram import Client, filters
from pyrogram.types import Message
from config import LOG_CHANNEL

MAX_SIZE = 1900 * 1024 * 1024  # 1.9 GB

@Client.on_message(filters.text & filters.private)
async def auto_download_handler(client: Client, message: Message):
    url = message.text.strip()

    if not url.startswith("http"):
        await message.reply("❌ Invalid URL")
        return

    temp_dir = "/tmp"
    file_path = os.path.join(temp_dir, "downloaded_file")

    await message.reply("⏳ Starting download...")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    await message.reply(f"❌ Failed to download:\n{url}\n\nStatus: {resp.status}")
                    return
                with open(file_path, "wb") as f:
                    while True:
                        chunk = await resp.content.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
    except Exception as e:
        await message.reply(f"❌ Error during download:\n{e}")
        return

    file_size = os.path.getsize(file_path)
    await message.reply(f"✅ Download complete.\nFile size: {round(file_size / (1024**2), 2)} MB")

    if file_size <= MAX_SIZE:
        await message.reply_video(file_path, caption="🎥 Video")
        await client.send_video(LOG_CHANNEL, file_path, caption=f"User: {message.from_user.id}\nDownloaded Link:\n{url}")
        os.remove(file_path)
        return

    await message.reply(f"⚙️ File size: {round(file_size / (1024**3), 2)} GB. Splitting into parts...")

    # Calculate number of parts
    total_parts = math.ceil(file_size / MAX_SIZE)
    split_paths = []

    for i in range(total_parts):
        start_time = i * 15  # Assume 15 min parts
        part_path = os.path.join(temp_dir, f"part_{i+1}.mp4")

        # Use ffmpeg to split video
        try:
            cmd = [
                "ffmpeg", "-i", file_path,
                "-ss", str(start_time * 60),
                "-t", "900",  # 15 min = 900 sec
                "-c", "copy",
                part_path
            ]
            subprocess.run(cmd, check=True)
            if os.path.exists(part_path):
                split_paths.append(part_path)
        except Exception as e:
            await message.reply(f"❌ Error while splitting part {i+1}: {e}")
            continue

    # Upload parts
    for i, part_path in enumerate(split_paths):
        try:
            await message.reply_video(part_path, caption=f"**Video Part {i+1} of {total_parts}**")
            await client.send_video(LOG_CHANNEL, part_path, caption=f"User: {message.from_user.id}\nPart {i+1} of {total_parts}\n{url}")
            os.remove(part_path)
        except Exception as e:
            await message.reply(f"❌ Failed to upload part {i+1}:\n{e}")

    # Cleanup
    if os.path.exists(file_path):
        os.remove(file_path)