import aiohttp

async def call_model(
        messages: list[dict],
        json_output:bool=False,
        ) -> str:
    """调用模型接口，返回模型输出。"""
    payload = {
        "model": "qwen3.5:9b",
        "messages": messages,
        "stream": False,
        "think": False,
    }
    if json_output:
        payload["format"] = "json"

    async with aiohttp.ClientSession(
        trust_env=False,
        timeout=aiohttp.ClientTimeout(total=120),
        ) as session:
        async with session.post(
            "http://127.0.0.1:11434/api/chat",
            json=payload
        ) as response:
            response.raise_for_status()
            data = await response.json()

    return data["message"]["content"]

