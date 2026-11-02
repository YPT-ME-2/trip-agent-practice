import asyncio
import json

import aiohttp
from compliance_service import check_hotel_cost
# 告诉模型：有哪些工具，以及工具需要什么参数。
tools = [
    {
        "type": "function",
        "function": {
            "name": "check_hotel_cost",
            "description": "根据城市和每人每晚报价，检查住宿是否超过公司限额。",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称，例如杭州",
                    },
                    "nightly_price": {
                        "type": "number",
                        "description": "每人每晚住宿报价，单位为元",
                    },
                },
                "required": ["city", "nightly_price"],
            },
        },
    }
]

async def main():
    messages = [
        {
            "role": "system",
           "content": (
                "你是差旅助手。涉及住宿限额判断时，调用工具查询，不要自行判断。"
                "收到工具结果后，只解释结果和用户已提供的信息。"
                "不得编造审批理由、审批流程或保证报销。"
                "用户提供报价不代表已经入住，不要推断入住、付款或退房状态。"
                "回答保持简短。"
            ),
        },
        {
            "role": "user",
            "content": "杭州酒店每人每晚450元，超过公司住宿标准了吗？",
        }
    ]

    async with aiohttp.ClientSession(
        trust_env=False,
        timeout=aiohttp.ClientTimeout(total=120),
    ) as session:
        async with session.post(
            "http://127.0.0.1:11434/api/chat",
            json={
                "model": "qwen3.5:9b",
                "messages": messages,
                "tools": tools,
                "stream": False,
                "think": False,
            },
        ) as response:
            response.raise_for_status()
            data = await response.json()

    print(json.dumps(data["message"], ensure_ascii=False, indent=2))

    handlers = {
        "check_hotel_cost": check_hotel_cost,
    }

    message = data["message"]
    messages.append(message)
    for tool_call in message.get("tool_calls", []):
        name = tool_call["function"]["name"]
        arguments = tool_call["function"]["arguments"]

        if name not in handlers:
            raise ValueError(f"不支持的工具：{name}")

        function = handlers[name]
        result = function(**arguments)

        print("执行工具：", name)
        print("传入参数：", arguments)
        print("工具结果：")
        print(json.dumps(result, ensure_ascii=False, indent=2))

        messages.append({
            "role": "tool",
            "tool_name": name,
            "tool_call_id": tool_call["id"],
            "content": json.dumps(result, ensure_ascii=False),
        })

    async with aiohttp.ClientSession(
        trust_env=False,
        timeout=aiohttp.ClientTimeout(total=120),
    ) as session:
        async with session.post(
            "http://127.0.0.1:11434/api/chat",
            json={
                "model": "qwen3.5:9b",
                "messages": messages,
                "stream": False,
                "think": False,
            },
        ) as response:
            response.raise_for_status()
            final_data = await response.json()

    print("\n最终回答：")
    print(final_data["message"]["content"])

if __name__ == "__main__":
    asyncio.run(main())