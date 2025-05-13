import aiohttp
import aiofiles
import os
import time
from pyrogram import Client, filters
from pyrogram.types import Message

async def download_file(url, file_path):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return False
                f = await aiofiles.open(file_path, mode='wb')
                async for chunk in resp.content.iter_chunked(1024):
                    await f.write(chunk)
                await f.close()
        return True
    except Exception as e:
        print(f"Download error: {e}")
        return False

@Client.on_message(filters.text & filters.private)
async def handle_link(client, message: Message):
    url = message.text.strip()
    if not url.startswith("http"):
        return

    status = await message.reply("⏳ Downloading file...")

    file_name = f"file_{int(time.time())}.mp4"
    downloaded = await download_file(url, file_name)

    if not downloaded:
        return await status.edit("❌ Failed to download the file.")

    try:
        await status.edit("⬆️ Uploading file to Telegram...")
        await message.reply_document(document=file_name, caption="✅ Here's your downloaded file")
    except Exception as e:
        print(f"Upload error: {e}")
        await message.reply("❌ Failed to upload the file.")
    finally:
        if os.path.exists(file_name):
            os.remove(file_name)
        await status.delete()