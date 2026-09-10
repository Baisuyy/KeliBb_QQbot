import os
from datetime import datetime

DIARY_DIR = "/var/log/qqbot_diary"

def ensure_dir():
    os.makedirs(DIARY_DIR, exist_ok=True)

def append_entry(entry: str):
    ensure_dir()
    date_str = datetime.now().strftime("%Y-%m-%d")
    filepath = os.path.join(DIARY_DIR, f"日记_{date_str}.txt")
    with open(filepath, 'a', encoding='utf-8') as f:
        f.write(entry + "\n")

def get_today_diary() -> str:
    ensure_dir()
    date_str = datetime.now().strftime("%Y-%m-%d")
    filepath = os.path.join(DIARY_DIR, f"日记_{date_str}.txt")
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    return ""

def save_summary(content: str, date_str: str = None):
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    filepath = os.path.join(DIARY_DIR, f"总结_{date_str}.txt")
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

def get_context_text(ai, session_id: str) -> str:
    """从 ai 实例获取上下文文本"""
    contexts = ai.contexts
    if session_id not in contexts:
        return "今天还没有任何对话记录喵～"
    context = contexts[session_id]
    messages = context[1:] if len(context) > 1 else []
    if not messages:
        return "今天还没有任何对话记录喵～"
    lines = []
    for msg in messages:
        role = msg.get('role', '')
        content = msg.get('content', '')
        if role == 'user':
            lines.append(f"用户: {content}")
        elif role == 'assistant':
            lines.append(f"可丽堡堡: {content}")
    return "\n".join(lines)

async def generate_diary_from_text(ai, context_text: str) -> str:
    """调用 AI 生成日记总结"""
    if not context_text.strip():
        return "今天还没有任何对话记录喵～"
    prompt = f"请根据以下今天的对话记录，写一篇详细的日记喵～要求：\n1. 先写一个标题，格式为「2026年X月X日 星期X 天气：XXX」\n2. 天气可以虚构（比如晴、多云、小雨等）\n3. 描述今天的心情（比如开心、平静、有点累等）\n4. 总结今天的主要对话内容，尽量详细\n5. 最后写一点自己的感悟或期待\n\n对话记录：\n{context_text}\n\n请用猫娘风格写，每句话末尾带'喵'，内容要丰富，不少于200字。"
    old_context = ai.contexts.get("global", [])
    sys_prompt = old_context[0] if old_context else {"role": "system", "content": "你是一只可爱的猫娘，名叫可丽堡堡。"}
    ai.contexts["global"] = [sys_prompt, {"role": "user", "content": prompt}]
    reply = await ai.chat("global", prompt, is_group=False)
    if old_context:
        ai.contexts["global"] = old_context
    else:
        del ai.contexts["global"]
    return reply
