from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN

class Bot(Client):
def init(self):
super().init(
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

async def stop(self, *args):  
    await super().stop()  
    print("Bot Stopped.")

Bot().run()

Thik acha

