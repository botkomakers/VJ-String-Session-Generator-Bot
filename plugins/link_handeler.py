import os
import time
import requests
from pyrogram import Client, filters
from pyrogram.types import Message
import math

# ✅ প্রগ্রেস বার জেনারেটর ফাংশন
def progress_bar(current, total, prefix):
    percent = current * 100 / total
    bar_length = 10
    filled_length = int(bar_length * percent / 100)
    bar = '■' * filled_length + '▩' + '□' * (bar_length - filled_length - 1)
    return f"{prefix}: {int(percent)}%\n{bar}"

# ✅ /direct কমান্ড হ্যান্ডলার
@Client.on_message(filters.command("direct") & filters.private)
async def direct_link_handler(client, message: Message):
    url = ' '.join(message.command[1:])
    if not url.startswith("http"):
        return await message.reply("❌ Usage: `/direct [Download URL]`", parse_mode="markdown")
    await handle_direct_download(client, message, url)

# ✅ সরাসরি লিংক হ্যান্ডলার (auto detection)
@Client.on_message(filters.private & filters.text & filters.regex(r'^https?://'))
async def auto_direct_handler(client, message: Message):
    url = message.text.strip()
    await handle_direct_download(client, message, url)

# ✅ মেইন হ্যান্ডলার
async def handle_direct_download(client, message: Message, url: str):
    status = await message.reply("⏳ Starting download...")

    try:
        ext = url.split('?')[0].split('.')[-1][:4]
        file_name = f"file_{int(time.time())}.{ext if ext.isalnum() else 'bin'}"

        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            total = int(r.headers.get('Content-Length', 0))
            downloaded = 0
            last_update = time.time()

            with open(file_name, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024 * 512):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        # প্রতি 1 সেকেন্ড পরপর আপডেট
                        if time.time() - last_update > 1:
                            prog = progress_bar(downloaded, total, "Downloading")
                            await status.edit(prog)
                            last_update = time.time()
    except Exception as e:
        print(f"[Download Error] {e}")
        return await status.edit("❌ Failed to download the file. Invalid or unsupported link.")

    try:
        await status.edit("⬆️ Preparing to upload...")

        # ✅ Upload with progress bar
        async def progress(current, total):
            prog = progress_bar(current, total, "Sending")
            try:
                await status.edit(prog)
            except:
                pass  # Prevent flood errors

        await message.reply_document(
            document=file_name,
            caption="✅ Here's your downloaded file",
            progress=progress
        )
    except Exception as e:
        print(f"[Upload Error] {e}")
        await message.reply("❌ Failed to upload the file.")
    finally:
        if os.path.exists(file_name):
            os.remove(file_name)
        await status.delete()