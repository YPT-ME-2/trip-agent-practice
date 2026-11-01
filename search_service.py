import xml.etree.ElementTree as ET

import aiohttp


async def search_information(query: str) -> list[dict]:
    """查询必应 RSS 搜索结果，返回标题、来源链接和摘要。"""
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=20),
        trust_env=False,
    ) as session:
        async with session.get(
            "https://cn.bing.com/search",
            params={"q": query, "format": "rss", "mkt": "zh-CN"},
        ) as response:
            if response.status != 200:
                raise RuntimeError(f"搜索请求失败，HTTP 状态码：{response.status}")
            content = await response.read()

    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise RuntimeError("搜索服务没有返回预期格式，请稍后重试") from exc

    if root.tag != "rss":
        raise RuntimeError("搜索服务没有返回预期的 RSS 搜索结果")

    results = []
    for item in root.findall("./channel/item")[:3]:
        results.append({
            "title": item.findtext("title", default=""),
            "url": item.findtext("link", default=""),
            "snippet": item.findtext("description", default=""),
        })

    return results
