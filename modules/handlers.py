import re
import subprocess
import traceback
import aiohttp
from datetime import datetime
from botpy.message import Message
from modules.monitor import get_server_status
from modules.ai_chat import AIChat
from modules.utils import get_session_id
from modules.reply_utils import send_reply
from modules.help_text import get_help
from modules.commands import *
from modules.diary import append_entry

class MessageHandler:
    def __init__(self, client):
        self.client = client
        self.ai = AIChat()

    async def handle(self, message: Message, is_group: bool):
        try:
            await self._dispatch(message, is_group)
        except Exception as e:
            error_msg = f"❌ 处理消息时出错喵：{str(e)[:100]}"
            print(f"错误详情: {traceback.format_exc()}")
            await send_reply(self.client, message, error_msg, is_group)

    async def _dispatch(self, message: Message, is_group: bool):
        content = message.content.strip()
        clean_content = re.sub(r'^@.*?\s+', '', content).strip()
        session_id = get_session_id(message, is_group)

        if clean_content.startswith("/"):
            parts = clean_content.split()
            cmd = parts[0].lower() if parts else ""
            args = " ".join(parts[1:]) if len(parts) > 1 else ""

            if cmd in ("/status", "/状态"):
                reply = await cmd_status()
            elif cmd == "/models":
                reply = await cmd_models(message, args, is_group)
            elif cmd in ("/help", "/帮助"):
                reply = get_help(is_group)
            elif cmd == "/clear":
                reply = await cmd_clear(self.ai, session_id)
            elif cmd == "/myid":
                reply = cmd_myid(message)
            elif cmd == "/name":
                reply = await cmd_name(message, args, is_group)
            elif cmd == "/testalert":
                reply = await cmd_testalert(self.client, message)
            elif cmd == "/restart":
                reply = await cmd_restart(message, args, is_group, lambda m, r, g: send_reply(self.client, m, r, g))
                if reply is None:
                    return
            elif cmd == "/exec":
                reply = await cmd_exec(message, args, is_group)
            elif cmd == "/wp":
                reply = await cmd_wp(message, args, is_group)
            elif cmd == "/diary":
                reply = await cmd_diary(message, self.ai, session_id, is_group)
            elif cmd == "/tts":
                reply = await cmd_tts(message, args, self.client, self.ai, is_group, session_id)
                if reply is None:
                    return
            else:
                reply = "未知命令喵，发送 /help 看看～"
            await send_reply(self.client, message, reply, is_group)
            return

        if clean_content:
            sender = getattr(message.author, 'nickname', None) or getattr(message.author, 'username', None) or '用户'
            user_id = getattr(message.author, 'id', None) or getattr(message.author, 'openid', None) or getattr(message.author, 'user_openid', None)
            stored_name = get_user_name(user_id) if user_id else None
            display_name = stored_name if stored_name else (sender or user_id or '用户')
            enhanced_content = f"[{display_name}] {clean_content}"
            print(f"📤 转发到 AI: {enhanced_content}")
            reply = await self.ai.chat(session_id, enhanced_content, is_group)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            append_entry(f"[{now}] {display_name}: {clean_content}")
            append_entry(f"[{now}] 可丽堡堡: {reply}")
            await send_reply(self.client, message, reply, is_group)

    def _get_help(self, is_group: bool):
        return get_help(is_group)
