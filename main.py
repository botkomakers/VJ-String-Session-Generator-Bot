from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN, LOG_CHANNEL  # LOG_CHANNEL হলো তোমার লক চ্যানেলের ID বা ইউজারনেম

class Bot(Client):
    def __init__(self):
        super().__init__(
            "universal_video_bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            plugins=dict(root="plugins"),
            workers=150,
            sleep_threshold=10
        )

    async def start(self):
        await super().start()
        me = await self.get_me()
        print(f"Bot Started as @{me.username}")

        # বট স্টার্ট নোটিফিকেশন
        try:
            await self.send_message(LOG_CHANNEL, f"✅ Bot Started as @{me.username}")
        except Exception as e:
            print(f"Failed to send start notification: {e}")

    async def stop(self, *args):
        me = await self.get_me()
        # বট স্টপ নোটিফিকেশন
        try:
            await self.send_message(LOG_CHANNEL, f"❌ Bot Stopped @{me.username}")
        except Exception as e:
            print(f"Failed to send stop notification: {e}")
        
        await super().stop()
        print("Bot Stopped.")

Bot().run()