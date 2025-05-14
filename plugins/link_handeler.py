import os
import aiohttp
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
import subprocess

THUMB_URL = "https://i.ibb.co/21RKmKDG/file-1485.jpg"

async def download_file(url, path):
    timeout = aiohttp.ClientTimeout(total=300)
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

def get_video_duration(path):
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration", "-of",
                "default=noprint_wrappers=1:nokey=1", path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        duration = float(result.stdout.decode().strip())
        return duration
    except Exception as e:
        print("Duration check error:", e)
        return None

@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def handle_direct_link(client, message: Message):
    url = message.text.strip()
    if not url.startswith("http"):
        return await message.reply("❌ Invalid link.")

    status = await message.reply_photo(THUMB_URL, caption="⏬ Downloading video, please wait...")

    os.makedirs("downloads", exist_ok=True)
    input_path = "downloads/input.mkv"
    cut_path = "downloads/trimmed.mp4"
    final_path = "downloads/converted.mp4"

    try:
        success = await download_file(url, input_path)
        if not success:
            return await status.edit_caption("❌ Failed to download the video.")

        await status.edit_caption("🔍 Checking video duration...")

        duration = get_video_duration(input_path)
        if duration is None:
            return await status.edit_caption("❌ Could not determine video duration.")

        if duration > 60 * 60:  # 60 minutes
            return await status.edit_caption("⚠️ Video is too long. Max allowed: 1 hour.")

        if duration > 20 * 60:
            await status.edit_caption("✂️ Trimming to 20 minutes to fit size limit...")
            trim_cmd = f'ffmpeg -i "{input_path}" -t 00:20:00 -c copy "{cut_path}" -y'
            subprocess.run(trim_cmd, shell=True)
            source_path = cut_path
        else:
            source_path = input_path

        await status.edit_caption("🎞 Converting to MP4 format...")

        convert_cmd = f'ffmpeg -i "{source_path}" -c:v libx264 -c:a aac "{final_path}" -y'
        subprocess.run(convert_cmd, shell=True)

        if not os.path.exists(final_path):
            return await status.edit_caption("❌ Conversion failed.")

        await status.edit_caption("⬆️ Uploading video...")

        await message.reply_video(
            video=final_path,
            caption="✅ Done! Here's your video.",
            thumb=THUMB_URL,
            supports_streaming=True
        )

    except Exception as e:
        await status.edit_caption(f"❌ Error: {e}")
        print("Error:", e)
    finally:
        await status.delete()
        for f in [input_path, cut_path, final_path]:
            if os.path.exists(f):
                os.remove(f)