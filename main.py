from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from intent_practice import answer_policy, plan_trip, agent_chat_service

app=FastAPI(title="差旅助手")

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

@app.post("/api/agent/chat")
async def agent_chat(request: AgentRequest):
    question = request.question.strip()

    if not question:
        raise HTTPException(status_code=422, detail="问题不能为空")

    result = await agent_chat_service(
        question,
        nightly_price=request.nightly_price
    )
    return result
