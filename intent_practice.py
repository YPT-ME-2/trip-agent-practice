import asyncio
import json

# import aiohttp
from llm_service import call_model
from pathlib import Path

from search_service import search_information

from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from policy_service import PolicyService
from compliance_service import check_hotel_cost
policy_service = PolicyService()

async def recognize_intent(question:str)->dict:
    """把用户的话整理成出行需求。"""
    messages = [
        {
            "role": "system",
            "content": """
你是差旅助手，负责提取用户需求。

请返回 JSON，包含以下字段：
- intent：行程规划用 itinerary_planning，其他需求用 other
仅询问差旅报销标准、交通标准或审批规定用 policy_query;
仅要求记住或更新酒店品牌偏好，使用 preference_save。
其他需求用 other。
- origin：出发地
- destination：目的地
- date：出发日期
- duration：出行时长
- hotel_preference：酒店偏好
- tasks：任务列表，按以下规则返回：
  行程规划默认返回 ["search", "policy"]。
  如果用户明确要求不联网，返回 ["policy"]。
  非行程规划需求返回 []。

用户没提供的信息填 null，不要猜测。
只提取信息，不生成行程。
用户没提供的信息填 null，不要猜测。
日期保留用户原始表达，例如“11月5日”，未提供年份时不要补充年份。
只提取信息，不生成行程。
""",
        },
        {
            "role": "user",
            "content": question,
        },
    ]

    # async with aiohttp.ClientSession() as session:
    #     async with session.post(
    #         "http://127.0.0.1:11434/api/chat",
    #         json={
    #             "model": "qwen3.5:9b",
    #             "messages": messages,
    #             "stream": False,
    #             "think": False,
    #             "format": "json",
    #         },
    #     ) as response:
    #         # response.raise_for_status()
    #         # data = await response.json()
    #         if response.status == 401:
    #             raise RuntimeError("搜索认证失败，请检查 SERPAPI_KEY 是否为有效的 SerpAPI 密钥")

    #         if response.status >= 400:
    #             raise RuntimeError(f"搜索请求失败，HTTP 状态码：{response.status}")

    #         data = await response.json()

    # return json.loads(data["message"]["content"])

    text = await call_model(messages, json_output=True)
    return json.loads(text)

async def generate_plan(
        requirements: dict,
        search_results:list[dict],
        policy_results: list[dict],
        ) -> str:
    """根据结构化需求生成行程草案。"""
    messages = [
        {
            "role": "system",
            "content": """
你是差旅行程规划助手，请根据用户需求生成简洁的行程草案。

要求：
1. 按天安排交通、住宿和出差活动。
2. 尊重用户的酒店偏好。
3. 未提供的会议地点和时间，标注“待确认”，不要自行编造。
4. 参考提供的搜索资料安排交通，资料没有说明的信息标注“待确认”。
5. 网页摘要不代表实时票务和房态，不要编造具体班次、价格或余房。
6. 使用搜索资料时标注对应的来源链接。
7. 只输出行程草案。
日期没有年份时，不要推断星期几。
根据提供的差旅政策安排方案，并注明政策来源。
个人酒店偏好不能覆盖企业规定。
没有实际酒店报价时，不能宣称酒店符合住宿报销上限。
未检索到的政策事项，不要自行编造。
""",
        },
        {
            "role": "user",
            # "content": json.dumps(requirements, ensure_ascii=False),
            "content": json.dumps(
                {
                    "出行需求": requirements,
                    "搜索资料": search_results,
                    "差旅政策": policy_results,
                },
                ensure_ascii=False,
            ),
        },
    ]

    # async with aiohttp.ClientSession() as session:
    #     async with session.post(
    #         "http://127.0.0.1:11434/api/chat",
    #         json={
    #             "model": "qwen3.5:9b",
    #             "messages": messages,
    #             "stream": False,
    #             "think": False,
    #         },
    #     ) as response:
    #         response.raise_for_status()
    #         data = await response.json()

    # return data["message"]["content"]
    text = await call_model(messages,json_output=False)
    return text

# 偏好文件和当前 Python 文件放在同一个目录
PREFERENCE_FILE = Path(__file__).parent / "preferences.json"

def load_preference()->dict:
    """读取之前保存的偏好。"""
    if not PREFERENCE_FILE.exists():
        return {}

    text=PREFERENCE_FILE.read_text(encoding="utf-8")
    return json.loads(text)

