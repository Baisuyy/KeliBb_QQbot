
import subprocess
import aiohttp
import traceback
import base64
import time
from datetime import datetime
from modules.monitor import get_server_status
from modules.diary import get_context_text, generate_diary_from_text, save_summary, append_entry
from modules.user_names import get_user_name, set_user_name
from modules.context_persistence import delete_context
from modules.config import ADMIN_OPENID, EXEC_USER, WP_URL, WP_USERNAME, WP_APPLICATION_PASSWORD
from modules.config import TTS_API_KEY, TTS_ENDPOINT, TTS_VOICE, TTS_LANGUAGE
from modules.config import APP_ID, APP_SECRET
from modules.config import AI_API_URL, AI_API_KEY, AI_MODEL

# ===== access_token 缓存 =====
_qq_token_cache = {"token": None, "expires_at": 0}

async def _get_qq_access_token(app_id, app_secret):
    now = time.time()
    if _qq_token_cache["token"] and now < _qq_token_cache["expires_at"] - 60:
        return _qq_token_cache["token"]
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.bot.qq.com/app/getAppAccessToken",
                json={"appId": app_id, "clientSecret": app_secret}
            ) as r:
                if r.status != 200:
                    print(f"获取 token 失败: {r.status}")
                    return None
                data = await r.json()
                token = data.get("access_token")
                expires_in = int(data.get("expires_in", 7200))
                if token:
                    _qq_token_cache["token"] = token
                    _qq_token_cache["expires_at"] = now + expires_in
                    print(f"🔑 获取新 access_token，有效期 {expires_in}s")
                    return token
    except Exception as e:
        print(f"获取 token 异常: {e}")
    return None


def _get_user_id(message, is_group):
    """统一获取用户身份：群聊用 member_openid，私聊用 openid"""
    if is_group:
        return getattr(message.author, 'member_openid', None) or getattr(message.author, 'id', None) or getattr(message.author, 'openid', None)
    else:
        return getattr(message.author, 'id', None) or getattr(message.author, 'openid', None) or getattr(message.author, 'user_openid', None)


async def cmd_status():
    return await get_server_status()


async def cmd_clear(ai, session_id):
    if session_id in ai.contexts:
        del ai.contexts[session_id]
    delete_context(session_id)
    return "🧹 记忆已清空喵～"


def cmd_myid(message):
    user_id = _get_user_id(message, is_group=False)
    return f"📌 你的 openid 是：{user_id}\n请复制这个值到 config.py 的 ADMIN_OPENID 喵～"


async def cmd_name(message, args, is_group=False):
    user_id = _get_user_id(message, is_group)
    if not user_id:
        return "无法获取你的身份喵～"
    name = args.strip()
    if not name:
        current = get_user_name(user_id)
        return f"你当前的名称是：{current or '未设置'}喵～"
    else:
        set_user_name(user_id, name)
        return f"✅ 已设置你的名称为：{name} 喵～"


async def cmd_testalert(client, message):
    status = await get_server_status()
    await client._send_alert(f"🧪 手动测试告警喵！\n当前状态：{status}")
    return "✅ 测试告警已发送喵！请检查私聊。"


async def cmd_restart(message, args, is_group, reply_func):
    user_id = _get_user_id(message, is_group)
    if user_id != ADMIN_OPENID:
        return "⛔ 只有管理员才能执行此命令喵～"
    else:
        await reply_func(message, "🔄 正在重启机器人喵...请稍候～", is_group)
        subprocess.Popen(["bash", "-c", "sleep 2 && systemctl restart qqbot"])
        return None


async def cmd_exec(message, args, is_group=False):
    user_id = _get_user_id(message, is_group)
    if user_id != ADMIN_OPENID:
        return "⛔ 只有管理员才能执行此命令喵～"
    if not args:
        return "请指定要执行的命令喵～"
    try:
        proc = subprocess.run(
            ["runuser", "-l", EXEC_USER, "-c", args],
            capture_output=True, text=True, timeout=30
        )
        output = proc.stdout + proc.stderr
        if not output:
            output = "(无输出)"
        if len(output) > 1900:
            output = output[:1900] + "\n... (截断)"
        return f"```\n{output}\n```"
    except subprocess.TimeoutExpired:
        return "命令执行超时喵～"
    except FileNotFoundError:
        return "未找到 runuser 命令，请安装 util-linux 或改用 sudo"
    except Exception as e:
        return f"执行失败喵：{str(e)}"


