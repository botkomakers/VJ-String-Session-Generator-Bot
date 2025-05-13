from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from config import OWNER_ID, F_SUB
from TechVJ.db import db

@Client.on_message(filters.private & filters.incoming & filters.command("start"))
async def start(bot: Client, msg: Message):
    if not await db.is_user_exist(msg.from_user.id):
        await db.add_user(msg.from_user.id, msg.from_user.first_name)
    if F_SUB:
        try:
            await bot.get_chat_member(int(F_SUB), msg.from_user.id)
        except:
            try:
                invite_link = await bot.create_chat_invite_link(int(F_SUB))
            except:
                await msg.reply("**Make Sure I Am Admin In Your Channel**")
                return 
            key = InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton("🍿 Join Update Channel 🍿", url=invite_link.invite_link),
                    InlineKeyboardButton("🍀 Check Again 🍀", callback_data="chk")
                ]]
            ) 
        await msg.reply_text("**⚠️Access Denied!⚠️\n\nPlease Join My Update Channel To Use Me.If You Joined The Channel Then Click On Check Again Button To Confirm.**", reply_markup=key)
        return 
    me = (await bot.get_me()).mention
    await bot.send_message(
        chat_id=msg.chat.id,
        text=f"""<b>𝐇𝐞𝐲 {msg.from_user.mention}🍷,\n\nɪ ᴀᴍ {me},\nᴛʀᴜsᴛᴇᴅ 𝗦𝗧𝗥𝗜𝗡𝗚 𝗚𝗥𝗡𝗘𝗥𝗔𝗧𝗢𝗥 ʙᴏᴛ.ғᴜʟʟʏ sᴀғᴇ & sᴇᴄᴜʀᴇ.\nɴᴏ ᴀɴʏ ᴇʀʀᴏʀ\n\nMade With By : [VJ Botz](https://t.me/VJ_Botz) !</b>""",
        reply_markup=InlineKeyboardMarkup(
            [[
                InlineKeyboardButton(text="⚡ Generate String Session ⚡", callback_data="generate")
            ],[
                InlineKeyboardButton("❣️ Support Group ❣️", url="https://t.me/VJ_Bot_Disscussion"),
                InlineKeyboardButton("🥀 Update Channel 🥀", url="https://t.me/VJ_Botz")
            ]]
        )
    )

@Client.on_callback_query(filters.regex("chk"))
async def chk(bot : Client, cb : CallbackQuery):
    try:
        await bot.get_chat_member(int(F_SUB), cb.from_user.id)
    except:
        await cb.answer("🙅‍♂️ You are not joined my channel first join channel then check again. 🙅‍♂️", show_alert=True)
        return 
    me = (await bot.get_me()).mention
    await bot.send_message(
        chat_id=cb.from_user.id,
        text=f"""<b>𝐇𝐞𝐲 {cb.from_user.mention}🍷,\n\nɪ ᴀᴍ {me},\nᴛʀᴜsᴛᴇᴅ 𝗦𝗧𝗥𝗜𝗡𝗚 𝗚𝗥𝗡𝗘𝗥𝗔𝗧𝗢𝗥 ʙᴏᴛ.ғᴜʟʟʏ sᴀғᴇ & sᴇᴄᴜʀᴇ.\nɴᴏ ᴀɴʏ ᴇʀʀᴏʀ\n\nMade With By : [VJ Botz](https://t.me/VJ_Botz) !</b>""",
        reply_markup=InlineKeyboardMarkup(
            [[
                InlineKeyboardButton(text="⚡ Generate String Session ⚡", callback_data="generate")
            ],[
                InlineKeyboardButton("❣️ Support Group ❣️", url="https://t.me/VJ_Bot_Disscussion"),
                InlineKeyboardButton("🥀 Update Channel 🥀", url="https://t.me/VJ_Botz")
            ]]
        )
    )







import os
import time
import asyncio
import yt_dlp
from pyrogram import Client, filters
from pyrogram.types import Message

# Supported platforms (you can add more patterns)
VIDEO_SITES = ["youtube.com", "youtu.be", "facebook.com", "fb.watch", "tiktok.com", "instagram.com", "vimeo.com"]

def is_video_link(url: str) -> bool:
    return any(domain in url.lower() for domain in VIDEO_SITES)

# Auto-detect & download social video links
@Client.on_message(filters.private & filters.text)
async def auto_video_downloader(client, message: Message):
    url = message.text.strip()
    if not url.startswith("http") or not is_video_link(url):
        return  # Not a supported video link

    status = await message.reply("⏳ Fetching video info...")

    try:
        # Create download options
        timestamp = int(time.time())
        output_template = f"downloads/video_{timestamp}.%(ext)s"
        ydl_opts = {
            "outtmpl": output_template,
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "quiet": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)
            if not file_path.endswith(".mp4"):
                file_path = file_path.rsplit(".", 1)[0] + ".mp4"

        await status.edit("⬆️ Uploading video to Telegram...")
        await message.reply_video(
            video=file_path,
            caption=f"✅ Downloaded from {info.get('webpage_url')}"
        )

    except Exception as e:
        print(f"Download Error: {e}")
        await status.edit("❌ Failed to download the video.")
        return

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
        await status.delete()
