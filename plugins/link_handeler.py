import os
import aiohttp
import asyncio
import subprocess
from pyrogram import Client, filters
from pyrogram.types import Message

THUMB_URL = "https://i.ibb.co/21RKmKDG/file-1485.jpg"

async def download_file(url, path):
    timeout = aiohttp.ClientTimeout(total=90)  # 90 seconds max wait
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    with open(path, "wb") as f:
                        while True:
                            chunk = await resp.content.read(1024)
                            if not chunk:
                                break
                            f.write(chunk)
                    return True
    except Exception as e:
        print("Download error:", str(e))
    return False


@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def direct_video_handler(client, message: Message):
    url = message.text.strip()

    if not url.startswith("http"):
        return await message.reply("❌ Invalid link provided.")

    status = await message.reply_photo(
        photo=THUMB_URL,
        caption="⏬ Downloading video, please wait..."
    )

    os.makedirs("downloads", exist_ok=True)
    raw_path = "downloads/input.mkv"
    mp4_path = "downloads/converted.mp4"

    try:
        print("Trying to download:", url)
        ok = await download_file(url, raw_path)

        if not ok:
            return await status.edit_caption("❌ Failed to download the file. The link may be invalid or expired.")

        await status.edit_caption("🎞 Converting to MP4 format...")

        convert_cmd = f'ffmpeg -i "{raw_path}" -c:v libx264 -c:a aac -strict experimental "{mp4_path}" -y'
        try:
            subprocess.run(convert_cmd, shell=True, timeout=300)  # 5 minutes max
        except subprocess.TimeoutExpired:
            return await status.edit_caption("❌ FFmpeg conversion timed out.")

        await status.edit_caption("⬆️ Uploading the video...")

        await message.reply_video(
            video=mp4_path,
            caption="✅ Here is your converted video!",
            thumb=THUMB_URL,
            supports_streaming=True
        )

    except Exception as e:
        print("Error:", str(e))
        await message.reply(f"❌ Error occurred: {str(e)}")

    finally:
        await status.delete()
        for f in [raw_path, mp4_path]:
            if os.path.exists(f):
                os.remove(f)