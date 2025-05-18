from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from config import LOG_CHANNEL
from db import save_user, has_been_notified, set_notified
from PIL import Image, ImageDraw, ImageFont
import os

FONT_PATH = "assets/fonts/DejaVuSans-Bold.ttf"
DEFAULT_PFP_PATH = "assets/default_profile.png"


def generate_user_image(name, username, user_id, profile_pic_path=None):
    img = Image.new("RGB", (800, 400), (30, 30, 30))
    draw = ImageDraw.Draw(img)

    try:
        if profile_pic_path and os.path.exists(profile_pic_path):
            pfp = Image.open(profile_pic_path).convert("RGB").resize((200, 200))
        elif os.path.exists(DEFAULT_PFP_PATH):
            pfp = Image.open(DEFAULT_PFP_PATH).convert("RGB").resize((200, 200))
        else:
            raise FileNotFoundError("Default profile picture missing.")
        img.paste(pfp, (30, 100))
    except Exception as e:
        print(f"Profile picture error: {e}")

    font_big = ImageFont.truetype(FONT_PATH, 40)
    font_small = ImageFont.truetype(FONT_PATH, 30)

    draw.text((260, 100), f"Name: {name}", font=font_big, fill="white")
    draw.text((260, 160), f"Username: @{username}" if username else "Username: N/A", font=font_small, fill="white")
    draw.text((260, 210), f"User ID: {user_id}", font=font_small, fill="white")
    draw.text((260, 260), "Joined via /start", font=font_small, fill="lightgreen")

    temp_path = f"/tmp/{user_id}_info.jpg"
    img.save(temp_path)
    return temp_path


@Client.on_message(filters.private & filters.command("start"))
async def start_handler(bot: Client, message: Message):
    user = message.from_user
    user_id = user.id
    profile_photo_path = None

    save_user(user_id, user.first_name, user.username)

    if not has_been_notified(user_id):
        try:
            photos = await bot.get_profile_photos(user_id, limit=1)
            if photos.total_count > 0:
                profile_photo_path = await bot.download_media(photos.photos[0].file_id)
        except Exception as e:
            print(f"Error fetching profile photo: {e}")

        image_path = generate_user_image(
            name=user.first_name,
            username=user.username,
            user_id=user_id,
            profile_pic_path=profile_photo_path
        )

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
            print(f"Error sending log: {e}")
        finally:
            if image_path and os.path.exists(image_path):
                os.remove(image_path)
            if profile_photo_path and os.path.exists(profile_photo_path):
                os.remove(profile_photo_path)

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




from pyrogram import Client, filters
from db import delete_user

@Client.on_message(filters.command("delete_user") & filters.private)
async def delete_user_command(client, message):
    user_id = message.from_user.id
    if delete_user(user_id):
        await message.reply_text("তোমার তথ্য সফলভাবে ডিলিট করা হয়েছে।")
    else:
        await message.reply_text("তোমার তথ্য খুঁজে পাওয়া যায়নি বা আগেই ডিলিট করা হয়েছে।")













from pyrogram import Client, filters
from pyrogram.types import Message
from db import add_premium, remove_premium, get_all_premium
ADMIN_ID = 7862181538  # তোমার টেলিগ্রাম ID এখানে দাও

@Client.on_message(filters.command("add_premium") & filters.user(ADMIN_ID))
async def add_premium_cmd(client, message: Message):
    if len(message.command) < 2:
        return await message.reply("Usage: /add_premium user_id")

    try:
        user_id = int(message.command[1])
        add_premium(user_id)
        users = get_all_premium()
        await message.reply(f"✅ Added `{user_id}` as Premium.\nTotal Premiums: {len(users)}")
    except Exception as e:
        await message.reply(f"Error: {e}")

@Client.on_message(filters.command("remove_premium") & filters.user(ADMIN_ID))
async def remove_premium_cmd(client, message: Message):
    if len(message.command) < 2:
        return await message.reply("Usage: /remove_premium user_id")

    try:
        user_id = int(message.command[1])
        remove_premium(user_id)
        users = get_all_premium()
        await message.reply(f"❌ Removed `{user_id}` from Premium.\nTotal Premiums: {len(users)}")
    except Exception as e:
        await message.reply(f"Error: {e}")

@Client.on_message(filters.command("premium_list") & filters.user(ADMIN_ID))
async def premium_list_cmd(client, message: Message):
    users = get_all_premium()
    if not users:
        return await message.reply("No Premium Users Found.")
    
    text = "\n".join([f"- `{u}`" for u in users])
    await message.reply(f"**Total Premium Users: {len(users)}**\n{text}")