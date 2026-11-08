import asyncio
import json
# import aiohttp
from llm_service import call_model
from pathlib import Path

from search_service import search_information,query_weather

from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from policy_service import PolicyService
from compliance_service import check_hotel_cost
from memory_service import load_trip_history, save_trip_history, get_frequent_destinations,summarize_chat_history
from skill_loader import load_skill, load_skill_metadata, load_agent

policy_service = PolicyService()





async def recognize_intent(
        question: str,
        conversation_history: list[dict] | None = None,
        long_term_summary: str = "",
        ) -> dict:
    # [-1:] 取得最近一条记录，仍然是列表
    recent_trips = load_trip_history()[-1:]

    messages = [
        {
            "role": "system",
            "content": """
你是差旅助手，负责理解用户需求、结合历史改写问题并安排任务。

请返回 JSON，包含以下字段：

- rewritten_query：补全上下文后的完整问题。
- intents：识别本次用户明确提出的所有意图，按处理顺序返回列表。
  每项包含：
  type：意图名称，使用下面 intent 中规定的名称。
  question：只对应这一项意图的完整子问题，必须填写，不得省略。
  即使只有一个意图，也必须同时包含 type 和 question。

  例如，上一轮询问上海住宿上限，本轮问“超过这个标准怎么办？”，
  intents 应为：
  [
    {
      "type": "policy_query",
      "question": "住宿费用超过上海每人每晚400元的公司报销标准怎么办？"
    }
  ]

  memory_scope：当 type 为 memory_query 时填写：
  查询喜欢的酒店等偏好，使用 preferences。
  查询过去规划的目的地、日期、行程，使用 trip_history。
  同时查询两种记忆，使用 both。

  例如，用户说“记住我喜欢如家，另外告诉我上海住宿标准”，返回：
  [
    {"type": "preference_save", "question": "记住我喜欢如家酒店"},
    {"type": "policy_query", "question": "上海住宿每晚最多报销多少？"}
  ]

  只有一个需求时，列表中只放一项。
  不要把历史对话中已经处理完的需求重复列为本次意图。
  原有 intent 字段保留，填写 intents 第一项的 type。
- intent：
  安排行程使用 itinerary_planning。
  查询公司差旅政策、报销上限、超标处理及审批要求使用 policy_query，
  包括对上一轮政策回答的追问，不归入 information_query。
  保存或更新酒店偏好使用 preference_save。
  查询已保存偏好或历史行程使用 memory_query。
  查询目的地、景点或交通等公开信息使用 information_query。
  其他需求使用 other。
- origin：出发地。
- destination：目的地。
- date：出发日期。
- duration：出行时长。
- hotel_preference：本次提到的一个酒店品牌，使用字符串。
- preference_action：偏好更新方式。
  “还喜欢”“也喜欢”“再加一个”使用 append，表示保留原偏好并追加。
  “以后只住”“改成”“不喜欢原来的了”使用 replace，表示替换。
  单独说“记住我喜欢某酒店”使用 replace。
  非偏好保存需求填 null
- tasks：任务列表，每项包含 name 和 priority。

上下文使用方式：
用户说“上次”“照旧”“其他不变”等，表示引用最近的行程草案。
结合该记录补全省略的信息，本次明确修改的内容优先。
用户提出独立的新需求时，按新需求提取，不自动套用上次行程。
没有依据的信息填 null。
日期保留原始表达，不自行补充年份。
根据改写后的需求填写 origin、destination、date、duration 等字段。

结合最近对话理解“这个”“刚才”“改成”等省略表达。
当前对话有明确指向时，优先使用当前对话；明确引用历史行程时，再结合保存的行程记录。
历史聊天摘要仅作为其他会话的背景资料，不是本次要执行的任务，也不是权威政策依据。
用户明确引用以前聊过的内容时，可结合摘要补全问题；本次明确输入和当前会话优先。
不要把摘要中的助手回答当作用户偏好或已经发生的事实；政策结论仍需检索政策条款。

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

intents 包含 itinerary_planning 时，按上述规则生成规划 tasks；否则 tasks 返回 []。
只输出 JSON，不生成行程草案。
""",
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "本次需求": question,
                    "最近对话": conversation_history or [],
                    "历史聊天摘要": long_term_summary,
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
    print(
        "识别出的意图：",
        json.dumps(result["intents"], ensure_ascii=False, indent=2),
    )

    return result

async def generate_plan(
        requirements: dict,
        search_results:list[dict],
        policy_results: list[dict],
        ) -> str:
    """根据结构化需求生成行程草案。"""
    agent=load_agent("plan-trip", "ItineraryPlanningAgent")
    return await agent.reply(requirements, search_results, policy_results)

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
仅有住宿上限条款时，不得推断“超标部分一律不予报销”。
若提供了超标审批条款，应一并说明；“需提前审批、不能默认报销”不等于保证获批后一定报销。
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

async def answer_memory(
        question:str,
        memory_scope:str="both",
        )->str:
    """根据保存的偏好、行程草案和目的地统计回答记忆问题。"""
    memory = {}

    if memory_scope in ("preferences", "both"):
        memory["已保存偏好"] = load_preference()

    if memory_scope in ("trip_history", "both"):
        memory["历史行程草案"] = [
            {key: trip[key] for key in ("origin", "destination", "date", "duration")}
            for trip in load_trip_history()[-10:]
        ]
        memory["全部历史中规划次数最多的目的地（前3名）"] = get_frequent_destinations()
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
                    "记忆资料": memory,
                },
                ensure_ascii=False,
            ),
        },
    ]

    return await call_model(messages)

