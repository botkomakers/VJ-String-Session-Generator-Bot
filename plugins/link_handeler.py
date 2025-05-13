import os
import aiohttp
import asyncio
import subprocess
from pyrogram import Client, filters
from pyrogram.types import Message

THUMB_URL = "https://i.ibb.co/21RKmKDG/file-1485.jpg"

async def download_file(url, path):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                with open(path, "wb") as f:
                    while True:
                        chunk = await resp.content.read(1024)
                        if not chunk:
                            break
                        f.write(chunk)
                return True
    return False

@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def direct_video_handler(client, message: Message):
    url = message.text.strip()
    if not url.startswith("http"):
        await message.reply("❌ Invalid link!")
        return

    status = await message.reply_photo(
        photo=THUMB_URL,
        caption="⏬ Downloading video, please wait..."
    )

    os.makedirs("downloads", exist_ok=True)
    raw_path = "downloads/input.mkv"
    mp4_path = "downloads/converted.mp4"

    try:
        ok = await download_file(url, raw_path)
        if not ok:
            return await status.edit_caption("❌ Failed to download the file.")

        # Convert to MP4
        convert_cmd = f'ffmpeg -i "{raw_path}" -c:v libx264 -c:a aac -strict experimental "{mp4_path}" -y'
        subprocess.run(convert_cmd, shell=True)

        await status.edit_caption("⬆️ Uploading as video...")

        await message.reply_video(
            video=mp4_path,
            caption="✅ Here is your converted video!",
            thumb=THUMB_URL,
            supports_streaming=True
        )
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")
    finally:
        await status.delete()
        for f in [raw_path, mp4_path]:
            if os.path.exists(f):
                os.remove(f)