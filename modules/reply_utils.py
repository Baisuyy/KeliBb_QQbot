import re
import time
from botpy.message import Message

# 记录最近发送过的 (msg_id, content, 时间戳)，防止同一消息重复回复触发 QQ 去重(40054005)
_recent_sends = {}


def _check_dedup(msg_id: str, content: str) -> bool:
    """若同一 msg_id 在 5 秒内已发送过相同内容，返回 True 表示应跳过"""
    if not msg_id:
        return False
    now = time.time()
    key = (msg_id, content)
    last = _recent_sends.get(key, 0)
    if now - last < 5:
        return True
    _recent_sends[key] = now
    return False


async def send_reply(client, message: Message, reply_content: str, is_group: bool):
    msg_id = getattr(message, 'id', None)
    if _check_dedup(msg_id, reply_content):
        print(f"⏭️ 跳过重复回复 (msg_id={msg_id})")
        return
    if len(reply_content) > 1900:
        reply_content = reply_content[:1900] + "\n... (截断)"
    if is_group:
        has_markdown = re.search(r'([#*`\-]|\n\s*\d+\.|\n\s*-|\n```)', reply_content)
        if has_markdown:
            msg_type = 2
            markdown_obj = {"content": reply_content}
            content_field = ""
        else:
            msg_type = 0
            markdown_obj = None
            content_field = reply_content
    else:
        msg_type = 0
        markdown_obj = None
        content_field = reply_content

    try:
        if is_group:
            group_openid = getattr(message, 'group_openid', None) or getattr(message, 'group_id', None)
            if group_openid:
                await client.api.post_group_message(
                    group_openid=group_openid,
                    msg_type=msg_type,
                    content=content_field,
                    markdown=markdown_obj,
                    msg_id=msg_id
                )
            else:
                await message.reply(content=reply_content)
        else:
            openid = getattr(message.author, 'id', None)
            if openid:
                await client.api.post_c2c_message(
                    openid=openid,
                    msg_type=msg_type,
                    content=content_field,
                    markdown=markdown_obj,
                    msg_id=msg_id
                )
            else:
                await message.reply(content=reply_content)
    except Exception as e:
        print(f"发送消息失败: {e}")
        try:
            await message.reply(content=reply_content)
        except:
            pass
