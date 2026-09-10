import aiohttp
import json
import asyncio

SEARXNG_INSTANCES = [
    "https://searx.be",
    "https://search.disroot.org",
    "https://searx.tiekoetter.com",
    "https://searx.feneas.org",
    "https://searx.nu",
]

async def search_searxng(query: str, max_results: int = 5) -> str:
    for instance in SEARXNG_INSTANCES:
        try:
            url = f"{instance}/search"
            params = {"q": query, "format": "json"}
            print(f"🔍 SearXNG 尝试: {instance}")
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status != 200:
                        print(f"❌ {instance} HTTP {resp.status}")
                        continue
                    data = await resp.json()
                    print(f"📦 {instance} 返回数据 keys: {list(data.keys())}")
                    results = data.get('results', [])
                    print(f"📦 {instance} 结果数量: {len(results)}")
                    if results:
                        formatted = []
                        for r in results[:max_results]:
                            title = r.get('title', '无标题')
                            content = r.get('content', '')[:150]
                            formatted.append(f"- {title}: {content}...")
                        return "\n".join(formatted)
                    else:
                        print(f"ℹ️ {instance} 无结果")
        except Exception as e:
            print(f"❌ {instance} 异常: {e}")
            continue
    return None

async def search_duckduckgo(query: str, max_results: int = 5) -> str:
    result = await search_searxng(query, max_results)
    if result:
        return result
    return "喵～没找到相关信息呢，试试更具体的关键词喵？"
