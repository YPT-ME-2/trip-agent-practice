import asyncio
import json

from agentscope.agent import AgentBase
from agentscope.message import Msg

from intent_practice import recognize_intent, answer_policy,answer_memory,answer_information

from llm_service import call_model
from skill_loader import load_skill

SCHEDULE_PROMPT = """
你负责将本次差旅需求拆成 Agent 调度计划，只输出 JSON：
{"agent_schedule": [{"type": "意图名称", "question": "该任务的完整问题", "priority": 1}]}

每项必须包含 type、question、priority。priority 使用整数，数值小的先执行，同级任务可并行。
可用角色：
- policy_query：查询公司差旅政策、住宿上限、超标审批。
- memory_query：查询已保存的酒店偏好或历史行程；额外填写 memory_scope，取 preferences、trip_history 或 both。
- information_query：查询天气或搜索公开信息。
- itinerary_planning：根据出行需求及前序结果生成行程草案。

只安排完成本次需求所需的任务，不能凭空增加用户没有提供的出发地、日期、天数等信息。
用户只查询信息时，不添加 itinerary_planning。
用户要求规划时，先安排所需的政策查询；明确引用个人偏好或历史行程时，安排对应的记忆查询。
明确要求天气或公开信息时，安排信息查询；要求不联网时，不安排 information_query。
独立查询通常设为优先级1，依赖查询结果的规划设为优先级2。
查询任务的 question 只包含该项查询；规划任务的 question 保留完整出行需求、限制和偏好。
例如“不用联网，安排2026年11月10日从深圳去上海出差三天”：
{"agent_schedule": [
  {"type": "policy_query", "question": "上海住宿上限和超标审批要求是什么？", "priority": 1},
  {"type": "itinerary_planning", "question": "2026年11月10日从深圳去上海出差三天，不用联网，生成草案。", "priority": 2}
]}
"""

class IntentionAgent(AgentBase):
    async def reply(self,message:Msg)->Msg:
        messages=[
            {
                "role": "system",
                "content": SCHEDULE_PROMPT,
            },
            {
                "role": "user",
                "content": message.content,
            },
        ]
        text=await call_model(messages,json_output=True)

        # result = await recognize_intent(message.content)
        print("\n模型生成的调度计划：")
        print(text)

        return Msg(
            name="IntentAgent",
            role="assistant",
            # content=json.dumps(result, ensure_ascii=False),
            content=text,
        )

class PolicyAgent(AgentBase):
    async def reply(self,message:Msg)->Msg:
        requirements=json.loads(message.content)
        question=requirements["intents"][0]["question"]

        print("政策 Agent 收到的问题：", question)
        answer = await answer_policy(question)

        return Msg(
            name="PolicyAgent",
            role="assistant",
            # content=json.dumps(answer, ensure_ascii=False),
            content=answer,
        )

class MemoryQueryAgent(AgentBase):
    async def reply(self,message:Msg)->Msg:
        requirements=json.loads(message.content)
        item = requirements["intents"][0]
        answer = await answer_memory(
                item["question"],
                memory_scope=item.get("memory_scope", "both"),
            )

        return Msg(
            name="MemoryAgent",
            role="assistant",
            content=answer,
        )

class InformationQueryAgent(AgentBase):
    async def reply(self, message: Msg) -> Msg:
        requirements = json.loads(message.content)
        question = requirements["intents"][0]["question"]

        print("信息 Agent 收到的问题：", question)
        answer = await answer_information(question)

        return Msg(
            name="InformationQueryAgent",
            role="assistant",
            content=answer,
        )


class OrchestrationAgent(AgentBase):
    def __init__(self,agent_registry):
        super().__init__()
        self.agent_registry = agent_registry

    async def reply(self,message:Msg)->Msg:
        requirements=json.loads(message.content)
        schedule=requirements["agent_schedule"]
        previous_results = []

        priorities = sorted({
            item["priority"] for item in schedule
        })

        for priority in priorities:
            print(f"\n开始执行优先级：{priority}")
            jobs = []

            for item in schedule:
                if item["priority"] != priority:
                    continue
                agent=self.agent_registry[item["type"]]

                task_message=Msg(
                    name="OrchestrationAgent",
                    role="assistant",
                    content=json.dumps({
                        "intents":[item],
                        "出行需求": item["question"],
                        "previous_results": previous_results,
                        }, ensure_ascii=False),
                )
                jobs.append(agent.reply(task_message))

            results = await asyncio.gather(*jobs)

            for result in results:
                previous_results.append({
                    "agent_name": result.name,
                    "priority": priority,
                    "content": result.content,
                })

        return Msg(
            name="OrchestrationAgent",
            role="assistant",
            content=json.dumps(previous_results, ensure_ascii=False),
        )

class ItineraryPlanningAgent(AgentBase):
    async def reply(self,message:Msg)->Msg:
        messages = [
            {
                "role": "system",
                "content": load_skill("plan-trip"),
            },
            {
                "role": "user",
                "content": message.content,
            },
        ]

        plan = await call_model(messages)

        return Msg(
            name="ItineraryPlanningAgent",
            role="assistant",
            content=plan,
        )

class LazyAgentRegistry:
    def __init__(self, agent_classes: dict):
        self.agent_classes=agent_classes
        self.instances = {}

    def __getitem__(self, name:str):
        if name not in self.instances:
            agent_class = self.agent_classes[name]
            self.instances[name] = agent_class()
            print("首次创建 Agent：", name)
        return self.instances[name]


async def main():
    intention_agent = IntentionAgent()
    registry = LazyAgentRegistry({
        "policy_query": PolicyAgent,
        "memory_query": MemoryQueryAgent,
        "information_query": InformationQueryAgent,
        "itinerary_planning": ItineraryPlanningAgent,
    })

    orchestrator = OrchestrationAgent(registry)
    user_message = Msg(
        name="user",
        role="user",
        content="上海现在天气如何？另外上海住宿每晚最多报销多少？"
    )

    intention_result =await intention_agent.reply(user_message)
    result=await orchestrator.reply(intention_result)
    results=json.loads(result.content)

    print("\n执行结果：")
    for item in results:
        print(f"\n{item['agent_name']}：")
        print(item["content"])

if __name__ == "__main__":
    asyncio.run(main())
