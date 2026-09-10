import json
import aiohttp
import asyncio
import traceback
from datetime import datetime
from modules.config import AI_API_URL, AI_API_KEY, AI_MODEL, MAX_CONTEXT, MAX_TOKENS, COMPRESS_THRESHOLD, COMPRESS_TARGET, KEEP_RECENT
from modules.search import search_duckduckgo
from modules.context_manager import context_manager
from modules.context_persistence import load_context, save_context, delete_context

class AIChat:
    def __init__(self):
        self.contexts = {}

    def load_all_contexts(self):
        """启动时加载所有已保存的上下文"""
        from modules.context_persistence import list_sessions, load_context
        sessions = list_sessions()
        for sid in sessions:
            msgs = load_context(sid)
            if msgs:
                self.contexts[sid] = msgs
                print(f"📂 加载会话 {sid}，共 {len(msgs)} 条消息")
        print(f"✅ 加载了 {len(self.contexts)} 个会话")

    async def chat(self, session_id: str, user_message: str, is_group: bool) -> str:
        print(f"📨 收到消息: {user_message}")

        # 联网搜索触发
        search_triggers = ["搜索", "查一下", "找一下", "查询", "搜一下", "search"]
        should_search = False
        query = user_message.strip()
        for kw in search_triggers:
            if kw in user_message:
                query = user_message.replace(kw, "").strip()
                if query and len(query) > 1:
                    should_search = True
                break

        if should_search and query:
            print(f"🔍 触发搜索: {query}")
            search_result = await search_duckduckgo(query)
            user_message = f"用户想搜索：{query}\n\n搜索结果：\n{search_result}\n\n请根据这些搜索结果用中文回答用户，保持猫娘语气，每句话末尾带'喵'。"

        # 初始化上下文（如果不存在，尝试从文件加载）
        if session_id not in self.contexts:
            loaded = load_context(session_id)
            if loaded:
                self.contexts[session_id] = loaded
            else:
                today = datetime.now().strftime("%Y年%m月%d日")
                if is_group:
                    sys_prompt = (
                        f"{today}。\n"
                        "你是一只可爱的猫娘，名叫可丽堡堡。(必须记住这个名字)\n"
                        "自然的中文口语，每句话末尾带一个'喵'字。你还是个大小姐\n"
                        "你可以使用Markdown语法美化回复：\n"
                        "用 ``` 包裹代码块，用 **加粗** 强调重点，\n"
                        "用有序/无序列表组织信息。\n"
                        "禁止使用英文、过多emoji。\n"
                        "据说你是由吕纹蔷蒸馏来的。\n"
                       # "问到与你相关的问题，可以发送https://kelibb.top这个网站，让用户了解更多(极少概率)。其他用户隐私不要暴露"
                    )
                else:
                    sys_prompt = (
                        f"{today}。\n"
                        "你是一只可爱的猫娘，名叫可丽堡堡。(必须记住这个名字)\n"
                        "简洁自然的中文口语，每句话末尾带一个'喵'字。你还是个大小姐\n"
                        "禁止使用任何Markdown语法（如 # * - ``` 等），只输出纯文本。\n"
                        "禁止使用英文、过多emoji。\n"
                        "据说你是由吕纹蔷蒸馏来的。\n"
                     #   "问到与你相关的问题，可以发送https://kelibb.top这个网站，让用户了解更多(极少概率)。其他用户隐私不要暴露"
                    )
                self.contexts[session_id] = [{"role": "system", "content": sys_prompt}]

        context = self.contexts[session_id]
        # 跨天检查与压缩
        context = context_manager.check_day_change(context)
        self.contexts[session_id] = context

        context.append({"role": "user", "content": user_message})
        messages = [context[0]] + context[-MAX_CONTEXT:]

        # ===== Token 管理 =====
        try:
            tokens = context_manager.count_tokens(messages)
            print(f"📊 Token: {tokens} / {MAX_TOKENS}")

            if context_manager.needs_compression(messages):
                print("🔄 触发上下文压缩...")
                system_msg, old_msgs, recent_msgs = context_manager.prepare_for_compression(messages)
                if old_msgs:
                    summary_text = context_manager.get_summary_text(old_msgs)
                    compressed = [system_msg]
                    compressed.append({"role": "user", "content": summary_text})
                    compressed.extend(recent_msgs)
                    messages = compressed
                    print(f"✅ 压缩完成，新 Token: {context_manager.count_tokens(messages)}")
            else:
                messages = context_manager.trim_to_budget(messages)
                print(f"📊 裁剪后 Token: {context_manager.count_tokens(messages)}")
        except Exception as e:
            print(f"⚠️ Token 管理跳过: {e}")
        # ===== Token 管理结束 =====

        headers = {
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": AI_MODEL,
            "messages": messages,
            "stream": True
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    AI_API_URL,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        return f"❌ AI接口错误 (HTTP {resp.status}): {error_text[:100]}"
                    full = ""
                    async for line in resp.content:
                        line = line.decode('utf-8').strip()
                        if not line:
                            continue
                        if line.startswith("data: "):
                            data = line[6:]
                            if data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                                choices = chunk.get("choices")
                                if choices and len(choices) > 0:
                                    delta = choices[0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        full += content
                                else:
                                    # 可能为空或结束标记，忽略
                                    pass
                            except json.JSONDecodeError as e:
                                print(f"⚠️ JSON解析失败: {e}, 原始数据: {data[:100]}")
                                continue
                    reply = full.strip() or "喵～ 我走神了，再说一遍好不好？"
                    context.append({"role": "assistant", "content": reply})
                    if len(context) > MAX_CONTEXT + 1:
                        self.contexts[session_id] = [context[0]] + context[-(MAX_CONTEXT):]
                    else:
                        self.contexts[session_id] = context
                    # 保存到文件（只保留最近 N 条）
                    save_context(session_id, self.contexts[session_id])
                    return reply
        except asyncio.TimeoutError:
            return "❌ AI请求超时喵～"
        except Exception as e:
            print(f"AI调用异常: {traceback.format_exc()}")
            return f"❌ AI出错喵: {str(e)[:50]}"
