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

## 文件职责

- main.py：FastAPI 接口。
- intent_practice.py：意图识别、业务路由、工作流和终端入口。
- llm_service.py：统一调用 Ollama。
- policy_service.py：差旅政策向量检索。
- search_service.py：获取网页搜索结果。
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

## 当前限制

- 搜索结果相关性不稳定，不提供实时票务、房价或预订能力。
- 模型可能编造星期、过度推断政策，草案需要人工核查。
- 政策只检索部分条款，不是完整合规审查。
- 偏好文件为单用户存储。
- HTTP 接口不保存多轮对话，补充信息需随完整需求重新提交。
- 使用受限任务编排，尚未复现原项目完整的 AgentScope 多智能体架构。