from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

@Client.on_message(filters.private & filters.command("start"))
async def start_command(client: Client, message: Message):
    try:
        await message.reply_photo(
            photo="https://i.ibb.co/rRj5vjLn/photo-2025-05-11-04-24-45-7504497537693253636.jpg",  # ইচ্ছামত পরিবর্তনযোগ্য
            caption=(
                "**👋 Welcome to the Ultimate Downloader Bot!**\n\n"
                "Easily download videos from **any platform** with just a link.\n\n"
                "**✅ Supported Platforms:**\n"
                "• YouTube, Facebook, Instagram, TikTok, Twitter\n"
                "• Pinterest, Reddit, Likee, IMDB trailers\n"
                "• Direct video/file links (e.g., .mp4, .mov, etc.)\n\n"
                "**⚡ Features:**\n"
                "• Multiple links in one message\n"
                "• Fast CDN-based downloads\n"
                "• Smart auto-detection & format handling\n"
                "• Auto thumbnail generation\n"
                "• Upload as video/document intelligently\n\n"
                "_Just send any video link, and let me handle the rest!_"
            ),
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("💬 Support", url="https://t.me/your_support_group"),
                    InlineKeyboardButton("📢 Updates", url="https://t.me/your_update_channel")
                ],
                [
                    InlineKeyboardButton("➕ Add to Group", url=f"https://t.me/{client.me.username}?startgroup=true")
                ]
            ])
        )
    except Exception as e:
        await message.reply_text(f"❌ Error sending start message:\n\n`{e}`")