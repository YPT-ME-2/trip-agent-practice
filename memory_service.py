import json
from pathlib import Path

import asyncio

from llm_service import call_model

HISTORY_FILE = Path(__file__).parent / "trip_history.json"

def load_trip_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []

    return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))

def save_trip_history(requirements: dict, plan: str) -> None:
    history = load_trip_history()

    history.append({
        "origin": requirements["origin"],
        "destination": requirements["destination"],
        "date": requirements["date"],
        "duration": requirements["duration"],
        "plan": plan,
    })

    HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

async def summarize_trip_history() -> str:
    history = load_trip_history()[-10:]
    # 只提取行程信息，不把整篇草案送去总结
    records = []
    for trip in history:
        records.append({
            "出发地": trip["origin"],
            "目的地": trip["destination"],
            "出发日期": trip["date"],
            "天数": trip["duration"],
        })

    messages = [
        {
            "role": "system",
            "content": (
                "请将提供的历史行程草案记录整理成不超过200字的摘要。"
                "保留主要出发地、目的地、日期和天数。"
                "这些记录表示曾经生成过规划，不代表用户实际出行。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(records, ensure_ascii=False),
        },
    ]

    summary=await call_model(messages)
    return summary

def get_frequent_destinations(top_n: int = 3) -> list[tuple]:
    frequency = {}
    for trip in load_trip_history():
        city = trip["destination"]
        frequency[city] = frequency.get(city, 0) + 1

    ranked = sorted(
        frequency.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    return ranked[:top_n]

if __name__ == "__main__":
    results = get_frequent_destinations(3)

    for city, count in results:
        print(f"{city}：{count} 条规划记录")