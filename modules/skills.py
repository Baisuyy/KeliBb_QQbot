import os
import json

# Skill 库目录：把 .md/.txt 文件丢进去即自动入库（默认禁用，需 /inject skill enable 启用）
SKILLS_DIR = os.environ.get("QQBOT_SKILLS_DIR", "/opt/qqbot/skills")
STATE_FILE = os.environ.get("QQBOT_SKILL_STATE_FILE", "/opt/qqbot/skill_state.json")


def ensure_dir() -> None:
    os.makedirs(SKILLS_DIR, exist_ok=True)


def _load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"enabled": []}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"enabled": []}
        data.setdefault("enabled", [])
        return data
    except Exception:
        return {"enabled": []}


def _save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _available_files() -> dict:
    """扫描 skill 目录，返回 {skill名: 文件名}"""
    ensure_dir()
    out = {}
    try:
        for fname in sorted(os.listdir(SKILLS_DIR)):
            lower = fname.lower()
            if lower.endswith(".md") or lower.endswith(".txt"):
                stem = os.path.splitext(fname)[0]
                out[stem] = fname
    except OSError:
        pass
    return out


def list_skills() -> list:
    """列出所有 skill：[{name, file, enabled, chars}]"""
    enabled = set(_load_state().get("enabled", []))
    out = []
    for name, fname in _available_files().items():
        path = os.path.join(SKILLS_DIR, fname)
        try:
            chars = os.path.getsize(path)
        except OSError:
            chars = 0
        out.append({"name": name, "file": fname, "enabled": name in enabled, "chars": chars})
    return out


def match_skill(name: str):
    """模糊匹配 skill 名（忽略大小写、容忍带 .md/.txt 后缀），返回标准名或 None"""
    name = name.strip()
    for suffix in (".md", ".txt", ".MD", ".TXT"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    files = _available_files()
    if name in files:
        return name
    lower = name.lower()
    for candidate in files:
        if candidate.lower() == lower:
            return candidate
    return None


def set_skill(name: str, enabled: bool):
    """启用/禁用 skill，返回 (成功?, 消息)"""
    matched = match_skill(name)
    if not matched:
        return False, f"找不到 skill「{name}」，发送 /inject skill 查看列表"
    state = _load_state()
    enabled_list = state.setdefault("enabled", [])
    if enabled:
        if matched not in enabled_list:
            enabled_list.append(matched)
        _save_state(state)
        return True, f"✅ skill「{matched}」已启用，立即生效"
    if matched in enabled_list:
        enabled_list.remove(matched)
        _save_state(state)
        return True, f"🚫 skill「{matched}」已禁用，立即生效"
    return True, f"skill「{matched}」本来就是禁用状态"


def build_skills_context() -> str:
    """拼接所有启用中的 skill 内容，注入 system prompt（无启用时返回空串）"""
    enabled = _load_state().get("enabled", [])
    if not enabled:
        return ""
    files = _available_files()
    blocks = []
    for name in enabled:
        fname = files.get(name)
        if not fname:
            continue
        path = os.path.join(SKILLS_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
        except OSError:
            continue
        if content:
            blocks.append(f"【附加技能：{name}】\n{content}")
    if not blocks:
        return ""
    return "\n\n".join(blocks)
