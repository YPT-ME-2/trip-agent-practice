import asyncio
import json

from agentscope.agent import AgentBase
from agentscope.message import Msg

from intent_practice import recognize_intent, answer_policy,answer_memory,answer_information

from llm_service import call_model
from skill_loader import load_skill

class IntentionAgent(AgentBase):
    async def reply(self,message:Msg)->Msg:
        result = await recognize_intent(message.content)

        return Msg(
            name="IntentAgent",
            role="assistant",
            content=json.dumps(result, ensure_ascii=False),
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
        # answers=[]
        previous_results = []
        jobs=[]

        for item in requirements["intents"]:
            agent = self.agent_registry[item["type"]]

            task_message=Msg(
                name="OrchestrationAgent",
                role="assistant",
                content=json.dumps({"intents":[item]}, ensure_ascii=False),
            )
            jobs.append(agent.reply(task_message))

        results = await asyncio.gather(*jobs)

        for result in results:
            # answers.append(result.content)
            previous_results.append({
                "agent_name": result.name,
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
    })

    orchestrator = OrchestrationAgent(registry)
    user_message = Msg(
        name="user",
        role="user",
        content="上海现在天气如何？另外上海住宿每晚最多报销多少？"
    )

    intention_result =await intention_agent.reply(user_message)
    result = await orchestrator.reply(intention_result)
    print(
    "是否复用同一个政策Agent：",
    registry["policy_query"] is registry["policy_query"],
)

    print("\n前序查询结果：")
    print(result.content)

    planning_agent = ItineraryPlanningAgent()

    planning_message = Msg(
        name="OrchestrationAgent",
        role="assistant",
        content=json.dumps(
            {
                "出行需求": "2026年11月10日从深圳去上海出差三天，不用联网。",
                # "前序Agent查询结果": result.content,
                "previous_results": json.loads(result.content),
                "搜索资料": [],
            },
            ensure_ascii=False,
        ),
    )

    plan_result = await planning_agent.reply(planning_message)

    print("\n最终行程：")
    print(plan_result.content)

if __name__ == "__main__":
    asyncio.run(main())
