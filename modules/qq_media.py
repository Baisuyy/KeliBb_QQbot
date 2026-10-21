"""QQ 图片收发工具：下载图片转 data URL（识图）、把图片 URL 发到 QQ 会话"""
import base64
import aiohttp
from modules.config import APP_ID, APP_SECRET
from modules.commands import _get_qq_access_token


async def download_image_dataurl(url: str, max_mb: int = 10) -> str:
    """下载图片并转为 base64 data URL（发给多模态模型识图用）"""
    async with aiohttp.ClientSession() as s:
        async with s.get(url, timeout=aiohttp.ClientTimeout(total=30)) as r:
            if r.status != 200:
                raise RuntimeError(f"图片下载失败 HTTP {r.status}")
            data = await r.read()
    if len(data) > max_mb * 1024 * 1024:
        raise RuntimeError("图片超过10MB")
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        ctype = "image/png"
    elif data[:4] == b"GIF8":
        ctype = "image/gif"
    else:
        ctype = "image/jpeg"
    return f"data:{ctype};base64,{base64.b64encode(data).decode()}"


def _extract_attachment_url(att) -> str:
    """兼容 botpy Attachment 对象和原始 dict"""
    if isinstance(att, dict):
        return att.get("url") or ""
    return getattr(att, "url", None) or ""


async def send_media_message(client, message, is_group: bool, media: dict) -> bool:
    """把图片（media={"type":"image","url":...}）发到 QQ 会话，成功返回 True"""
    url = (media or {}).get("url")
    if not url:
        return False
    token = await _get_qq_access_token(APP_ID, APP_SECRET)
    if not token:
        print("⚠️ 图片发送失败：拿不到 access_token")
        return False

    headers = {"Authorization": f"QQBot {token}", "Content-Type": "application/json"}
    group_openid = None
    if is_group:
        group_openid = getattr(message, "group_openid", None) or getattr(message, "group_id", None)
        if not group_openid:
            return False
        upload_url = f"https://api.sgroup.qq.com/v2/groups/{group_openid}/files"
    else:
        user_id = (getattr(message.author, "user_openid", None)
                   or getattr(message.author, "openid", None)
                   or getattr(message.author, "id", None))
        if not user_id:
            return False
        upload_url = f"https://api.sgroup.qq.com/v2/users/{user_id}/files"

    try:
        # 上传拿 file_info（file_type=1 图片，支持 url 直传）
        async with aiohttp.ClientSession() as s:
            async with s.post(upload_url, headers=headers,
                              json={"file_type": 1, "url": url, "srv_send_msg": False}) as r:
                if r.status != 200:
                    print(f"⚠️ 图片上传失败 HTTP {r.status}: {(await r.text())[:150]}")
                    return False
                file_info = (await r.json()).get("file_info")
        if not file_info:
            return False

        from botpy.types.message import Media
        m = Media(file_info=file_info)
        if is_group:
            await client.api.post_group_message(
                group_openid=group_openid, msg_type=7, media=m,
                msg_id=getattr(message, "id", None))
        else:
            await client.api.post_c2c_message(
                openid=user_id, msg_type=7, media=m,
                msg_id=getattr(message, "id", None))
        return True
    except Exception as e:
        print(f"⚠️ 图片发送失败: {e}")
        return False
