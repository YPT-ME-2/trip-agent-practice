from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from intent_practice import answer_policy, plan_trip, agent_answer

app=FastAPI(title="差旅助手")

class PolicyRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)

class TripRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)

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

    result = await plan_trip(question)
    return result

class AgentRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)

@app.post("/api/agent/answer")
async def agent_chat(request: AgentRequest):
    question = request.question.strip()

    if not question:
        raise HTTPException(status_code=422, detail="问题不能为空")

    result = await agent_answer(question)
    return result