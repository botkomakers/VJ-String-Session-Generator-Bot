from pyrogram import Client, filters
from pyrogram.types import Message
import aiohttp
import asyncio
import os
from urllib.parse import urlparse

VIDEO_EXTENSIONS = [".mp4", ".mkv", ".mov", ".avi", ".webm"]

def get_extension_from_url(url):
    parsed = urlparse(url)
    ext = os.path.splitext(parsed.path)[1]
    return ext if ext.lower() in VIDEO_EXTENSIONS else ".mp4"

async def download_video(url, filename):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
        "Connection": "keep-alive",
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to fetch: {resp.status}")
            with open(filename, 'wb') as f:
                while True:
                    chunk = await resp.content.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
    return filename

@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def direct_video_handler(bot: Client, message: Message):
    urls = message.text.strip().split()
    msg = await message.reply_text("Checking provided links...")

    valid_urls = []
    for url in urls:
        if not url.lower().startswith("http"):
            continue
        ext = get_extension_from_url(url)
        valid_urls.append((url, ext))

    if not valid_urls:
        return await msg.edit("No valid video links found.")

    await msg.edit(f"Found {len(valid_urls)} video(s). Starting download...")

    tasks = []
    file_names = []

    for index, (url, ext) in enumerate(valid_urls, start=1):
        filename = f"video_{index}{ext}"
        tasks.append(download_video(url, filename))
        file_names.append(filename)

    try:
        await asyncio.gather(*tasks)
        await msg.edit("Uploading video(s) to Telegram...")

        for file, (url, _) in zip(file_names, valid_urls):
            await message.reply_video(
                video=file,
                caption=f"**Downloaded from:** `{url}`"
            )
            os.remove(file)

        await msg.delete()

    except Exception as e:
        await msg.edit(f"Error occurred: `{e}`")
        for file in file_names:
            if os.path.exists(file):
                os.remove(file)