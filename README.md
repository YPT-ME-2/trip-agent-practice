# 差旅 Agent 练习

参考课程差旅助手流程实现的学习项目，使用本地 Ollama、
LangGraph 和 FastAPI，支持行程草案、政策问答及酒店偏好保存。

## 已实现

- 模型识别行程规划、政策查询、偏好保存三类意图。
- 检查行程必要信息，终端支持追问缺失字段。
- 酒店偏好保存到本地 JSON 文件。
- FAISS 检索演示差旅政策。
- 模型生成受限任务列表，程序执行已注册的任务。
- 搜索与政策检索可并行，完成后生成行程草案。
- 提供统一接口 POST /api/agent/chat。
- 根据城市住宿上限和用户报价，由 Python 判断是否超标，返回独立的 hotel_cost_check 字段。
- 统一接口支持通过 conversation_id 补充缺失信息，并保留上一轮住宿报价。
- 模型请求设置120秒超时，统一接口将 aiohttp 网络错误转换为502、超时转换为504。

## 文件职责

- main.py：FastAPI 接口。
- intent_practice.py：意图识别、业务路由、工作流和终端入口。
- llm_service.py：统一调用 Ollama。
- policy_service.py：差旅政策向量检索。
- search_service.py：获取网页搜索结果。
- compliance_service.py：比较每人每晚住宿报价与城市上限。
- policy_rules.json：住宿限额的统一数据来源，同时用于费用检查和政策检索。
- 差旅政策.txt：虚构的演示政策，不代表真实企业制度。

## 运行

环境：Python 3.11，Ollama。

本地需具备模型：
- qwen3.5:9b
- qwen3-embedding:4b

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

在项目目录启动：

```powershell
python -m uvicorn main:app --reload --port 8002
```

接口文档：http://127.0.0.1:8002/docs

## 住宿报价检查示例

在接口文档中选择 POST /api/agent/chat，点击 Try it out，提交：

```json
{
  "question": "我11月10日从深圳去杭州出差三天，不用联网，根据公司政策给我一份草案。",
  "nightly_price": 450
}
```

POST /api/trip/plan 也支持同样的请求字段。nightly_price 表示每人每晚住宿报价，单位为元，必须是非负有限数值；省略或传 null 表示报价未知。目前仅从该字段读取报价，不从 question 中提取。

示例中杭州上限为400元，hotel_cost_check 返回：

```json
{
  "status": "approval_required",
  "limit": 400,
  "message": "报价超过住宿上限，需提前获得审批，不能默认可以报销。"
}
```

检查状态包括：within_limit（未超过上限）、approval_required（超标需审批）、price_unknown（未提供报价）、unknown_policy（未配置该城市标准）。报价未超标只表示通过金额比较，不代表满足全部报销条件。

## 分两轮补充需求

第一轮向 POST /api/agent/chat 提交，不填写 conversation_id：

```json
{
  "question": "我要去杭州出差三天，不用联网。",
  "nightly_price": 450
}
```

如果返回 status 为 needs_information，将响应中的 conversation_id 原样填入第二轮请求：

```json
{
  "question": "11月10日从深圳出发。",
  "conversation_id": "替换为第一轮响应中的实际ID"
}
```

第二轮会合并先前需求，未重新提供报价时沿用450元。规划完成后清除暂存记录。新行程不带ID提交；ID不存在或已失效时返回404。

## 错误返回

POST /api/agent/chat 中，aiohttp 网络访问失败返回502，超时返回504，响应正文的 detail 提供错误提示。这不覆盖所有客户端异常或程序错误，也尚未覆盖另外两个业务接口。120秒限制针对每次模型请求，不是整个规划流程的总时长。

## 当前限制

- 搜索结果相关性不稳定，不提供实时票务、房价或预订能力。
- 模型可能编造星期、过度推断政策，草案需要人工核查。
- 模型正文可能忽略已提供的报价，或与费用检查结果矛盾；住宿金额比较以独立的 hotel_cost_check 字段为准。该检查不验证实时报价、审批状态或实际可报销金额。
- 政策只检索部分条款，不是完整合规审查。
- 偏好文件为单用户存储。
- 会话仅暂存在单个服务进程的内存字典中，重启或自动重载后失效，不支持多进程共享；尚无过期清理，也不是完整聊天历史。
- 使用受限任务编排，尚未复现原项目完整的 AgentScope 多智能体架构。