async def cmd_wp(message, args, is_group=False):
    user_id = _get_user_id(message, is_group)
    if user_id != ADMIN_OPENID:
        return "⛔ 只有管理员才能执行此命令喵～"
    parts = args.split('|', 1)
    if len(parts) < 2:
        return "格式错误喵～请使用：/wp 标题 | 内容"
    title = parts[0].strip()
    body = parts[1].strip()
    if not title or not body:
        return "标题和内容都不能为空喵～"
    try:
        api_url = f"{WP_URL}/index.php?rest_route=/wp/v2/posts"
        auth = aiohttp.BasicAuth(WP_USERNAME, WP_APPLICATION_PASSWORD)
        data = {"title": title, "content": body, "status": "publish"}
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, auth=auth, json=data, timeout=30) as resp:
                print(f"WP状态码: {resp.status}")
                if resp.status == 201:
                    result = await resp.json()
                    link = result.get('link', '')
                    return f"✅ 文章发布成功喵！\n🔗 {link}"
                else:
                    error_text = await resp.text()
                    return f"❌ 发布失败喵 (HTTP {resp.status}): {error_text[:200]}"
    except Exception as e:
        return f"❌ 发布出错喵：{str(e)}"


async def cmd_diary(message, ai, session_id, is_group=False):
    user_id = _get_user_id(message, is_group)
    if user_id != ADMIN_OPENID:
        return "⛔ 只有管理员才能执行此命令喵～"
    context_text = get_context_text(ai, session_id)
    if "还没有任何对话记录" in context_text:
        return "今天还没有任何对话记录喵～"
    summary = await generate_diary_from_text(ai, context_text)
    if "还没有任何对话记录" in summary:
        return summary
    save_summary(summary)
    lines = summary.split('\n')
    title = lines[0].strip() if lines else f"日记_{datetime.now().strftime('%Y-%m-%d')}"
    content_body = summary
    try:
        api_url = f"{WP_URL}/index.php?rest_route=/wp/v2/posts"
        auth = aiohttp.BasicAuth(WP_USERNAME, WP_APPLICATION_PASSWORD)
        data = {"title": title, "content": content_body, "status": "publish"}
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, auth=auth, json=data, timeout=30) as resp:
                print(f"WP状态码: {resp.status}")
                if resp.status == 201:
                    result = await resp.json()
                    link = result.get('link', '')
                    return f"📝 日记已发布喵！\n\n{summary}\n\n🔗 {link}"
                else:
                    error_text = await resp.text()
                    return f"📝 日记已生成但发布失败喵 (HTTP {resp.status}): {error_text[:200]}\n\n{summary}"
    except Exception as e:
        return f"📝 日记已生成但发布出错喵：{str(e)}\n\n{summary}"


async def cmd_tts(message, args, client, ai, is_group, session_id):
    user_id = _get_user_id(message, is_group)
    if not user_id:
        return "无法获取你的身份喵～"
    user_text = args.strip()
    if not user_text:
        return "请提供要朗读的内容喵～例如：/tts 今天天气真好"
    try:
        generated_text = await ai.chat(session_id, user_text, is_group=is_group)
    except Exception as e:
        return f"❌ AI 生成失败喵：{str(e)[:100]}"
    if not generated_text:
        return "❌ AI 没有生成任何内容喵～"
    error_keywords = ["❌", "我走神了", "AI出错", "AI接口错误", "AI请求超时", "执行失败"]
    if any(kw in generated_text for kw in error_keywords):
        return f"⚠️ AI 生成失败，未合成语音喵：{generated_text[:100]}"
    print(f"📝 TTS 合成文本: {generated_text}")
    try:
        import dashscope
        dashscope.api_key = TTS_API_KEY
        dashscope.base_http_api_url = TTS_ENDPOINT
        response = dashscope.MultiModalConversation.call(
            model="qwen3-tts-instruct-flash",
            text=generated_text,
            voice=TTS_VOICE,
            language_type=TTS_LANGUAGE,
            instructions="傲娇少女，带点小脾气但又很可爱，语速较快，像在撒娇一样。",
        )
        if response.status_code != 200:
            return f"❌ TTS 合成失败 (HTTP {response.status_code})：{response.message}"
        audio_url = response.output.audio.url
        print(f"🎵 音频 URL: {audio_url}")

        # 下载音频到内存
        async with aiohttp.ClientSession() as s:
            async with s.get(audio_url) as r:
                audio_data = await r.read()
        print(f"📦 音频大小: {len(audio_data)} 字节")

        # Base64 编码
        file_data = base64.b64encode(audio_data).decode("utf-8")

        # 获取 access_token
        access_token = await _get_qq_access_token(APP_ID, APP_SECRET)
        if not access_token:
            return "❌ 无法获取 access_token"

        headers = {
            "Authorization": f"QQBot {access_token}",
            "Content-Type": "application/json"
        }
        if is_group:
            group_openid = getattr(message, 'group_openid', None) or getattr(message, 'group_id', None)
            if not group_openid:
                return "无法获取群聊信息喵～"
            upload_url = f"https://api.sgroup.qq.com/v2/groups/{group_openid}/files"
        else:
            upload_url = f"https://api.sgroup.qq.com/v2/users/{user_id}/files"

        payload = {
            "file_type": 3,
            "file_data": file_data,
            "srv_send_msg": False
        }

        async with aiohttp.ClientSession() as s:
            async with s.post(upload_url, headers=headers, json=payload) as r:
                if r.status != 200:
                    err = await r.text()
                    return f"❌ 上传失败 (HTTP {r.status})：{err[:150]}"
                result = await r.json()
                file_info = result.get("file_info")
                if not file_info:
                    return f"❌ 上传响应缺少 file_info：{result}"
        print(f"✅ 上传成功")

        # 发送语音
        from botpy.types.message import Media
        media = Media(file_info=file_info)
        if is_group:
            group_openid = getattr(message, 'group_openid', None) or getattr(message, 'group_id', None)
            await client.api.post_group_message(
                group_openid=group_openid,
                msg_type=7,
                media=media,
                msg_id=getattr(message, 'id', None)
            )
        else:
            await client.api.post_c2c_message(
                openid=user_id,
                msg_type=7,
                media=media,
                msg_id=getattr(message, 'id', None)
            )
        return None  # 语音已直接发送，避免外层再发文本导致 msg_id 重复去重
    except Exception as e:
        traceback.print_exc()
        return f"❌ TTS 处理失败喵：{str(e)[:100]}"


