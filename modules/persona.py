import os

# SKILL.md 位于项目根目录（本文件在 modules/ 下）
PERSONA_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "SKILL.md")

_persona_cache = None


def _strip_front_matter(content: str) -> str:
    """剥离 YAML front-matter（--- 开头的一段元数据），只保留正文"""
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            return content[end + 3:].strip()
    return content


def load_persona() -> str:
    """直接读取 SKILL.md 的人格提示词（去掉 front-matter），带缓存"""
    global _persona_cache
    if _persona_cache is None:
        with open(PERSONA_FILE, "r", encoding="utf-8") as f:
            _persona_cache = _strip_front_matter(f.read())
    return _persona_cache
