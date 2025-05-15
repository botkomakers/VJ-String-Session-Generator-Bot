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






import os
import math
import aiohttp
import asyncio
import subprocess
from pyrogram import Client, filters
from pyrogram.types import Message

MAX_SIZE_MB = 1536
TEMP_DIR = "/tmp"

async def download_file(url: str, path: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to download: HTTP {resp.status}")
            with open(path, "wb") as f:
                async for chunk in resp.content.iter_chunked(1024 * 1024):
                    f.write(chunk)

def get_size_mb(path):
    return os.path.getsize(path) / (1024 * 1024)

def split_video_by_size(input_path: str, output_dir: str, max_size_mb: int):
    total_size = os.path.getsize(input_path)
    part_size = max_size_mb * 1024 * 1024
    total_parts = math.ceil(total_size / part_size)
    part_paths = []

    for i in range(total_parts):
        part_path = os.path.join(output_dir, f"part_{i+1}.mp4")
        command = [
            "ffmpeg", "-y", "-i", input_path,
            "-ss", str(i * 1800),  # 30 minutes estimate per part
            "-fs", str(part_size),
            "-c", "copy", part_path
        ]
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(part_path):
            part_paths.append(part_path)

    return part_paths

@Client.on_message(filters.private & filters.command("start"))
async def start(client, message: Message):
    await message.reply("Welcome! Just send a direct video link to download it.")

@Client.on_message(filters.private & filters.text)
async def handle_direct_link(client, message: Message):
    url = message.text.strip()
    if not url.startswith("http"):
        return await message.reply("❌ Invalid link.")

    tmp_video = os.path.join(TEMP_DIR, f"{message.from_user.id}_video.mp4")
    status = await message.reply("📥 Downloading...")

    try:
        await download_file(url, tmp_video)
        size = get_size_mb(tmp_video)
        await status.edit(f"✅ Downloaded ({size:.2f} MB). Preparing to upload...")

        if size <= MAX_SIZE_MB:
            await message.reply_video(tmp_video, caption="🎬 Here is your video!", supports_streaming=True)
            os.remove(tmp_video)
            return

        await status.edit(f"🔧 Splitting {size:.2f}MB into 1.5GB parts...")

        parts = split_video_by_size(tmp_video, TEMP_DIR, MAX_SIZE_MB)
        if not parts:
            return await status.edit("❌ Failed to split the video.")

        for i, part in enumerate(parts):
            await message.reply_video(part, caption=f"📤 Part {i+1}/{len(parts)}", supports_streaming=True)
            os.remove(part)

        os.remove(tmp_video)
        await status.edit("✅ All parts uploaded successfully!")

    except Exception as e:
        await status.edit(f"❌ Error: {e}")
        if os.path.exists(tmp_video):
            os.remove(tmp_video)