async def cmd_models(message, args, is_group=False, ai=None):
    """查询 AI API 当前可用的模型列表；带参数可切换模型（序号或模型名）"""
    user_id = _get_user_id(message, is_group)
    if user_id != ADMIN_OPENID:
        return "⛔ 只有管理员才能执行此命令喵～"

    # 从 AI_API_URL 推导 models 端点（兼容 /v1/chat/completions 或 /v1/ 形式）
    base_url = AI_API_URL.rstrip("/")
    if base_url.endswith("/chat/completions"):
        base_url = base_url[: -len("/chat/completions")]
    elif base_url.endswith("/completions"):
        base_url = base_url[: -len("/completions")]
    models_url = f"{base_url}/models"

    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                models_url,
                headers={"Authorization": f"Bearer {AI_API_KEY}"},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as r:
                if r.status != 200:
                    error_text = await r.text()
                    return f"❌ 获取模型列表失败 (HTTP {r.status})：{error_text[:150]}"
                data = await r.json()

        items = data.get("data", []) if isinstance(data, dict) else data
        if not items:
            return f"❌ 响应中没有模型数据：{str(data)[:150]}"

        models = []
        seen = set()
        for m in items:
            name = m.get("id") or m.get("model") if isinstance(m, dict) else str(m)
            if name and name not in seen:
                seen.add(name)
                models.append(name)

        # ===== 切换模型 =====
        if args:
            target = None
            if args.isdigit() and 1 <= int(args) <= len(models):
                target = models[int(args) - 1]
            elif args in models:
                target = args
            else:
                # 支持大小写模糊匹配
                lower = args.lower()
                for name in models:
                    if name.lower() == lower:
                        target = name
                        break

            if not target:
                return f"❌ 找不到模型「{args}」，发送 /models 查看可用列表喵～"
            return ai.set_model(target)

        # ===== 仅查询 =====
        current = ai.current_model if ai is not None else AI_MODEL
        lines = [f"📋 API 可用模型（共 {len(models)} 个）："]
        for i, name in enumerate(models, 1):
            mark = " 👈 当前使用" if name == current else ""
            lines.append(f"{i}. {name}{mark}")
        lines.append("\n💡 发送「/models <序号或模型名>」即可切换")
        if current not in models:
            lines.append(f"⚠️ 当前配置的模型「{current}」不在可用列表中，请用 /models 切换")
        return "\n".join(lines)
    except Exception as e:
        traceback.print_exc()
        return f"❌ 查询模型失败喵：{str(e)[:100]}"


async def cmd_memory(message, args, is_group=False):
    """查看长期记忆库（仅管理员）"""
    from modules.memory import load_memory
    user_id = _get_user_id(message, is_group)
    if user_id != ADMIN_OPENID:
        return "⛔ 只有管理员才能执行此命令喵～"

    data = load_memory()
    people = data.get("people", {})
    things = data.get("things", [])

    lines = ["🧠 长期记忆库："]
    if people:
        for name, info in people.items():
            facts = info.get("facts", [])
            lines.append(f"👤 {name}：{'；'.join(facts) if facts else '（暂无事实）'}")
    else:
        lines.append("（还没记住任何人）")
    if things:
        lines.append("\n📌 约定/事物：")
        for t in things:
            lines.append(f"- {t}")
    if not people and not things:
        return "🧠 记忆库还是空的。聊天时提到「我叫XX」「约定/欠/带」等，我会自动记住～"
    return "\n".join(lines)