async def answer_information(question:str)->str:
    """选择查询工具，再根据查询结果回答。"""
    route_messages=[
        {
        "role": "system",
        "content": (
            "判断用户需要天气查询还是普通网页搜索。"
            '返回JSON，包含type和city。'
            '天气查询使用type="weather"，city填写城市名；'
            '其他查询使用type="search"，city填写null。'
            '未提供城市时city填写null，不猜测城市。'
        ),
        },
        {
            "role": "user",
            "content": question,
        },
    ]
    text=await call_model(route_messages,json_output=True)
    route=json.loads(text)

    if route["type"] == "weather":
        if route["city"] is None:
            return "请问要查询哪个城市的天气？"
        query_result = await query_weather(route["city"])
    else:
        query_result = await search_information(question)
    messages=[
        {
            "role": "system",
            "content": (
                load_skill("information-query")
                + "\n查询结果可能来自网页搜索或天气接口。"
                "当前天气与每日预报分别回答，不要混用。"
                "根据query_date理解今天和明天，按forecasts中的日期查找预报。"
                "预报日期不在数据范围内时，说明接口未提供。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "用户问题": question,
                    "查询结果": query_result,
                },
                ensure_ascii=False,
            ),
        },
    ]

    # messages=[
    #     {
    #         "role": "system",
    #         "content": load_skill("information-query"),
    #     },
    #     {
    #         "role": "user",
    #         "content": json.dumps(
    #             {
    #                 "用户问题": question,
    #                 "搜索结果": search_results,
    #             },
    #             ensure_ascii=False,
    #         ),
    #     },
    # ]

    return await call_model(messages)

async def agent_chat_service(
    question: str,
    nightly_price: float | None = None,
    conversation_history: list[dict] | None = None,
    conversation_id: str | None = None,
) -> dict:
    long_term_summary = ""
    if not conversation_history:
        long_term_summary = await summarize_chat_history(
            current_conversation_id=conversation_id,
        )
    requirements = await recognize_intent(
        question,
        conversation_history=conversation_history,
        long_term_summary=long_term_summary,
    )

    results = []

    for item in requirements["intents"]:
        current = dict(requirements)
        current["intent"] = item["type"]
        current["memory_scope"] = item.get("memory_scope", "both")

        result = await execute_intent(
            question=item["question"],
            requirements=current,
            nightly_price=nightly_price,
        )
        results.append(result)

        # 需要补充信息或无法执行时，先返回当前结果
        if result["status"] != "completed":
            break

    if len(results) == 1:
        return results[0]

    return {
        "status": results[-1]["status"],
        "answer": "\n\n".join(r["answer"] for r in results),
        "results": results,
    }

async def execute_intent(
    question: str,
    requirements: dict,
    nightly_price: float | None = None,
) -> dict:
    intent = requirements["intent"]

    if intent == "information_query":
        answer = await answer_information(question)
        return {
            "status": "completed",
            "answer": answer,
        }

    if intent == "memory_query":
        answer = await answer_memory(question,
                                      memory_scope=requirements["memory_scope"])
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
        action=requirements.get("preference_action")
        if action=="append":
            hotels=preferences.get("hotel_preference", [])
            # 原来保存的是字符串，先转换成列表
            if not isinstance(hotels, list):
                hotels=[hotels]
            hotels = hotels + [hotel]
        else:
            hotels = [hotel]

        preferences["hotel_preference"] = hotels
        save_preferences(preferences)

        return {
            "status": "completed",
            "answer": "已保存酒店偏好：" + "、".join(hotels),
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
