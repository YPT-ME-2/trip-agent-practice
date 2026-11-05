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
from memory_service import load_trip_history, save_trip_history
from skill_loader import load_skill, load_skill_metadata, load_agent

policy_service = PolicyService()

# async def recognize_intent(question:str)->dict:
#     """把用户的话整理成出行需求。"""
#     messages = [
#         {
#             "role": "system",
#             "content": """
# 你是差旅助手，负责提取用户需求。

# 请返回 JSON，包含以下字段：
# - intent：行程规划用 itinerary_planning，其他需求用 other
# 询问差旅报销标准、交通标准或审批规定用 policy_query;
# 要求记住或更新酒店品牌偏好，使用 preference_save。
# 询问之前保存的酒店偏好或历史行程草案，使用 memory_query。
# 其他需求用 other。
# - origin：出发地
# - destination：目的地
# - date：出发日期
# - duration：出行时长
# - hotel_preference：酒店偏好
# - tasks：任务列表，每个任务包含 name 和 priority。
#   行程规划默认返回：
#   [
#     {"name": "search", "priority": 1},
#     {"name": "policy", "priority": 1},
#     {"name": "plan", "priority": 2}
#   ]
#   如果用户明确要求不联网，返回：
#   [
#     {"name": "policy", "priority": 1},
#     {"name": "plan", "priority": 2}
#   ]
#   非行程规划需求返回 []。
#   priority 数字越小越先执行，同一 priority 的任务并行执行。

# 用户没提供的信息填 null，不要猜测。
# 只提取信息，不生成行程。
# 用户没提供的信息填 null，不要猜测。
# 日期保留用户原始表达，例如“11月5日”，未提供年份时不要补充年份。
# 只提取信息，不生成行程。
# """,
#         },
#         {
#             "role": "user",
#             "content": question,
#         },
#     ]

#     # async with aiohttp.ClientSession() as session:
#     #     async with session.post(
#     #         "http://127.0.0.1:11434/api/chat",
#     #         json={
#     #             "model": "qwen3.5:9b",
#     #             "messages": messages,
#     #             "stream": False,
#     #             "think": False,
#     #             "format": "json",
#     #         },
#     #     ) as response:
#     #         # response.raise_for_status()
#     #         # data = await response.json()
#     #         if response.status == 401:
#     #             raise RuntimeError("搜索认证失败，请检查 SERPAPI_KEY 是否为有效的 SerpAPI 密钥")

#     #         if response.status >= 400:
#     #             raise RuntimeError(f"搜索请求失败，HTTP 状态码：{response.status}")

#     #         data = await response.json()

#     # return json.loads(data["message"]["content"])

#     text = await call_model(messages, json_output=True)

#     # messages[0]["content"] += (
#     #     "\n\n可用技能简介：\n"
#     #     + json.dumps(load_skill_metadata(), ensure_ascii=False)
#     # )
#     # return json.loads(text)

#     messages[0]["content"] += (
#         "\n\n可用技能简介：\n"
#         + json.dumps(load_skill_metadata(), ensure_ascii=False)
#     )

#     text = await call_model(messages, json_output=True)
#     return json.loads(text)


async def recognize_intent(question: str) -> dict:
    # [-1:] 取得最近一条记录，仍然是列表
    recent_trips = load_trip_history()[-1:]

    messages = [
        {
            "role": "system",
            "content": """
你是差旅助手，负责理解用户需求、结合历史改写问题并安排任务。

请返回 JSON，包含以下字段：

- rewritten_query：补全上下文后的完整问题。
- intent：
  安排行程使用 itinerary_planning。
  查询差旅政策使用 policy_query。
  保存或更新酒店偏好使用 preference_save。
  查询已保存偏好或历史行程使用 memory_query。
  查询目的地、景点或交通等公开信息使用 information_query。
  其他需求使用 other。
- origin：出发地。
- destination：目的地。
- date：出发日期。
- duration：出行时长。
- hotel_preference：酒店偏好。
- tasks：任务列表，每项包含 name 和 priority。

上下文使用方式：
用户说“上次”“照旧”“其他不变”等，表示引用最近的行程草案。
结合该记录补全省略的信息，本次明确修改的内容优先。
用户提出独立的新需求时，按新需求提取，不自动套用上次行程。
没有依据的信息填 null。
日期保留原始表达，不自行补充年份。
根据改写后的需求填写 origin、destination、date、duration 等字段。

任务安排：
行程规划默认返回：
[
  {"name": "search", "priority": 1},
  {"name": "policy", "priority": 1},
  {"name": "plan", "priority": 2}
]

明确要求不联网时返回：
[
  {"name": "policy", "priority": 1},
  {"name": "plan", "priority": 2}
]

非行程规划需求返回 []。
只输出 JSON，不生成行程草案。
""",
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "本次需求": question,
                    "最近的行程草案": recent_trips,
                    "可用技能简介": load_skill_metadata(),
                },
                ensure_ascii=False,
            ),
        },
    ]

    text = await call_model(messages, json_output=True)
    result = json.loads(text)

    print("改写后的需求：", result["rewritten_query"])

    return result