def save_preferences(preferences: dict):
    """把偏好保存到文件。"""
    text = json.dumps(preferences, ensure_ascii=False, indent=2)
    PREFERENCE_FILE.write_text(text, encoding="utf-8")

class TravelState(TypedDict):
    requirements: dict
    search_results: list[dict]
    policy_results: list[dict]
    plan: str

async def search_node(state: TravelState):
    print("执行：搜索节点")

    requirements = state["requirements"]
    origin = requirements["origin"]
    destination = requirements["destination"]

    query= f"{origin}到{destination} 交通方式 {destination}市内交通"
    results = await search_information(query)

    return {"search_results": results}

async def plan_node(state: TravelState):
    print("执行：规划节点")

    plan = await generate_plan(
        state["requirements"],
        state["search_results"],
        state["policy_results"],
    )
    return {"plan": plan}

async def policy_node(state:TravelState):
    print("执行：政策检索节点")

    destination = state["requirements"]["destination"]
    query = f"去{destination}出差的住宿、交通和审批规定"

    results = await policy_service.search(query)

    for item in results:
        print("政策条款：", item["content"])

    return {"policy_results": results}

async def execute_tasks_node(state: TravelState):
    handlers = {
        "search": search_node,
        "policy": policy_node,
    }
    tasks = state["requirements"].get("tasks", ["search", "policy"])

    if "policy" not in tasks:
        tasks = tasks+["policy"]
    jobs=[]

    for name in tasks:
        if name not in handlers:
            raise ValueError(f"不支持的任务：{name}")

        function = handlers[name]
        jobs.append(function(state))

    outputs = await asyncio.gather(*jobs)

    updates={}

    for output in outputs:
        updates.update(output)

    return updates

# builder = StateGraph(TravelState)

# builder.add_node("search", search_node)
# builder.add_node("policy", policy_node)
# builder.add_node("plan", plan_node)


# # 两个任务都从起点出发
# builder.add_edge(START, "search")
# builder.add_edge(START, "policy")
# builder.add_edge(["search","policy"], "plan")
# builder.add_edge("plan", END)

builder = StateGraph(TravelState)

builder.add_node("execute_tasks", execute_tasks_node)
builder.add_node("plan", plan_node)

builder.add_edge(START, "execute_tasks")
builder.add_edge("execute_tasks", "plan")
builder.add_edge("plan", END)

graph = builder.compile()

async def answer_policy(question: str) -> str:
    print("正在检索差旅政策……")
    await policy_service.load()
    documents=await policy_service.search(question)

    messages=[
        {
            "role": "system",
            "content": """
你是企业差旅政策助手。
只根据提供的政策条款回答，并注明政策来源。
资料没有明确说明时，回答“现有政策资料无法确认”。
不要自行补充报销或审批规则。
""",
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "问题": question,
                    "政策条款": documents,
                },
                ensure_ascii=False,
            ),
        }
    ]

    # async with aiohttp.ClientSession() as session:
    #     async with session.post(
    #         "http://127.0.0.1:11434/api/chat",
    #         json={
    #             "model": "qwen3.5:9b",
    #             "messages": messages,
    #             "stream": False,
    #             "think": False,
    #         },
    #     ) as response:
    #         response.raise_for_status()
    #         data = await response.json()

    # return data["message"]["content"]

    text = await call_model(messages, json_output=False)
    return text

async def plan_trip(
        question:str,
        requirements: dict | None = None,
        nightly_price: float | None = None,
        )-> dict:
    if requirements is None:
        requirements = await recognize_intent(question)
    if requirements.get("intent") != "itinerary_planning":
        return {
            "status": "unsupported",
            "answer": "请描述需要规划的出差行程。",
        }
    required_fields={
        "origin": "出发地",
        "destination": "目的地",
        "date": "出发日期",
        "duration": "出行时长",
    }

    missing=[]

    for field,label in required_fields.items():
        if not requirements.get(field):
            missing.append(label)

    if missing:
        return {
            "status": "needs_information",
            "missing": missing,
            "answer": "请补充：" + "、".join(missing),
        }
    preferences=load_preference()

    if requirements.get("hotel_preference"):
        # 本次明确说了酒店偏好，就保存或更新
        preferences["hotel_preference"] = requirements["hotel_preference"]
        save_preferences(preferences)
    else:
        # 本次没说，就使用之前保存的偏好
        requirements["hotel_preference"] = preferences.get("hotel_preference")

    hotel_cost_check = check_hotel_cost(
        city=requirements["destination"],
        nightly_price=nightly_price,
    )

    # 让规划模型也能看到报价和规则判断结果
    requirements["nightly_price"] = nightly_price
    requirements["hotel_cost_check"] = hotel_cost_check

    await policy_service.load()
    result = await graph.ainvoke({
        "requirements": requirements,
        "search_results": [],
        "policy_results": [],
        "plan": "",
    })
    return {
        "status": "completed",
        "answer": result["plan"],
        "hotel_cost_check": hotel_cost_check,
    }

