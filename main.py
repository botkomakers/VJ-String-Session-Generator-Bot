import asyncio
from pyrogram import Client
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

        try:
            await self.send_message(
                chat_id=LOG_CHANNEL,
                text="✅ **Bot Restarted Successfully!**\n\nEverything is up and running now."
            )
        except Exception as e:
            print(f"Failed to send startup message: {e}")

    async def stop(self, *args):
        await super().stop()
        print("❌ Bot Stopped.")

    async def run(self):
        await self.start()
        try:
            await asyncio.Event().wait()  # replaces idle()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            await self.stop()

if __name__ == "__main__":
    bot = Bot()
    asyncio.run(bot.run())