async def generate_plan(
        requirements: dict,
        search_results:list[dict],
        policy_results: list[dict],
        ) -> str:
    """根据结构化需求生成行程草案。"""
    agent=load_agent("plan-trip", "ItineraryPlanningAgent")
    return await agent.reply(requirements, search_results, policy_results)
    # messages = [
    #     {
    #         "role": "system",
    #         "content": load_skill("plan-trip"),
    #     },
    #     {
    #         "role": "user",
    #         # "content": json.dumps(requirements, ensure_ascii=False),
    #         "content": json.dumps(
    #             {
    #                 "出行需求": requirements,
    #                 "搜索资料": search_results,
    #                 "差旅政策": policy_results,
    #             },
    #             ensure_ascii=False,
    #         ),
    #     },
    # ]

    # # async with aiohttp.ClientSession() as session:
    # #     async with session.post(
    # #         "http://127.0.0.1:11434/api/chat",
    # #         json={
    # #             "model": "qwen3.5:9b",
    # #             "messages": messages,
    # #             "stream": False,
    # #             "think": False,
    # #         },
    # #     ) as response:
    # #         response.raise_for_status()
    # #         data = await response.json()

    # # return data["message"]["content"]
    # text = await call_model(messages,json_output=False)
    # return text

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
        "plan": plan_node,
    }
    tasks = state["requirements"]["tasks"]

    priorities=sorted({task["priority"] for task in tasks})
    current_state = dict(state)
    updates = {}

    for priority in priorities:
        print(f"执行优先级 {priority} 的任务")
        jobs = []
        for task in tasks:
            if task["priority"] == priority:
                function = handlers[task["name"]]
                jobs.append(function(current_state))
        outputs = await asyncio.gather(*jobs)

        for output in outputs:
            current_state.update(output)
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

# builder = StateGraph(TravelState)

# builder.add_node("execute_tasks", execute_tasks_node)
# builder.add_node("plan", plan_node)

# builder.add_edge(START, "execute_tasks")
# builder.add_edge("execute_tasks", "plan")
# builder.add_edge("plan", END)

builder = StateGraph(TravelState)

builder.add_node("execute_tasks", execute_tasks_node)

builder.add_edge(START, "execute_tasks")
builder.add_edge("execute_tasks", END)

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

    save_trip_history(requirements, result["plan"])
    return {
        "status": "completed",
        "answer": result["plan"],
        "hotel_cost_check": hotel_cost_check,
    }

async def answer_memory(question:str)->str:
    """回答用户关于之前保存的酒店偏好的问题。"""
    preferences=load_preference()
    trip_history = load_trip_history()
    messages=[
        {
            "role": "system",
            "content": load_skill("memory-query"),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "用户问题": question,
                    "已保存偏好": preferences,
                    "历史行程草案": trip_history[-10:],
                },
                ensure_ascii=False,
            ),
        },
    ]

    return await call_model(messages)

async def answer_information(question:str)->str:
    """回答用户关于目的地、景点或交通等公开信息的查询。"""
    search_results = await search_information(question)

    messages=[
        {
            "role": "system",
            "content": load_skill("information-query"),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "用户问题": question,
                    "搜索结果": search_results,
                },
                ensure_ascii=False,
            ),
        },
    ]

    return await call_model(messages)


async def agent_chat_service(
        question:str,
        nightly_price: float | None = None,
        )->dict:
    requirements = await recognize_intent(question)
    intent = requirements.get("intent")

    if intent == "information_query":
        answer = await answer_information(question)
        return {
            "status": "completed",
            "answer": answer,
        }

    if intent == "memory_query":
        answer = await answer_memory(question)
        return {
            "status": "completed",
            "answer": answer,
        }

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
        "answer": "目前支持行程规划、政策查询、信息查询及酒店偏好保存和记忆查询。",
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
