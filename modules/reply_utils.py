import re
from botpy.message import Message

async def send_reply(client, message: Message, reply_content: str, is_group: bool):
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
                    msg_id=getattr(message, 'id', None)
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
                    msg_id=getattr(message, 'id', None)
                )
            else:
                await message.reply(content=reply_content)
    except Exception as e:
        print(f"发送消息失败: {e}")
        try:
            await message.reply(content=reply_content)
        except:
            pass
