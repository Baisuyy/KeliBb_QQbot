import botpy
from botpy.message import Message
import asyncio
import traceback
from modules.handlers import MessageHandler
from modules.monitor import get_server_status
from modules.config import ADMIN_OPENID

class MyClient(botpy.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.handler = MessageHandler(self)
        self._alert_task = None

    async def on_ready(self):
        print("✅ 机器人已就绪，等待消息...")
        self.handler.ai.load_all_contexts()
        # 启动后台告警循环
        self._alert_task = asyncio.create_task(self._alert_loop())
        # 发送上线通知（测试私聊通道）
        await self._send_alert("🎉 可丽堡堡已上线喵！我随时待命～")

    async def on_event(self, event):
        pass   # 可选择性打印日志

    async def on_c2c_message_create(self, message: Message):
        print(f"📩 私聊: {message.content}")
        await self.handler.handle(message, is_group=False)

    async def on_group_at_message_create(self, message: Message):
        print(f"📩 群@: {message.content}")
        await self.handler.handle(message, is_group=True)

    async def on_direct_message_create(self, message: Message):
        print(f"📩 私信: {message.content}")
        await self.handler.handle(message, is_group=False)

    # ========== 主动告警模块 ==========
    async def _send_alert(self, msg: str):
        if not ADMIN_OPENID or ADMIN_OPENID == "你的管理员openid":
            print("⚠️ 未设置管理员 openid，告警无法发送")
            return
        try:
            await self.api.post_c2c_message(
                openid=ADMIN_OPENID,
                msg_type=0,
                content=f"🔔 {msg}",
                msg_id=None
            )
            print(f"✅ 告警已发送: {msg}")
        except Exception as e:
            print(f"❌ 告警发送失败: {e}")

    async def _check_and_alert(self):
        status = await get_server_status()
        if "⚠️" in status or "❌" in status:
            await self._send_alert(status)
        else:
            print("✅ 定时巡检: 一切正常")

    async def _alert_loop(self):
        while True:
            await asyncio.sleep(3600)  # 1小时
            await self._check_and_alert()
