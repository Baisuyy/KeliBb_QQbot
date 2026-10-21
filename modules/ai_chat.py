import json
import os
import aiohttp
import asyncio
import traceback
from datetime import datetime
from modules.config import AI_API_URL, AI_API_KEY, AI_MODEL, MAX_CONTEXT, MAX_TOKENS, COMPRESS_THRESHOLD, COMPRESS_TARGET, KEEP_RECENT
from modules.search import search_duckduckgo
from modules.context_manager import context_manager
from modules.context_persistence import load_context, save_context, delete_context
from modules.persona import load_persona
from modules.memory import build_memory_context
from modules.skills import build_skills_context

# 运行时模型切换的持久化文件
MODEL_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "model_state.json")
# 管理员指令注入注册表：{session_id: [{id, role, text}]}
INJECTIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "injections.json")


class AIChat:
    def __init__(self):
        self.contexts = {}
        self.current_model = self._load_saved_model()
        self.injections = self._load_injections()

    # ===== 管理员指令注入注册表 =====
    def _load_injections(self) -> dict:
        try:
            if os.path.exists(INJECTIONS_FILE):
                with open(INJECTIONS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            print(f"⚠️ 读取注入注册表失败: {e}")
        return {}

    def _save_injections(self) -> None:
        try:
            with open(INJECTIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.injections, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 保存注入注册表失败: {e}")

    def add_injection(self, session_id: str, role: str, text: str) -> int:
        """添加注入指令，返回分配的 ID"""
        items = self.injections.setdefault(session_id, [])
        next_id = max((i["id"] for i in items), default=0) + 1
        items.append({"id": next_id, "role": role, "text": text})
        self._save_injections()
        return next_id

    def list_injections(self, session_id: str) -> list:
        return self.injections.get(session_id, [])

    def delete_injection(self, session_id: str, inj_id: int):
        """按 ID 删除注入，成功返回被删条目，否则 None"""
        items = self.injections.get(session_id, [])
        for i, item in enumerate(items):
            if item["id"] == inj_id:
                removed = items.pop(i)
                self._save_injections()
                return removed
        return None

    def _apply_injections(self, session_id: str, messages: list) -> list:
        """把注入指令套到 API 消息上：system 插在主 system prompt 后，user/assistant 追加到末尾"""
        out = [{"role": m["role"], "content": m["content"]} for m in messages]
        items = self.injections.get(session_id, [])
        sys_items = [i for i in items if i["role"] == "system"]
        tail_items = [i for i in items if i["role"] != "system"]
        for pos, item in enumerate(sys_items, 1):
            out.insert(pos, {"role": "system", "content": f"【管理员指令 #{item['id']}（必须遵守）】{item['text']}"})
        for item in tail_items:
            out.append({"role": item["role"], "content": item["text"]})
        return out

    def _load_saved_model(self):
        """从持久化文件加载已切换的模型，没有则用 config 默认值"""
        try:
            if os.path.exists(MODEL_STATE_FILE):
                with open(MODEL_STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                saved = data.get("model")
                if saved:
                    print(f"🤖 已恢复上次切换的模型: {saved}")
                    return saved
        except Exception as e:
            print(f"⚠️ 读取模型状态失败: {e}")
        return AI_MODEL

    def set_model(self, model_name: str) -> str:
        """切换当前模型并持久化，返回结果说明"""
        if not model_name:
            return "❌ 模型名不能为空喵～"
        old = self.current_model
        self.current_model = model_name
        try:
            with open(MODEL_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump({"model": model_name}, f, ensure_ascii=False)
            return f"✅ 已从「{old}」切换到「{model_name}」喵～"
        except Exception as e:
            return f"✅ 已切换为「{model_name}」，但持久化失败：{e}"

    def load_all_contexts(self):
        """启动时加载所有已保存的上下文，并强制用 SKILL.md 人格刷新 system prompt"""
        from modules.context_persistence import list_sessions, load_context
        sessions = list_sessions()
        for sid in sessions:
            msgs = load_context(sid)
            if msgs:
                self.contexts[sid] = self._refresh_persona(msgs)
                print(f"📂 加载会话 {sid}，共 {len(msgs)} 条消息")
        print(f"✅ 加载了 {len(self.contexts)} 个会话")

    def _build_persona_prompt(self, is_group: bool) -> str:
        """组装 system prompt：人格 + 长期记忆 + 启用中的技能 + 群聊/私聊格式规则"""
        persona = load_persona()
        mem = build_memory_context()
        skills_txt = build_skills_context()
        today = datetime.now().strftime("%Y年%m月%d日")
        sys_prompt = f"{today}。\n{persona}\n"
        if mem:
            sys_prompt += f"{mem}\n"
        if skills_txt:
            sys_prompt += f"\n{skills_txt}\n"
        if is_group:
            sys_prompt += (
                "群聊中可使用 Markdown 语法美化回复：\n"
                "用 ``` 包裹代码块，用 **加粗** 强调重点，\n"
                "用有序/无序列表组织信息。\n"
            )
        else:
            sys_prompt += "禁止使用任何Markdown语法（如 # * - ``` 等），只输出纯文本。\n"
        return sys_prompt

    def _refresh_persona(self, msgs):
        """替换会话中的 system prompt 为当前 SKILL.md 人格 + 长期记忆 + 技能（保留历史消息）"""
        sys_prompt = self._build_persona_prompt(is_group=True)
        history = [dict(m) for m in msgs[1:]] if msgs and msgs[0].get("role") == "system" else [dict(m) for m in msgs]
        # 清理旧版直接写进上下文的注入消息（现改为注册表统一管理）
        history = [m for m in history if not str(m.get("content", "")).startswith("【管理员指令")]
        return [{"role": "system", "content": sys_prompt}] + history

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
            user_message = f"用户想搜索：{query}\n\n搜索结果：\n{search_result}\n\n请根据这些搜索结果回答用户，保持你的人格设定。"

        # 初始化上下文（如果不存在，尝试从文件加载）
        if session_id not in self.contexts:
            loaded = load_context(session_id)
            if loaded:
                self.contexts[session_id] = self._refresh_persona(loaded)
            else:
                self.contexts[session_id] = [{"role": "system", "content": self._build_persona_prompt(is_group)}]

        context = self.contexts[session_id]
        # 跨天检查与压缩
        context = context_manager.check_day_change(context)
        self.contexts[session_id] = context

        context.append({"role": "user", "content": user_message})
        # 套用管理员注入指令后再发给 API
        messages = self._apply_injections(session_id, [context[0]] + context[-MAX_CONTEXT:])

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
            "model": self.current_model,
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
                    reply = full.strip() or "？"
                    context.append({"role": "assistant", "content": reply})
                    if len(context) > MAX_CONTEXT + 1:
                        self.contexts[session_id] = [context[0]] + context[-(MAX_CONTEXT):]
                    else:
                        self.contexts[session_id] = context
                    # 保存到文件（只保留最近 N 条）
                    save_context(session_id, self.contexts[session_id])
                    return reply
        except asyncio.TimeoutError:
            return "超时了。"
        except Exception as e:
            print(f"AI调用异常: {traceback.format_exc()}")
            return f"出错了: {str(e)[:50]}"
