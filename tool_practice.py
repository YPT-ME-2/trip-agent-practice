import asyncio
import json

import aiohttp
from compliance_service import check_hotel_cost
from search_service import query_weather,search_information
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
    },
    {
        "type": "function",
        "function": {
            "name": "query_weather",
            "description": "查询指定城市的当前天气及接口提供的每日气温预报。",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "要搜索的关键词或问题",
                    },
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_information",
            "description": "搜索目的地、景点和交通等公开网页信息，返回标题、链接和摘要。",
                        "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "要搜索的关键词或问题，例如杭州西湖主要景点",
                    },
                },
                "required": ["query"],
            },
        },
    },
]

async def run_tool_agent(question: str) -> str:
    messages = [
        {
            "role": "system",
           "content": (
                "你是差旅助手。涉及住宿限额判断时，调用工具查询，不要自行判断。"
                "收到工具结果后，继续判断用户要求是否全部完成。"
                "如果用户设置的条件成立，且后续任务需要工具，继续调用对应工具。"
                "全部任务完成后再给最终回答，不要用文字描述代替实际工具调用。"
                "不得编造审批理由、审批流程或保证报销。"
                "用户提供报价不代表已经入住，不要推断入住、付款或退房状态。"
                "回答保持简短。"
                "涉及天气问题时，调用query_weather工具，不要凭空回答。"
                "天气工具中的query_date表示查询当天的日期。"
                "今天、明天、后天分别对应query_date当天、加一天、加两天。"
                "查询预报时，按forecasts中对应的date取值，不要默认取第一条。"
                "用户要求搜索公开信息时，调用search_information工具。"
                "根据搜索结果回答并附来源链接；资料不足时说明，不编造。"
                "temperature_c、description、humidity仅表示当前天气。"
                "forecasts仅提供各日期的最低和最高气温，不能据此补充未来天气描述或湿度。"
            ),
        },
        {
            "role": "user",
            "content": question,
        }
    ]    
    handlers = {
        "check_hotel_cost": check_hotel_cost,
        "query_weather": query_weather,
        "search_information": search_information,
    }

    async with aiohttp.ClientSession(
            trust_env=False,
            timeout=aiohttp.ClientTimeout(total=120),
        ) as session:
            while True:
            # 每一轮都把已有消息和工具说明交给模型
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
                message = data["message"]
                messages.append(message)

                print("\n模型返回：")
                print(json.dumps(data["message"], ensure_ascii=False, indent=2))

                tool_calls=message.get("tool_calls", [])

                # 不再请求工具，说明本次回答结束
                if not tool_calls:
                    return message["content"]


                for tool_call in message.get("tool_calls", []):
                    name = tool_call["function"]["name"]
                    arguments = tool_call["function"]["arguments"]
                    function = handlers[name]

                    if name in ("query_weather", "search_information"):
                        result = await function(**arguments)
                    else:
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

async def main():
    question = input("请输入问题：")
    answer = await run_tool_agent(question)

    print("\n最终回答：")
    print(answer)

if __name__ == "__main__":
    asyncio.run(main())