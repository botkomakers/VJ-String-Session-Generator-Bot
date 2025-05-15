import os
import aiohttp
import asyncio
import math
import subprocess
from pyrogram import Client, filters

MAX_PART_SIZE_MB = 1536  # 1.5 GB

async def download_file(url, path):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            with open(path, "wb") as f:
                async for chunk in resp.content.iter_chunked(1024 * 1024):
                    f.write(chunk)

def split_by_size(input_file, output_dir, part_size_mb=1536):
    os.makedirs(output_dir, exist_ok=True)
    total_size = os.path.getsize(input_file)
    part_size = part_size_mb * 1024 * 1024
    total_parts = math.ceil(total_size / part_size)
    part_paths = []

    for i in range(total_parts):
        start = i * part_size
        output_path = os.path.join(output_dir, f"part_{i + 1}.mp4")

        command = [
            "ffmpeg", "-y", "-i", input_file,
            "-ss", str(i * 900),
            "-fs", str(part_size),
            "-c", "copy", output_path
        ]

        try:
            subprocess.run(command, check=True)
            part_paths.append(output_path)
        except subprocess.CalledProcessError as e:
            print(f"❌ Error splitting part {i+1}: {e}")
            continue

    return part_paths

@Client.on_message(filters.command("dl") & filters.private)
async def download_handler(client, message):
    url = message.text.split(" ", 1)[1]
    downloading = await message.reply("📥 Downloading video...")

    temp_dir = "/tmp"
    downloaded_path = os.path.join(temp_dir, "downloaded_video.mp4")

    try:
        await download_file(url, downloaded_path)
        size_mb = os.path.getsize(downloaded_path) / (1024 * 1024)
        await downloading.edit(f"📥 File size: {size_mb:.2f} MB\nSplitting by 1.5GB parts...")

        parts = split_by_size(downloaded_path, temp_dir)
        if not parts:
            return await downloading.edit("❌ Failed to split the video.")

        for i, part_path in enumerate(parts):
            if os.path.exists(part_path):
                await message.reply_video(part_path, caption=f"**Part {i+1}/{len(parts)}**", supports_streaming=True)
                os.remove(part_path)
            else:
                await message.reply(f"❌ Part {i+1} missing!")

        os.remove(downloaded_path)
        await downloading.edit("✅ All parts sent successfully!")

    except Exception as e:
        await downloading.edit(f"❌ Error: {e}")