async def agent_chat_service(
        question:str,
        nightly_price: float | None = None,
        )->dict:
    requirements = await recognize_intent(question)
    intent = requirements.get("intent")

    if intent == "itinerary_planning":
        return await plan_trip(question, requirements, nightly_price=nightly_price)
    if intent == "policy_query":
        answer = await answer_policy(question)
        return {
            "status": "completed",
            "answer": answer,
        }
    if intent == "preference_save":
        hotel = requirements.get("hotel_preference")

        if not hotel:
            return {
                "status": "needs_information",
                "answer": "请说明你偏好的酒店品牌。",
            }
        preferences = load_preference()
        preferences["hotel_preference"] = hotel
        save_preferences(preferences)

        return {
            "status": "completed",
            "answer": f"已保存酒店偏好：{hotel}",
        }
    return {
        "status": "unsupported",
        "answer": "目前支持行程规划、政策查询和酒店偏好保存。",
    }


async def main():
    # question = "我11月5日从广州去上海出差两天，喜欢住如家，帮我安排一下。"
    question=input("请输入差旅需求：").strip()

    if not question:
        print("请输入具体需求。")
        return

    # result = await recognize_intent(question)
    required_fields = {
                "origin": "出发地",
                "destination": "目的地",
                "date": "出发日期",
                "duration": "出行时长",
            }
    
    while True:
        print("正在识别需求……")
        requirements = await recognize_intent(question)
        # if requirements.get("intent") != "itinerary_planning":
        #     print("目前支持差旅行程规划，请描述你的出差需求。")
        #     return
        intent=requirements.get("intent")

        if intent == "preference_save":
            hotel=requirements.get("hotel_preference")
            if not hotel:
                print("请说明你偏好的酒店品牌。")
                return
            preferences=load_preference()
            preferences["hotel_preference"]=hotel
            save_preferences(preferences)
            print(f"已保存酒店偏好：{hotel}")
            return
        if intent=="policy_query":
            answer=await answer_policy(question)
            print("\n政策回答：")
            print(answer)
            return

        if intent != "itinerary_planning":
            print("目前支持差旅行程规划和差旅政策查询。")
            return

        missing = []

        for field,label in required_fields.items():
            if not requirements.get(field):
                missing.append(label)
        if not missing:
            break

        print("\n请补充：" + "、".join(missing))
        supplement=input("补充信息：").strip()

        if not supplement:
            print("未补充信息，本次结束。")
            return
        question = question + "\n补充信息：" + supplement

    preferences=load_preference()

    if requirements.get("hotel_preference"):
        # 本次明确说了酒店偏好，就保存或更新
        preferences["hotel_preference"] = requirements["hotel_preference"]
        save_preferences(preferences)
    else:
        # 本次没说，就使用之前保存的偏好
        requirements["hotel_preference"] = preferences.get("hotel_preference")
        
    print("完整需求：")
    print(json.dumps(requirements, ensure_ascii=False, indent=2))
    print("模型安排的任务：", requirements.get("tasks"))

    # print("\n正在生成行程……")
    # plan = await generate_plan(requirements)
    # origin = requirements["origin"]
    # destination = requirements["destination"]
    # query = f"{origin}到{destination} 交通方式 {destination}市内交通"

    # print("\n正在搜索：", query)
    # search_results=await search_information(query)

    # for item in search_results:
    #     print("资料：", item["title"])
    #     print("来源：", item["url"])

    # print("\n正在生成行程……")
    # plan = await generate_plan(requirements, search_results)

    # print("\n行程草案：")
    # print(plan)
    print("正在加载差旅政策……")
    await policy_service.load()

    result = await graph.ainvoke({
        "requirements": requirements,
        "search_results": [],
        "policy_results": [],
        "plan": "",
    })

    print("\n行程草案：")
    print(result["plan"])


if __name__ == "__main__":
    asyncio.run(main())
