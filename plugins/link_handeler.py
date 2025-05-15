from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from config import LOG_CHANNEL
from PIL import Image, ImageDraw, ImageFont
import os

from db import save_user, has_been_notified, set_notified  # Ensure these are implemented properly

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

def generate_user_image(name, username, user_id, profile_pic=None):
    img = Image.new("RGB", (800, 400), (30, 30, 30))
    draw = ImageDraw.Draw(img)

    if profile_pic:
        try:
            pfp = Image.open(profile_pic).convert("RGB").resize((200, 200))
            img.paste(pfp, (30, 100))
        except Exception as e:
            print(f"Profile pic paste error: {e}")

    font_big = ImageFont.truetype(FONT_PATH, 40)
    font_small = ImageFont.truetype(FONT_PATH, 30)

    draw.text((260, 100), f"Name: {name}", font=font_big, fill="white")
    draw.text((260, 160), f"Username: @{username}" if username else "Username: N/A", font=font_small, fill="white")
    draw.text((260, 210), f"User ID: {user_id}", font=font_small, fill="white")
    draw.text((260, 260), f"Joined via /start", font=font_small, fill="lightgreen")

    temp_path = f"/tmp/{user_id}_info.jpg"
    img.save(temp_path)
    return temp_path


@Client.on_message(filters.private & filters.command("start"))
async def start_command(bot: Client, message: Message):
    user = message.from_user
    user_id = user.id
    profile_photo_path = None

    # Save user
    save_user(user_id, user.first_name, user.username)

    # Only if not notified before
    if not has_been_notified(user_id):
        # Get profile photo
        try:
            photos = await bot.get_profile_photos(user_id, limit=1)
            if photos:
                profile_photo_path = await bot.download_media(photos[0].file_id)
        except Exception as e:
            print(f"Profile photo fetch failed: {e}")

        # Generate image
        image_path = generate_user_image(
            name=user.first_name,
            username=user.username,
            user_id=user_id,
            profile_pic=profile_photo_path
        )

        # Send log to channel
        try:
            await bot.send_photo(
                chat_id=LOG_CHANNEL,
                photo=image_path,
                caption=(
                    f"**New User Started Bot!**\n\n"
                    f"**Name:** {user.first_name}\n"
                    f"**Username:** @{user.username if user.username else 'N/A'}\n"
                    f"**ID:** `{user_id}`\n"
                    f"**Link:** [Click Here](tg://user?id={user_id})"
                )
            )
            set_notified(user_id)
        except Exception as e:
            print(f"Log sending failed: {e}")
        finally:
            if image_path and os.path.exists(image_path):
                os.remove(image_path)
            if profile_photo_path and os.path.exists(profile_photo_path):
                os.remove(profile_photo_path)

    # Send welcome message to user (always)
    await message.reply_photo(
        photo="https://i.ibb.co/rRj5vjLn/photo-2025-05-11-04-24-45-7504497537693253636.jpg",
        caption=(
            f"👋 Hello {user.mention}!\n\n"
            "Send me any video link and I'll fetch it for you!\n"
            "**Supports:** YouTube, Facebook, Instagram, TikTok, etc."
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Support", url="https://t.me/your_support_group")],
            [InlineKeyboardButton("Updates", url="https://t.me/your_update_channel")]
        ])
    )