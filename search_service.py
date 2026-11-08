import xml.etree.ElementTree as ET

import aiohttp
from datetime import date

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


async def query_weather(city:str)->dict:
    """查询指定城市的当前天气。"""
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=20),
        trust_env=False,
    ) as session:
        async with session.get(
            f"https://wttr.in/{city}",
            params={"format": "j1"},
        ) as response:
            response.raise_for_status()
            data = await response.json(content_type=None)

    current=data["current_condition"][0]
    forecasts=[]
    for day in data["weather"]:
        forecasts.append({
            "date": day["date"],
            "min_temperature_c": day["mintempC"],
            "max_temperature_c": day["maxtempC"],
        })

    return{
        "city": city,
        "query_date": date.today().isoformat(),
        "temperature_c": current["temp_C"],
        "description": current["weatherDesc"][0]["value"],
        "humidity": current["humidity"],
        "forecasts": forecasts,
        "source": f"https://wttr.in/{city}",
    }


if __name__ == "__main__":
    import asyncio
    import json

    result = asyncio.run(query_weather("杭州"))
    print(json.dumps(result, ensure_ascii=False, indent=2))