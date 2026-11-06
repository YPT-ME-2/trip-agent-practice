from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from intent_practice import answer_policy, plan_trip, agent_chat_service

from uuid import uuid4
import aiohttp
import asyncio


app=FastAPI(title="差旅助手")
pending_trips:dict[str, dict] = {} #暂存待补全行程和报价
conversation_history:dict[str, list[dict]] = {}#保存这个会话最近说过的话

class PolicyRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)

class TripRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    nightly_price: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
        description="每人每晚的住宿报价，单位为元。"
    )

@app.post("/api/policy/chat")
async def policy_chat(request:PolicyRequest):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="问题不能为空")

    answer = await answer_policy(question)
    return {"answer": answer}

@app.post("/api/trip/plan")
async def trip_plan(request: TripRequest):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="问题不能为空")

    # result = await plan_trip(question)
    result = await plan_trip(
        question,
        nightly_price=request.nightly_price,
    )
    return result

class AgentRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    nightly_price: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
        description="每人每晚的住宿报价，单位为元。"
    )
    conversation_id: str | None = Field(default=None)

@app.post("/api/agent/chat")
async def agent_chat(request: AgentRequest):
    question = request.question.strip()

    if not question:
        raise HTTPException(status_code=422, detail="问题不能为空")

    conversation_id = request.conversation_id
    nightly_price = request.nightly_price

    if conversation_id is None:
        conversation_id = uuid4().hex
        conversation_history[conversation_id] = []
    elif conversation_id not in conversation_history:
        raise HTTPException(status_code=404, detail="会话不存在，请不带 conversation_id 开始新会话")

    history = conversation_history[conversation_id]
    previous=pending_trips.get(conversation_id)
    if previous is not None and nightly_price is None:
        nightly_price = previous["nightly_price"]

    try:
        result = await agent_chat_service(
            question,
            nightly_price=nightly_price,
            conversation_history=history,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="模型接口请求超时，请稍后重试") from exc
    except aiohttp.ClientError as exc:
        raise HTTPException(status_code=502, detail="外部服务访问失败，请检查 Ollama 是否启动，以及联网搜索是否可用。") from exc

    history.extend([
        {"role": "user", "content": question},
        {"role": "assistant", "content": result["answer"]},
    ])

    conversation_history[conversation_id] = history[-20:]

    if result.get("status") == "needs_information":
        pending_trips[conversation_id] = {
            "question": question,
            "nightly_price": nightly_price
        }
    else:
        pending_trips.pop(conversation_id, None)

    return {
        **result,
        "conversation_id": conversation_id
    }

    # result = await agent_chat_service(
    #     question,
    #     nightly_price=request.nightly_price
    # )
    # return result
