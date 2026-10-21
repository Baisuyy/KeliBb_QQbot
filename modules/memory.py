import os
import json
import asyncio
import re

# 长期记忆库文件（全群共享一份）；测试可用环境变量覆盖路径
MEMORY_FILE = os.environ.get("QQBOT_MEMORY_FILE", "/opt/qqbot/memory.json")

# 每次提取的节流间隔（秒），防止频繁调用 AI
EXTRACT_INTERVAL = 30
_last_extract_time = {}

# 触发提取的预过滤关键词（只有对话提到这些才调用 AI，省 token）
_EXTRACT_KEYWORDS = [
    "我叫", "我是", "叫", "名字", "外号", "记得", "记住", "别忘了", "别忘",
    "约定", "答应", "欠", "带", "买", "送", "喜欢", "讨厌", "爱吃", "爱玩",
    "以后", "回头", "到时候",
]


def load_memory() -> dict:
    """加载长期记忆库"""
    if not os.path.exists(MEMORY_FILE):
        return {"people": {}, "things": []}
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"people": {}, "things": []}
        data.setdefault("people", {})
        data.setdefault("things", [])
        return data
    except Exception:
        return {"people": {}, "things": []}


def save_memory(data: dict) -> None:
    os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def build_memory_context() -> str:
    """构建注入 system prompt 的长期记忆文本（无记忆时返回空串）"""
    data = load_memory()
    people = data.get("people", {})
    things = data.get("things", [])
    if not people and not things:
        return ""
    lines = ["\n【长期记忆】（你记得的人和事，聊天时自然引用即可，不要机械复述全部）"]
    for name, info in people.items():
        facts = info.get("facts", [])
        if facts:
            lines.append(f"- {name}：{'；'.join(facts[:3])}")
    for thing in things[-10:]:
        lines.append(f"- {thing}")
    return "\n".join(lines)


def _extract_json(raw: str) -> dict:
    """从 AI 回复中提取 JSON 对象（兼容 ```json 包裹）"""
    text = raw.strip()
    # 去掉 markdown 代码块
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    # 取第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return {}


def _should_extract(user_msg: str) -> bool:
    """预过滤：只有对话提到自我介绍/约定/喜好等才提取，省 token"""
    return any(k in user_msg for k in _EXTRACT_KEYWORDS)


async def extract_memories(ai, user_msg: str, reply: str) -> None:
    """对话结束后异步提取值得长期记住的人/事物（失败不影响主流程）"""
    try:
        if not _should_extract(user_msg):
            return
        now = asyncio.get_event_loop().time()
        if now - _last_extract_time.get("global", 0.0) < EXTRACT_INTERVAL:
            return
        _last_extract_time["global"] = now

        prompt = (
            "你是长期记忆提取器。根据下面的对话，提取值得长期记住的事实：\n"
            "1. 关于人：用户的名字/昵称、身份、喜好、厌恶、关系、习惯\n"
            "2. 关于事物：约定、承诺、账（欠钱/带东西）、重要事件、常用梗\n"
            '只输出 JSON：{"people": {"名字": ["事实1", "事实2"]}, "things": ["事物1", "事物2"]}\n'
            "没有的字段不要输出。不要输出空数组。\n"
            f"\n用户：{user_msg}\n机器人：{reply}"
        )

        # 用独立会话调用 AI，不污染正常聊天上下文
        sid = "__memory_extract__"
        ai.contexts[sid] = [{"role": "system", "content": "你是长期记忆提取器，只输出 JSON。"}]
        raw = await ai.chat(sid, prompt, is_group=False)
        try:
            from modules.context_persistence import delete_context
            delete_context(sid)
        except Exception:
            pass
        ai.contexts.pop(sid, None)

        result = _extract_json(raw)
        if not result:
            return

        data = load_memory()
        people = data.setdefault("people", {})
        things = data.setdefault("things", [])

        for name, facts in result.get("people", {}).items():
            if not isinstance(facts, list) or not name:
                continue
            info = people.setdefault(name, {"facts": []})
            for fact in facts:
                fact = str(fact).strip()
                if fact and fact not in info["facts"]:
                    info["facts"].append(fact)
            # 每个人最多保留 20 条事实
            info["facts"] = info["facts"][-20:]

        for thing in result.get("things", []):
            thing = str(thing).strip()
            if thing and thing not in things:
                things.append(thing)
        # 事物最多保留 50 条
        data["things"] = things[-50:]

        save_memory(data)
        print(f"🧠 记忆已更新：人物 {len(people)} 个，事物 {len(data['things'])} 条")
    except Exception as e:
        print(f"⚠️ 记忆提取失败: {e}")
