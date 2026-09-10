import botpy
from modules.client import MyClient
from modules.config import APP_ID, APP_SECRET

if __name__ == "__main__":
    intents = botpy.Intents.all()
    client = MyClient(intents=intents)
    client.run(appid=APP_ID, secret=APP_SECRET)
