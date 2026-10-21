"""Agent 工具调用：让 AI 自主决定调用搜索/状态/记忆/画图/发文等工具（function calling）"""
import json
import asyncio
import traceback
import aiohttp
from modules.config import AI_API_URL, AI_API_KEY, TTS_API_KEY, WP_URL, WP_USERNAME, WP_APPLICATION_PASSWORD
from modules.search import search_duckduckgo
from modules.monitor import get_server_status
from modules.memory import load_memory

MAX_TOOL_ROUNDS = 3
_IMAGE_MODEL = "wanx2.1-t2i-turbo"  # 复用阿里云 dashscope key

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "search_web",
        "description": "联网搜索最新信息、时事、资料。当用户问时效性问题、或你不确定的事实时使用",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "搜索关键词"}
        }, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "server_status",
        "description": "查看机器人所在服务器的实时运行状态（CPU/内存/磁盘）",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "query_memory",
        "description": "查询长期记忆库中关于某个人/事物的信息。当用户问「你还记得XX吗」「XX是谁」时使用",
        "parameters": {"type": "object", "properties": {
            "keyword": {"type": "string", "description": "要查的人名或事物关键词"}
        }, "required": ["keyword"]}}},
    {"type": "function", "function": {
        "name": "generate_image",
        "description": "根据文字描述生成一张图片。当用户明确要求画画/生成图片/画一个XX时使用",
        "parameters": {"type": "object", "properties": {
            "prompt": {"type": "string", "description": "图片内容描述，越具体效果越好"}
        }, "required": ["prompt"]}}},
]

ADMIN_TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "publish_article",
        "description": "把一篇文章发布到 WordPress 博客。仅当用户明确要求写文章/发博文时使用",
        "parameters": {"type": "object", "properties": {
            "title": {"type": "string", "description": "文章标题"},
            "content": {"type": "string", "description": "正文内容（支持HTML）"}
        }, "required": ["title", "content"]}}},
]


def build_tools(is_admin: bool) -> list:
    return TOOL_SCHEMAS + (ADMIN_TOOL_SCHEMAS if is_admin else [])


async def generate_image_url(prompt: str) -> str:
    """调用阿里云 wanx 文生图，返回图片 URL"""
    import dashscope  # 延迟导入

    def _call():
        dashscope.api_key = TTS_API_KEY  # 与 TTS 共用同一把阿里云 key
        resp = dashscope.ImageSynthesis.call(
            model=_IMAGE_MODEL, prompt=prompt[:500], n=1, size="1024*1024"
        )
        if resp.status_code != 200:
            raise RuntimeError(str(getattr(resp, "message", "") or getattr(resp, "code", "未知错误")))
        return resp.output.results[0].url

    return await asyncio.to_thread(_call)


async def execute_tool(name: str, arguments: str, is_admin: bool):
    """执行工具调用，返回 (给AI的结果文本, 附加媒体列表)"""
    media = []
    try:
        args = json.loads(arguments) if arguments else {}
        if not isinstance(args, dict):
            args = {}
    except json.JSONDecodeError:
        return "参数不是合法JSON", media

    try:
        if name == "search_web":
            return await search_duckduckgo(str(args.get("query", ""))[:200]), media
        if name == "server_status":
            return await get_server_status(), media
        if name == "query_memory":
            kw = str(args.get("keyword", ""))
            data = load_memory()
            hits = []
            for pname, info in data.get("people", {}).items():
                facts = "；".join(info.get("facts", []))
                if kw in pname or kw in facts:
                    hits.append(f"👤 {pname}：{facts}")
            things = [t for t in data.get("things", []) if kw in t]
            if things:
                hits.append("📌 " + "；".join(things[:5]))
            if hits:
                return "；".join(hits), media
            return f"记忆库中没有关于「{kw}」的信息", media
        if name == "generate_image":
            url = await generate_image_url(str(args.get("prompt", ""))[:500])
            media.append({"type": "image", "url": url})
            return f"图片已生成：{url}", media
        if name == "publish_article":
            if not is_admin:
                return "没有权限发布文章", media
            title = str(args.get("title", "")).strip()
            content = str(args.get("content", "")).strip()
            if not title or not content:
                return "标题和内容不能为空", media
            api_url = f"{WP_URL}/index.php?rest_route=/wp/v2/posts"
            auth = aiohttp.BasicAuth(WP_USERNAME, WP_APPLICATION_PASSWORD)
            async with aiohttp.ClientSession() as s:
                async with s.post(api_url, auth=auth,
                                  json={"title": title, "content": content, "status": "publish"},
                                  timeout=aiohttp.ClientTimeout(total=30)) as r:
                    if r.status == 201:
                        return f"已发布：{(await r.json()).get('link', '')}", media
                    return f"发布失败 HTTP {r.status}", media
        return f"未知工具：{name}", media
    except Exception as e:
        traceback.print_exc()
        return f"工具执行出错：{str(e)[:100]}", media


async def chat_with_tools(model: str, messages: list, is_admin: bool):
    """带工具的完整对话循环，返回 (回复文本, 媒体列表, 是否成功)。
    任何失败（模型不支持tools/超时/异常）返回 ok=False，由调用方回退普通流式对话。"""
    tools = build_tools(is_admin)
    msgs = [dict(m) for m in messages]
    media_all = []
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}

    try:
        async with aiohttp.ClientSession() as session:
            for _ in range(MAX_TOOL_ROUNDS + 1):
                payload = {"model": model, "messages": msgs, "tools": tools, "stream": False}
                async with session.post(AI_API_URL, headers=headers, json=payload,
                                        timeout=aiohttp.ClientTimeout(total=90)) as resp:
                    if resp.status != 200:
                        return "", media_all, False
                    data = await resp.json()

                choice = (data.get("choices") or [{}])[0]
                msg = choice.get("message") or {}
                tool_calls = msg.get("tool_calls")
                if not tool_calls:
                    reply = (msg.get("content") or "").strip()
                    return (reply or "？"), media_all, True

                msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls})
                for tc in tool_calls:
                    fn = tc.get("function") or {}
                    result_text, media = await execute_tool(fn.get("name", ""), fn.get("arguments", ""), is_admin)
                    media_all.extend(media)
                    msgs.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": result_text[:3000]})
        return "工具调用轮数超限了喵", media_all, True
    except Exception:
        traceback.print_exc()
        return "", media_all, False
