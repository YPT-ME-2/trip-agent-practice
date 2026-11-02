import json
from pathlib import Path

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