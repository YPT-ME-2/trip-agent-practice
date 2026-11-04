import json

from llm_service import call_model
from skill_loader import load_skill

class ItineraryPlanningAgent:
    async def reply(
        self,
        requirements: dict,
        search_results: list[dict],
        policy_results: list[dict],
    ) -> str:
        messages = [
            {
                "role": "system",
                "content": load_skill("plan-trip"),
            },
            {
                "role": "user",
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
        return await call_model(messages)