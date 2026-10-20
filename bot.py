import time
import traceback
import botpy
from modules.client import MyClient
from modules.config import APP_ID, APP_SECRET

if __name__ == "__main__":
    while True:
        try:
            intents = botpy.Intents.all()
            client = MyClient(intents=intents)
            client.run(appid=APP_ID, secret=APP_SECRET)
        except KeyboardInterrupt:
            print("👋 手动停止机器人")
            break
        except Exception as e:
            print(f"❌ 机器人异常退出，5 秒后自动重启: {e}")
            traceback.print_exc()
            time.sleep(5)
