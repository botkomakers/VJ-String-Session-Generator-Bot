from pyrogram import Client, filters
from pyrogram.types import Message

@Client.on_message(filters.command("start") & filters.private)
async def start_handler(client, message: Message):
    await message.reply_text(
        "Hello! Send me any video link from YouTube, Facebook, TikTok, etc. and I’ll download it for you!"
    )
