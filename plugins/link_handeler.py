import os
import aiohttp
import asyncio
import subprocess
from pyrogram import Client, filters
from pyrogram.types import Message

THUMB_URL = "https://i.ibb.co/21RKmKDG/file-1485.jpg"

async def download_file(url, path):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    with open(path, "wb") as f:
                        while True:
                            chunk = await resp.content.read(1024 * 1024)  # 1MB chunks
                            if not chunk:
                                break
                            f.write(chunk)
                    return True
                else:
                    print(f"Download failed with status {resp.status}")
                    return False
    except Exception as e:
        print(f"Download error: {e}")
        return False

@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def direct_video_handler(client, message: Message):
    url = message.text.strip()
    if not url.startswith("http"):
        return await message.reply("❌ Invalid link!")

    status = await message.reply_photo(
        photo=THUMB_URL,
        caption="⏬ Downloading video, please wait..."
    )

    os.makedirs("downloads", exist_ok=True)
    raw_path = "downloads/input.mkv"
    mp4_path = "downloads/converted.mp4"

    try:
        ok = await download_file(url, raw_path)
        if not ok or not os.path.exists(raw_path) or os.path.getsize(raw_path) < 1024:
            return await status.edit_caption("❌ Failed to download or file too small.")

        # Convert to MP4 using ffmpeg
        convert_cmd = f'ffmpeg -y -i "{raw_path}" -c:v libx264 -c:a aac "{mp4_path}"'
        conversion = subprocess.run(convert_cmd, shell=True)

        if not os.path.exists(mp4_path) or os.path.getsize(mp4_path) < 1024:
            return await status.edit_caption("❌ Conversion failed.")

        await status.edit_caption("⬆️ Uploading as video...")

        await message.reply_video(
            video=mp4_path,
            caption="✅ Here is your converted video!",
            thumb=THUMB_URL,
            supports_streaming=True
        )
    except Exception as e:
        await message.reply(f"❌ Error: {e}")
    finally:
        await status.delete()
        for f in [raw_path, mp4_path]:
            if os.path.exists(f):
                os.remove(f)