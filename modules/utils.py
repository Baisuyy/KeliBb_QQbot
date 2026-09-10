from botpy.message import Message

def get_session_id(message: Message, is_group=False):
    """所有用户共享同一个全局会话ID"""
    return "global"
