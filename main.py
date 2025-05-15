import asyncio
from pyrogram import Client
from pyrogram.idle import idle
from config import API_ID, API_HASH, BOT_TOKEN, LOG_CHANNEL

class Bot(Client):
    def __init__(self):
        super().__init__(
            name="universal_video_bot",
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
        print(f"✅ Bot Started as @{me.username}")
        await self.send_message(
            chat_id=LOG_CHANNEL,
            text="✅ **Bot Restarted Successfully!**\n\nEverything is up and running now."
        )

    async def stop(self, *args):
        await super().stop()
        print("❌ Bot Stopped.")

if __name__ == "__main__":
    bot = Bot()
    asyncio.run(bot.start())
    idle()
    asyncio.run(bot.stop())