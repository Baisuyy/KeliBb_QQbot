import os
import json
from datetime import datetime

CONTEXT_DIR = "/opt/qqbot/contexts"
MAX_SAVED_MESSAGES = 200  # 每个会话最多保存 200 条消息（可配置）

def ensure_dir():
    os.makedirs(CONTEXT_DIR, exist_ok=True)

def get_file_path(session_id):
    return os.path.join(CONTEXT_DIR, f"context_{session_id}.json")

def save_context(session_id, messages):
    """保存上下文（只保留最近 MAX_SAVED_MESSAGES 条）"""
    ensure_dir()
    # 只保留最近 N 条（系统提示除外）
    if len(messages) > MAX_SAVED_MESSAGES + 1:
        system = messages[0] if messages and messages[0].get('role') == 'system' else None
        recent = messages[-MAX_SAVED_MESSAGES:] if messages else []
        if system:
            save_msgs = [system] + recent
        else:
            save_msgs = recent
    else:
        save_msgs = messages
    data = {
        "session_id": session_id,
        "last_save": datetime.now().isoformat(),
        "messages": save_msgs
    }
    with open(get_file_path(session_id), 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_context(session_id):
    """加载上下文，如果文件存在则返回消息列表，否则返回 None"""
    filepath = get_file_path(session_id)
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            return data.get('messages', [])
        except:
            return None
    return None

def delete_context(session_id):
    """删除会话的上下文文件（用于 /clear 命令）"""
    filepath = get_file_path(session_id)
    if os.path.exists(filepath):
        os.remove(filepath)
        return True
    return False

def list_sessions():
    """列出所有已保存的会话 ID"""
    ensure_dir()
    sessions = []
    for fname in os.listdir(CONTEXT_DIR):
        if fname.startswith('context_') and fname.endswith('.json'):
            sid = fname[8:-5]  # 去掉 'context_' 和 '.json'
            sessions.append(sid)
    return sessions
