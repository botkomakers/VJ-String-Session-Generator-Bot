import os
import math
import time
import aiohttp
import aiofiles
import mimetypes
from pyrogram import Client, filters
from pyrogram.types import Message

# Progress bar function
async def progress_bar(current, total, message, stage):
    percent = current * 100 / total if total else 0
    bar = "█" * int(percent / 10) + "░" * (10 - int(percent / 10))
    current_mb = current / 1024 / 1024
    total_mb = total / 1024 / 1024
    await message.edit_text(
        f"**{stage}**\n"
        f"[{bar}] {percent:.2f}%\n"
        f"**{current_mb:.2f} MB** of **{total_mb:.2f} MB**"
    )

# Main downloader handler
@Client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def direct_link_handler(client: Client, message: Message):
    url = message.text.strip()

    if not url.startswith(("http://", "https://")):
        return await message.reply("Please send a **valid direct download link.**")

    processing = await message.reply("**Downloading from the link...**")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return await processing.edit("Failed to fetch the file. Try again.")

                total = int(resp.headers.get("Content-Length", 0))
                content_type = resp.headers.get("Content-Type", "")
                ext = mimetypes.guess_extension(content_type.split(";")[0]) or ".bin"
                filename = f"download_{int(time.time())}{ext}"
                path = f"./downloads/{filename}"

                os.makedirs("downloads", exist_ok=True)

                f = await aiofiles.open(path, mode='wb')
                downloaded = 0
                chunk_size = 1024 * 64
                start_time = time.time()

                async for chunk in resp.content.iter_chunked(chunk_size):
                    await f.write(chunk)
                    downloaded += len(chunk)
                    if time.time() - start_time > 2:
                        start_time = time.time()
                        await progress_bar(downloaded, total, processing, "Downloading")

                await f.close()

    except Exception as e:
        return await processing.edit(f"Download error: `{e}`")

    await processing.edit("**Uploading to Telegram...**")

    try:
        await client.send_video(
            chat_id=message.chat.id,
            video=path,
            caption=f"**Downloaded from:** `{url}`",
            progress=progress_bar,
            progress_args=(processing, "Uploading")
        )
    except Exception as e:
        await processing.edit(f"Upload failed: `{e}`")
    finally:
        if os.path.exists(path):
            os.remove(path)