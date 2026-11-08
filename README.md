# 差旅 Agent 练习

参考课程差旅助手流程实现的学习项目，使用本地 Ollama、
LangGraph 和 FastAPI，支持行程草案、政策问答及酒店偏好保存。

学习总览：[项目总览.md](项目总览.md) 包含统一入口总图、真实函数索引、课程实现对照，以及下一阶段的学习建议。

## 已实现

- 模型识别行程规划、政策查询、偏好保存、记忆查询和公开信息查询五类意图。
- 单次请求可识别多个意图，按列表顺序逐项执行，再合并回答；已演示“保存偏好 + 政策查询”和“保存偏好 + 行程规划”。
- 支持独立查询目的地、景点和交通等公开信息，复用搜索服务，无需填写完整行程字段。
- 检查行程必要信息，终端支持追问缺失字段。
- 酒店偏好保存到本地 JSON 文件。
- 偏好更新区分 append（追加）和 replace（替换）；当前追加不会自动去重。
- FAISS 检索演示差旅政策。
- 模型生成受限任务列表，程序执行已注册的任务。
- 搜索与政策检索可并行，完成后生成行程草案。
- 按模型生成的任务优先级分批执行：同级并行，前一批结果传给后一批。
- 保存生成过的行程草案，支持查询酒店偏好和历史规划记录。
- 意图识别时提供最近一条行程草案，支持理解“上次”“其他不变”等需求，并输出改写后的问题和结构化字段。
- 扫描 skills/*/SKILL.md 的名称和简介，意图识别时提供技能简介，执行规划或记忆查询时加载对应的详细指令。
- 规划 Agent 在首次使用时按文件路径加载并创建实例，后续请求复用该进程内的实例。
- 提供统一接口 POST /api/agent/chat。
- 根据城市住宿上限和用户报价，由 Python 判断是否超标，返回独立的 hotel_cost_check 字段。
- 统一接口支持通过 conversation_id 补充缺失信息，并保留上一轮住宿报价。
- 同一 conversation_id 保留最近20条用户和助手消息（约10轮对话），意图识别时结合最近对话补全问题，完成一次回答后仍可继续追问。
- 模型请求设置120秒超时，统一接口将 aiohttp 网络错误转换为502、超时转换为504。
- 公开信息问答可选择网页搜索或 wttr.in 天气查询，支持当前天气和接口提供日期范围内的每日最低、最高气温。
- 原生 tool_calls 支持天气查询、网页搜索和住宿限额检查，可在一次请求内根据前序工具结果继续调用工具；已接入 POST /api/tool/chat。

## 文件职责

- main.py：FastAPI 接口。
- intent_practice.py：recognize_intent() 识别需求，agent_chat_service() 遍历多意图清单，execute_intent() 执行单项业务；同时包含行程工作流和终端入口。
- llm_service.py：统一调用 Ollama。
- policy_service.py：差旅政策向量检索。
- search_service.py：获取网页搜索结果，以及当前天气和每日气温预报。
- compliance_service.py：比较每人每晚住宿报价与城市上限。
- policy_rules.json：住宿限额的统一数据来源，同时用于费用检查和政策检索。
- memory_service.py：保存和读取行程及聊天记录，统计目的地规划次数；summarize_chat_history() 已提供跨会话背景，summarize_trip_history() 仍是独立练习。
- skill_loader.py：发现 Skill 元数据，读取详细指令，按指定类名加载并缓存 Agent 实例。
- skills/plan-trip/SKILL.md：行程规划指令。
- skills/plan-trip/script/agent.py：规划 Agent，接收需求与检索资料，调用模型生成草案。
- skills/memory-query/SKILL.md：偏好与历史行程查询指令。
- skills/information-query/SKILL.md：独立公开信息查询指令。
- tool_practice.py：原生 tool_calls 多轮工具调用，支持天气查询、网页搜索和住宿限额检查；run_tool_agent() 已接入 /api/tool/chat，也可直接运行进行终端交互。
- agentsccope_practicce.py：独立的 AgentScope 练习，通过 Msg 传递消息，并行查询记忆与政策后生成草案；尚未替换 FastAPI 的业务调度。
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

POST /api/trip/plan 也支持同样的请求字段。nightly_price 表示每人每晚住宿报价，单位为元，必须是非负有限数值；省略或传 null 表示报价未知。这两个行程规划入口仅从该字段读取报价，不从 question 中提取；独立的 /api/tool/chat 则由模型从问题中提取工具参数。

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

第二轮会结合先前对话理解补充信息，待补全行程未重新提供报价时沿用450元。规划完成后只清除待补全记录，对话消息仍保留，可继续使用同一个ID追问。新会话不带ID提交；已有ID先查内存，缺失时从聊天文件恢复最近20条消息，文件也没有该ID才返回404。pending_trips 和暂存报价仍仅在内存中，重启不会恢复。

例如第一轮询问“去上海出差，住宿每晚最多报销多少？”，第二轮携带返回的 conversation_id 询问“超过这个标准怎么办？”，意图识别会接收上一轮问题和回答，用于理解“这个标准”。

## 记忆查询

向 POST /api/agent/chat 提交 {"question": "我之前说喜欢住什么酒店？"} 可查询已保存的酒店偏好；提交 {"question": "我之前规划过哪些目的地？"} 可查询已保存的历史行程草案。

历史行程从添加保存功能后开始积累，仅代表系统生成过草案，不代表用户实际出行。偏好和历史草案保存在本地文件中，服务重启后仍可读取；preferences.json 和 trip_history.json 均不提交到代码仓库。

提交 {"question": "我之前规划哪个城市最多？分别有多少条规划记录？"}，记忆查询会同时读取最近10条草案和全部历史记录中规划次数最多的前3个目的地。次数由 get_frequent_destinations() 计算，模型负责组织回答；次数不代表实际出行频率。

summarize_trip_history() 是独立的历史摘要练习，目前未接入接口。AgentScope 练习依赖 agentscope==1.0.16 和 mcp==1.30.0，已记录在 requirements.txt。

## 聊天保存、会话恢复与跨会话摘要

POST /api/agent/chat 返回前调用 save_chat_turn()，将每轮用户问题、助手回答、conversation_id 和 ISO 格式时间戳写入 chat_history.json。该文件已加入 .gitignore，不提交聊天内容。

- 旧会话ID：load_chat_history() 读取文件，按ID筛选，恢复最近20条 role/content 消息；已在内存中的会话直接使用内存对话。
- 新会话且没有当前对话：summarize_chat_history() 排除当前ID，从其他会话取最近20条消息，要求模型总结为不超过200字的摘要，通过 long_term_summary 提供给 recognize_intent()。
- 已有当前对话：本次不重新生成摘要；摘要本身不单独保存，也不插入后续对话，后续追问主要使用当前会话消息。

已演示：重启后携带旧ID追问“超过这个标准怎么办？”，恢复上海住宿问答；另起新ID询问“我以前问过的那个城市，住宿超过报销标准怎么办？”，回答补全上海与400元背景并检索审批条款。

摘要只是历史背景，不是政策依据，可能保留旧回答的错误。政策检索从 k=2 调整为 k=3，在已测试问题中补回审批条款，不保证所有问题都检索完整。存在旧聊天的新会话会多一次摘要模型调用，摘要长度由提示词要求。

此功能仅接入 /api/agent/chat；其他三个业务接口不经过上述保存与恢复流程。聊天文件仍是单用户共享文件，不是用户隔离机制。

## 独立信息查询

向 POST /api/agent/chat 提交 {"question": "杭州东站到西湖怎么走？"}，识别为 information_query 后，由 answer_information() 搜索资料并调用模型回答。该分支不要求出发日期、出行时长等规划字段，也不生成行程草案。

当前搜索可能只返回城市简介等不相关资料，此时回答可能说明资料不足；接通查询流程不代表能够提供准确的实时路线或导航。

天气问题如 {"question": "杭州明天最低和最高气温是多少？"}，由 answer_information() 调用模型返回 type 和 city，再选择 query_weather()。天气工具从 wttr.in 读取当前天气及每日气温预报，并提供 query_date 帮助理解今天和明天；不支持查询返回日期范围以外的预报。

## 原生工具调用接口

POST /api/tool/chat 接收问题，调用 tool_practice.py 的 run_tool_agent(question)。模型通过原生 tool_calls 选择 query_weather、search_information 或 check_hotel_cost，Python 执行工具并把结果作为 tool 消息回传；下一轮仍可请求工具，没有 tool_calls 时返回最终答案。

```json
{
  "question": "先查杭州明天最低气温。如果低于10℃，再检查每人每晚450元的酒店是否超标；否则只回答天气。"
}
```

返回结构为 {"status": "completed", "answer": "模型最终回答"}，调用过程显示在服务终端。已在一次实际请求中观察到：先查天气，再根据明天最低8℃调用住宿检查，最后说明450元超过400元上限、需提前审批。

天气和搜索可以组合请求，例如 {"question": "杭州明天气温如何？另外搜索西湖主要景点并附来源。"}。网页搜索复用现有 Bing RSS 服务，返回结果可能不够相关。

天气工具中的 temperature_c、description、humidity 是当前观测；forecasts 仅包含对应日期的最低和最高气温。已验证模型能回答明天气温，并说明未提供明天湿度。

该接口不保存跨请求会话，也不返回独立的 hotel_cost_check 字段。status 为 completed 表示函数返回了模型答案，不代表程序独立验证了用户的所有任务均已完成。日期理解、条件判断和工具选择仍可能出错；已观察到模型漏调工具、把今天当明天及把当前湿度当预报的情况，明确提示后对应测试通过。

/api/agent/chat 继续使用原有意图识别、记忆和业务调度；其信息查询分支使用模型返回的 type/city 选择工具，没有改成此原生工具循环。

## 多意图请求示例

向 POST /api/agent/chat 提交：

```json
{
  "question": "记住，以后只住汉庭，另外告诉我上海住宿每晚最多报销多少。"
}
```

识别结果包括 preference_save 和 policy_query。程序依次执行，answer 合并两项回答，results 保留各项结果。只有一项意图时沿用原来的单项响应结构；某项返回非 completed 状态时停止继续执行。

intents 表示用户要办理的业务事项；tasks 表示行程规划内部按优先级执行的检索和生成步骤。多意图清单当前顺序执行，行程内部同优先级的 tasks 才并行执行。

## 错误返回

POST /api/agent/chat 中，aiohttp 网络访问失败返回502，超时返回504，响应正文的 detail 提供错误提示。这不覆盖所有客户端异常或程序错误，也尚未覆盖其他业务接口（包括 /api/tool/chat）。120秒限制针对每次模型请求，不是整个规划或多轮工具调用流程的总时长。

## 当前限制

- 搜索结果相关性不稳定，不提供实时票务、房价或预订能力。
- 模型可能编造星期、过度推断政策或错误标注来源，草案需要人工核查。
- 模型正文可能忽略已提供的报价，或与费用检查结果矛盾；住宿金额比较以独立的 hotel_cost_check 字段为准。该检查不验证实时报价、审批状态或实际可报销金额。
- 政策只检索部分条款，不是完整合规审查。
- 偏好文件为单用户存储。
- 内存中每个会话保留最近20条消息；重启后已有聊天可从文件按ID恢复，待补全行程及暂存报价不恢复。当前JSON读写没有并发写入协调，也没有会话过期清理。
- 使用受限任务编排，尚未复现原项目完整的 AgentScope 多智能体架构。
- 仅规划 Agent 接入了代码懒加载，技能名与类名仍显式指定，尚未实现课程完整的 Agent 注册表和类自动发现。
- 短期对话按会话ID区分，但长期偏好和行程文件仍是单用户共享；日期、上下文补全和其他生成内容仍可能出错。
- 工具循环当前没有轮数上限；没有 tool_calls 就结束，不能保证模型每次都完成所有条件任务。天气查询不代表实时票务、房价或预订能力。
