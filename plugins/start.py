from pyrogram import Client, filters
from pyrogram.types import Message

@Client.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message: Message):
    await message.reply_text("✅ I'm alive and ready! Send me any direct or social media video link.")