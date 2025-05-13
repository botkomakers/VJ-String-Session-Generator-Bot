import os
import time
import asyncio
import requests
from pyrogram import Client, filters
from pyrogram.types import Message

# -------------------- Auto Link Detector --------------------
@Client.on_message(filters.private & filters.text & ~filters.command(["start", "help"]))
async def auto_direct_link_handler(client, message: Message):
    text = message.text.strip()

    # Auto detect direct URL (basic pattern)
    if not text.startswith("http://") and not text.startswith("https://"):
        return

    # Optional: add more checks if needed (e.g., file extensions or headers)

    status = await message.reply("⏳ Downloading file...")

    try:
        file_name = f"file_{int(time.time())}.bin"
        with requests.get(text, stream=True) as r:
            r.raise_for_status()
            content_type = r.headers.get("content-type", "")
            ext = content_type.split("/")[-1].split(";")[0] if "/" in content_type else "bin"
            file_name = f"file_{int(time.time())}.{ext}"
            with open(file_name, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
    except Exception as e:
        print(f"Download Error: {e}")
        return await status.edit("❌ Failed to download the file.")

    try:
        await status.edit("⬆️ Uploading file to Telegram...")
        await message.reply_document(
            document=file_name,
            caption="✅ Here's your downloaded file"
        )
    except Exception as e:
        print(f"Upload Error: {e}")
        await message.reply("❌ Failed to upload the file.")
    finally:
        if os.path.exists(file_name):
            os.remove(file_name)
        await status.delete()