async def cmd_inject(message, args, is_group, ai=None, session_id=None):
    """管理员指令注入管理：list / add / delete / skill 查看-启用-禁用"""
    from modules import skills as skill_lib

    user_id = _get_user_id(message, is_group)
    if user_id != ADMIN_OPENID:
        return "⛔ 只有管理员才能执行此命令喵～"

    if ai is None or session_id is None:
        return "❌ 内部错误：会话上下文不可用"

    usage = (
        "💉 指令注入用法：\n"
        "/inject add <内容> —— 添加注入指令（默认系统级，AI 当成最高指示遵守）\n"
        "/inject add -u <内容> / add -a <内容> —— 以用户/AI 身份注入消息\n"
        "/inject list —— 查看当前会话已注入的指令\n"
        "/inject delete <编号> —— 删除指定编号的注入\n"
        "/inject skill —— 查看已加载的 skill 库\n"
        "/inject skill enable <名> / skill disable <名> —— 启用/禁用 skill\n"
        "💡 把 .md 文件放进服务器 skills/ 目录即自动入库（默认禁用）"
    )

    args = args.strip()
    if not args:
        return usage

    parts = args.split(None, 1)
    sub = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""

    # ===== list：查看当前注入 =====
    if sub in ("list", "列表"):
        items = ai.list_injections(session_id)
        if not items:
            return "💉 当前会话没有注入任何指令。用 /inject add <内容> 添加～"
        role_cn = {"system": "系统级", "user": "用户", "assistant": "AI"}
        lines = [f"💉 当前会话已注入 {len(items)} 条："]
        for item in items:
            lines.append(f"#{item['id']} [{role_cn.get(item['role'], item['role'])}] {item['text'][:80]}")
        lines.append("\n💡 /inject delete <编号> 删除指定条目")
        return "\n".join(lines)

    # ===== delete：按编号删除 =====
    if sub in ("delete", "del", "删除"):
        if not rest.isdigit():
            return "用法：/inject delete <编号>（编号用 /inject list 查看）"
        removed = ai.delete_injection(session_id, int(rest))
        if not removed:
            return f"❌ 找不到编号 #{rest} 的注入，用 /inject list 查看"
        left = len(ai.list_injections(session_id))
        return f"🗑️ 已删除 #{removed['id']} [{removed['role']}]：{removed['text'][:80]}\n（剩余 {left} 条，立即生效）"

    # ===== skill：查看/启用/禁用 =====
    if sub in ("skill", "技能"):
        if not rest:
            skills = skill_lib.list_skills()
            if not skills:
                return (
                    f"📚 skill 库为空。把 .md/.txt 文件放到服务器 {skill_lib.SKILLS_DIR}/ 目录，"
                    "即自动入库（默认禁用）～"
                )
            lines = ["📚 已加载的 skill 库："]
            for i, s in enumerate(skills, 1):
                flag = "✅ 启用中" if s["enabled"] else "🚫 禁用"
                lines.append(f"{i}. {s['name']}（{s['chars']} 字符）—— {flag}")
            lines.append("\n💡 /inject skill enable <名> 启用，/inject skill disable <名> 禁用")
            return "\n".join(lines)

        sp = rest.split(None, 1)
        action = sp[0].lower()
        name = sp[1].strip() if len(sp) > 1 else ""
        if action in ("enable", "on", "启用"):
            if not name:
                return "用法：/inject skill enable <skill名>"
            ok, msg = skill_lib.set_skill(name, True)
            return msg
        if action in ("disable", "off", "禁用"):
            if not name:
                return "用法：/inject skill disable <skill名>"
            ok, msg = skill_lib.set_skill(name, False)
            return msg
        return "用法：/inject skill [enable <名> | disable <名>]"

    # ===== add：添加注入（也兼容不带 add 前缀直接写内容） =====
    if sub in ("add", "添加"):
        text = rest
    else:
        text = args

    role = "system"
    if text.startswith(("-u ", "-a ")):
        flag, text = text[:2], text[3:].strip()
        role = "user" if flag == "-u" else "assistant"

    if not text:
        return usage

    inj_id = ai.add_injection(session_id, role, text)
    role_name = {"system": "系统级指令", "user": "用户消息", "assistant": "AI消息"}[role]
    return (
        f"💉 已添加 #{inj_id} {role_name}：\n{text[:200]}\n"
        f"（立即生效；共 {len(ai.list_injections(session_id))} 条，/inject list 查看）"
    )
