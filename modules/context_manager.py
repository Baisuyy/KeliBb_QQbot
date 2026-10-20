import json
import tiktoken
from datetime import datetime
from modules.config import MAX_TOKENS, COMPRESS_THRESHOLD, COMPRESS_TARGET, KEEP_RECENT
from modules.persona import load_persona

class ContextManager:
    def __init__(self):
        self.encoding = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, messages):
        try:
            text = json.dumps(messages, ensure_ascii=False)
            return len(self.encoding.encode(text))
        except:
            return 0

    def trim_to_budget(self, messages):
        if not messages or len(messages) < 2:
            return messages
        while self.count_tokens(messages) > MAX_TOKENS and len(messages) > 2:
            messages.pop(1)
        return messages

    def needs_compression(self, messages):
        if len(messages) <= KEEP_RECENT + 1:
            return False
        return self.count_tokens(messages) > MAX_TOKENS * COMPRESS_THRESHOLD

    def prepare_for_compression(self, messages):
        if not messages:
            return None, [], []
        system_msg = messages[0] if messages[0].get('role') == 'system' else None
        if not system_msg:
            system_msg = {"role": "system", "content": load_persona()}
            old_msgs = messages[: -KEEP_RECENT] if len(messages) > KEEP_RECENT else []
            recent_msgs = messages[-KEEP_RECENT:] if len(messages) > KEEP_RECENT else messages
        else:
            old_msgs = messages[1:-KEEP_RECENT] if len(messages) > KEEP_RECENT + 1 else []
            recent_msgs = messages[-KEEP_RECENT:] if len(messages) > KEEP_RECENT + 1 else messages[1:]
        return system_msg, old_msgs, recent_msgs

    def get_summary_text(self, old_msgs):
        if not old_msgs:
            return ""
        lines = ["早期对话摘要："]
        for m in old_msgs:
            role = m.get('role', '')
            content = m.get('content', '')[:100]
            if role == 'user':
                lines.append(f"用户说：{content}")
            elif role == 'assistant':
                lines.append(f"助手说：{content}")
        return "\n".join(lines)


    def check_day_change(self, messages):
        """检测是否进入新的一天，如果是则压缩早期消息"""
        if not messages or len(messages) < 2:
            return messages
        # 获取最后一条消息的时间（假设消息中包含时间戳？）
        # 由于我们没有存储时间戳，我们可以基于系统时间判断是否跨天
        # 简单做法：每次调用时检查当前日期，如果与上次记录不同，则触发压缩
        # 但需要存储上次日期，我们使用一个文件记录
        import os, json
        date_file = "/opt/qqbot/last_date.json"
        today = datetime.now().strftime("%Y-%m-%d")
        last_date = None
        if os.path.exists(date_file):
            with open(date_file, 'r') as f:
                last_date = json.load(f).get('last_date')
        if last_date != today:
            # 跨天了，压缩早期消息（保留最近 KEEP_RECENT 条）
            if len(messages) > KEEP_RECENT + 1:
                system = messages[0] if messages[0].get('role') == 'system' else None
                recent = messages[-KEEP_RECENT:] if KEEP_RECENT > 0 else []
                if system:
                    new_msgs = [system] + recent
                else:
                    new_msgs = recent
                # 添加一条系统提示说明日期变化
                new_msgs.insert(1 if system else 0, {"role": "system", "content": f"（日期从 {last_date} 变为 {today}，之前的对话已压缩，仅保留最近 {KEEP_RECENT} 条记录。）"})
                messages = new_msgs
            # 更新日期记录
            with open(date_file, 'w') as f:
                json.dump({'last_date': today}, f)
        return messages

context_manager = ContextManager()
