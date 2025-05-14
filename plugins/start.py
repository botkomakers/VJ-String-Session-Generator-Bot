from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

@Client.on_message(filters.private & filters.command("start"))
async def start_command(client: Client, message: Message):
    await message.reply_text(
        text=(
            "**Welcome!**\n\n"
            "I can download videos from **direct video links**.\n"
            "Just send me any direct video link like:\n"
            "`https://example.com/video.mp4`\n\n"
            "**Features:**\n"
            "- Supports multiple links\n"
            "- Fast CDN downloading\n"
            "- Automatic upload to Telegram"
        ),
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Support", url="https://t.me/your_support_group")],
                [InlineKeyboardButton("Updates", url="https://t.me/your_update_channel")]
            ]
        )
    )