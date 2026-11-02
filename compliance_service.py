import json
from pathlib import Path

POLICY_FILE = Path(__file__).parent / "policy_rules.json"

def check_hotel_cost(
        city:str,
        nightly_price:float | None,
) -> dict:
    """nightly_price 表示每人每晚的住宿报价，单位为元。"""

    text = POLICY_FILE.read_text(encoding="utf-8-sig")
    rules = json.loads(text)

    limit = rules["hotel_limits"].get(city)

    if limit is None:
        return {
            "status": "unknown_policy",
            "message": f"未配置{city}的住宿标准，无法判断。",
        }

    if nightly_price is None:
        return {
            "status": "price_unknown",
            "limit": limit,
            "message": f"住宿上限为每人每晚{limit}元；未提供报价，无法判断。",
        }

    if nightly_price < 0:
        raise ValueError("住宿报价不能为负数")

    if nightly_price <= limit:
        return {
            "status": "within_limit",
            "limit": limit,
            "message": "报价未超过住宿上限，不代表其他报销条件均已满足。",
        }
    return {
        "status": "approval_required",
        "limit": limit,
        "message": "报价超过住宿上限，需提前获得审批，不能默认可以报销。",
    }


if __name__ == "__main__":
    result = check_hotel_cost("杭州", 450)
    print(json.dumps(result, ensure_ascii=False, indent=2))