# LIA — 完整技术指南

> 新一代多智能体 AI 助手的架构、模式与工程决策。
>
> 面向架构师、工程师和技术专家的技术展示文档。

**版本**：2.1
**日期**：2026-03-25
**应用**：LIA v1.14.0
**许可证**：AGPL-3.0（开源）

---

## 目录

1. [背景与基础选型](#1-背景与基础选型)
2. [技术栈](#2-技术栈)
3. [后端架构：Domain-Driven Design](#3-后端架构domain-driven-design)
4. [LangGraph：多智能体编排](#4-langgraph多智能体编排)
5. [会话执行管道](#5-会话执行管道)
6. [规划系统（ExecutionPlan DSL）](#6-规划系统executionplan-dsl)
7. [Smart Services：智能优化](#7-smart-services智能优化)
8. [语义路由与语义嵌入](#8-语义路由与语义嵌入)
9. [Human-in-the-Loop：6层架构](#9-human-in-the-loop6层架构)
10. [状态管理与消息窗口化](#10-状态管理与消息窗口化)
11. [记忆系统与心理画像](#11-记忆系统与心理画像)
12. [多提供商 LLM 基础设施](#12-多提供商-llm-基础设施)
13. [连接器：多供应商抽象](#13-连接器多供应商抽象)
14. [MCP：Model Context Protocol](#14-mcpmodel-context-protocol)
15. [语音系统（STT/TTS）](#15-语音系统stttts)
16. [主动性：Heartbeat 与计划任务](#16-主动性heartbeat-与计划任务)
17. [RAG Spaces 与混合搜索](#17-rag-spaces-与混合搜索)
18. [Browser Control 与 Web Fetch](#18-browser-control-与-web-fetch)
19. [安全性：纵深防御](#19-安全性纵深防御)
20. [可观测性与监控](#20-可观测性与监控)
21. [性能：优化与指标](#21-性能优化与指标)
22. [CI/CD 与质量](#22-cicd-与质量)
23. [横切工程模式](#23-横切工程模式)
24. [架构决策记录（ADR）](#24-架构决策记录adr)
25. [演进潜力与可扩展性](#25-演进潜力与可扩展性)

---

## 1. 背景与基础选型

### 1.1. 为什么做出这些选择？

LIA 的每一项技术决策都源于具体的约束条件。该项目旨在打造一个**可在普通硬件上自托管**（Raspberry Pi 5、ARM64）的多智能体 AI 助手，具备完全透明性、数据主权和多 LLM 供应商支持。这些约束决定了整个技术栈。

| 约束 | 架构影响 |
|------|---------|
| ARM64 自托管 | Docker 多架构、语义嵌入（多语言）、Playwright chromium 跨平台 |
| 数据主权 | 本地 PostgreSQL（非 SaaS 数据库）、Fernet 静态加密、本地 Redis 会话 |
| 多 LLM 供应商 | Factory 模式搭配 7 个适配器，按节点配置，不与特定供应商强耦合 |
| 完全透明 | 350+ Prometheus 指标、内嵌调试面板、逐 token 追踪 |
| 生产可靠性 | 59 篇 ADR、2,300+ 测试、原生可观测性、6 层 HITL |
| 成本可控 | Smart Services（节省 89% token）、语义嵌入、prompt 缓存、目录过滤 |

### 1.2. 架构原则

| 原则 | 实现方式 |
|------|---------|
| **Domain-Driven Design** | `src/domains/` 中的限界上下文、显式聚合、Router/Service/Repository/Model 分层 |
| **六边形架构** | 端口（Python 协议）和适配器（Google/Microsoft/Apple 具体客户端） |
| **事件驱动** | SSE 流式传输、ContextVar 传播、fire-and-forget 后台任务 |
| **纵深防御** | 使用限制 5 层防御、6 级 HITL、3 层反幻觉 |
| **功能开关** | 每个子系统可独立启用/禁用（`{FEATURE}_ENABLED`） |
| **配置即代码** | Pydantic BaseSettings 通过 MRO 组合，优先级链 APPLICATION > .ENV > CONSTANT |

### 1.3. 代码库指标

| 指标 | 数值 |
|------|------|
| 测试 | 2,300+（单元、集成、智能体、基准） |
| 可复用 Fixtures | 170+ |
| 文档 | 190+ |
| ADR（架构决策记录） | 59 |
| Prometheus 指标 | 350+ 定义 |
| Grafana 仪表板 | 18 |
| 支持语言（i18n） | 6（fr、en、de、es、it、zh） |

---

## 2. 技术栈

### 2.1. 后端

| 技术 | 版本 | 角色 | 选型原因 |
|------|------|------|---------|
| Python | 3.12+ | 运行时 | 最丰富的 ML/AI 生态系统、原生异步、完整类型标注 |
| FastAPI | 0.135.1 | REST API + SSE | Pydantic 自动验证、OpenAPI 文档、async-first、高性能 |
| LangGraph | 1.1.2 | 多智能体编排 | 唯一原生支持状态持久化 + 循环 + 中断（HITL）的框架 |
| LangChain Core | 1.2.19 | LLM/工具抽象 | `@tool` 装饰器、消息格式、标准化回调 |
| SQLAlchemy | 2.0.48 | 异步 ORM | `Mapped[Type]` + `mapped_column()`、异步会话、`selectinload()` |
| PostgreSQL | 16 + pgvector | 数据库 + 向量搜索 | 原生 LangGraph 检查点、HNSW 语义搜索、成熟度 |
| Redis | 7.3.0 | 缓存、会话、限流 | O(1) 操作、原子滑动窗口（Lua）、SETNX 领导者选举 |
| Pydantic | 2.12.5 | 验证 + 序列化 | `ConfigDict`、`field_validator`、通过 MRO 组合设置 |
| structlog | latest | 结构化日志 | JSON 输出、自动 PII 过滤、snake_case 事件 |
| openai | 1.0+ | 语义嵌入 | OpenAI 多语言嵌入，优化语义路由 |
| Playwright | latest | 浏览器自动化 | Chromium 无头模式、CDP 无障碍树、跨平台 |
| APScheduler | 3.x | 后台任务 | Cron/间隔触发器、兼容 Redis 领导者选举 |

### 2.2. 前端

| 技术 | 版本 | 角色 |
|------|------|------|
| Next.js | 16.1.7 | App Router、SSR、ISR |
| React | 19.2.4 | UI（含 Server Components） |
| TypeScript | 5.9.3 | 严格类型 |
| TailwindCSS | 4.2.1 | 实用优先 CSS |
| TanStack Query | 5.90 | 服务端状态管理、缓存、变更 |
| Radix UI | v2 | 无障碍 UI 基元 |
| react-i18next | 16.5 | i18n（6 种语言），基于命名空间 |
| Zod | 3.x | 调试模式的运行时验证 |

### 2.3. 支持的 LLM 提供商

| 提供商 | 模型 | 特性 |
|--------|------|------|
| OpenAI | GPT-5.4、GPT-5.4-mini、GPT-5.x、GPT-4.1-x、o1、o3-mini | 原生 prompt 缓存、Responses API、reasoning_effort |
| Anthropic | Claude Opus 4.6/4.5/4、Sonnet 4.6/4.5/4、Haiku 4.5 | Extended thinking、prompt 缓存 |
| Google | Gemini 3.1/3/2.5 Pro、Flash 3/2.5/2.0 | 多模态、HD TTS |
| DeepSeek | V3（对话）、R1（推理） | 低成本、原生推理 |
| Perplexity | sonar-small/large-128k-online | 搜索增强生成 |
| Qwen | qwen3-max、qwen3.5-plus、qwen3.5-flash | 思考模式、工具 + 视觉（阿里云） |
| Ollama | 所有本地模型（动态发现） | 零 API 成本、自托管 |

**为什么要 7 个提供商？** 这并非为了收藏而收藏，而是一种弹性策略：管道中的每个节点可以分配不同的提供商。如果 OpenAI 提价，路由器切换到 DeepSeek。如果 Anthropic 宕机，响应切换到 Gemini。LLM 抽象层（`src/infrastructure/llm/factory.py`）使用 Factory 模式配合 `init_chat_model()`，并通过特定适配器覆盖（`ResponsesLLM` 用于 OpenAI 的 Responses API，通过正则表达式 `^(gpt-4\.1|gpt-5|o[1-9])` 判断适用性）。

---

## 3. 后端架构：Domain-Driven Design

### 3.1. 领域结构

```
apps/api/src/
├── core/                         # 横切技术核心
│   ├── config/                   # 9 个 Pydantic BaseSettings 模块通过 MRO 组合
│   │   ├── __init__.py           # Settings 类（最终 MRO）
│   │   ├── agents.py, database.py, llm.py, mcp.py, voice.py, usage_limits.py, ...
│   ├── constants.py              # 1,000+ 集中常量
│   ├── exceptions.py             # 集中异常（raise_user_not_found 等）
│   └── i18n.py                   # i18n → settings 桥接
│
├── domains/                      # 限界上下文（DDD）
│   ├── agents/                   # 主领域 — LangGraph 编排
│   │   ├── nodes/                # 7+ 图节点
│   │   ├── services/             # Smart Services、HITL、上下文解析
│   │   ├── tools/                # 按领域分组的工具（@tool + ToolResponse）
│   │   ├── orchestration/        # ExecutionPlan、并行执行器、验证器
│   │   ├── registry/             # AgentRegistry、domain_taxonomy、catalogue
│   │   ├── semantic/             # 语义路由器、扩展服务
│   │   ├── middleware/           # 记忆注入、人格注入
│   │   ├── prompts/v1/           # 57 个版本化 .txt 提示文件
│   │   ├── graphs/               # 15 个智能体构建器（每个领域一个）
│   │   ├── context/              # Context store（Data Registry）、装饰器
│   │   └── models.py             # MessagesState（TypedDict + 自定义 reducer）
│   ├── auth/                     # OAuth 2.1、BFF 会话、RBAC
│   ├── connectors/               # 多供应商抽象（Google/Apple/Microsoft）
│   ├── rag_spaces/               # 上传、分块、嵌入、混合检索
│   ├── journals/                 # 内省日志
│   ├── interests/                # 兴趣点学习
│   ├── heartbeat/                # LLM 驱动的主动通知
│   ├── channels/                 # 多渠道（Telegram）
│   ├── voice/                    # TTS Factory、STT Sherpa、唤醒词
│   ├── skills/                   # agentskills.io 标准
│   ├── sub_agents/               # 持久化专用智能体
│   ├── usage_limits/             # 按用户配额（5 层防御）
│   └── ...                       # conversations、reminders、scheduled_actions、users、user_mcp
│
└── infrastructure/               # 横切层
    ├── llm/                      # Factory、providers、adapters、embeddings、tracking
    ├── cache/                    # Redis 会话、LLM 缓存、JSON 辅助工具
    ├── mcp/                      # MCP 客户端池、认证、SSRF、工具适配器、Excalidraw
    ├── browser/                  # Playwright 会话池、CDP、反检测
    ├── rate_limiting/            # Redis 分布式滑动窗口
    ├── scheduler/                # APScheduler、领导者选举、锁
    └── observability/            # 17+ Prometheus 指标文件、OTel 追踪
```

### 3.2. 配置优先级链

一个基本不变量贯穿整个后端。在 v1.9.4 中通过对约 80 个文件进行约 291 处修正来系统性地强制执行，因为常量与实际生产配置之间的偏差导致了静默 bug：

```
APPLICATION (Admin UI / DB) > .ENV (settings) > CONSTANT (fallback)
```

**为什么是这个优先级链？** 常量（`src/core/constants.py`）仅作为 Pydantic `Field(default=...)` 和 SQLAlchemy `server_default=` 的回退值。管理员通过界面更改 LLM 模型后，该变更必须立即生效，无需重新部署。在运行时，所有代码读取 `settings.field_name`，绝不直接读取常量。

### 3.3. 分层模式

| 层 | 职责 | 关键模式 |
|----|------|---------|
| **Router** | HTTP 验证、认证、序列化 | `Depends(get_current_active_session)`、`check_resource_ownership()` |
| **Service** | 业务逻辑、编排 | 构造函数接收 `AsyncSession`，创建仓储，集中异常处理 |
| **Repository** | 数据访问 | 继承 `BaseRepository[T]`，分页 `tuple[list[T], int]` |
| **Model** | 数据库模式 | `Mapped[Type]` + `mapped_column()`、`UUIDMixin`、`TimestampMixin` |
| **Schema** | I/O 验证 | Pydantic v2、`Field()` 带描述、请求/响应分离 |

---

## 4. LangGraph：多智能体编排

### 4.1. 为什么选择 LangGraph？（ADR-001）

选择 LangGraph 而非单独的 LangChain、CrewAI 或 AutoGen，基于三个不可妥协的需求：

1. **状态持久化**：带自定义 reducer 的 `TypedDict`，通过 PostgreSQL 检查点持久化 — 允许在 HITL 中断后恢复对话
2. **循环与中断**：原生支持循环（HITL 拒绝 → 重新规划）和 `interrupt()` 模式 — 没有它，6 层 HITL 将无法实现
3. **SSE 流式传输**：与回调处理器的原生集成 — 对实时 UX 至关重要

CrewAI 和 AutoGen 更容易上手，但两者都不支持计划级 HITL 所需的中断/恢复模式。这个选择有其代价：学习曲线更陡峭（图概念、条件边、状态模式）。

### 4.2. 主图

```
                    ┌──────────────────────────────────┐
                    │        Router Node (v3)            │
                    │  Binaire : conversation|actionable  │
                    │  Confiance : high > 0.85            │
                    └──────┬──────────┬─────────────────┘
                           │          │
              conversation │          │ actionable
                           │          │
                    ┌──────▼──┐  ┌───▼───────────────────┐
                    │ Response │  │  QueryAnalyzer          │
                    │  Node    │  │  + SmartPlanner          │
                    └──────────┘  └───┬───────────────────┘
                                      │
                                ┌─────▼───────────────────┐
                                │  Semantic Validator       │
                                └─────┬───────────────────┘
                                      │
                                ┌─────▼───────────────────┐
                                │   Approval Gate           │
                                │   (HITL interrupt)        │
                                └─────┬───────────────────┘
                                      │
                                ┌─────▼───────────────────┐
                                │  Task Orchestrator        │
                                │  (parallel executor)      │
                                └─────┬───────────────────┘
                                      │
                    ┌─────────────────▼────────────────────┐
                    │      15 Domain Agents                  │
                    │  + MCP dynamic agents                  │
                    │  + Sub-agent delegation                │
                    └─────────────────┬────────────────────┘
                                      │
                                ┌─────▼───────────────────┐
                                │   Response Node           │
                                │  (anti-hallucination)     │
                                └───────────────────────────┘
```

### 4.3. 图节点

| 节点 | 文件 | 角色 | 窗口化 |
|------|------|------|--------|
| Router v3 | `router_node_v3.py` | 二元分类 conversation/actionable | 5 轮 |
| QueryAnalyzer | `query_analyzer_service.py` | 领域检测、意图提取 | — |
| Planner v3 | `planner_node_v3.py` | 生成 ExecutionPlan DSL | 10 轮 |
| Semantic Validator | `semantic_validator.py` | 依赖关系和一致性验证 | — |
| Approval Gate | `hitl_dispatch_node.py` | HITL interrupt()，6 级审批 | — |
| Task Orchestrator | `task_orchestrator_node.py` | 并行执行、上下文传递 | — |
| Response | `response_node.py` | 反幻觉合成，3 层防护 | 20 轮 |

### 4.4. AgentRegistry 与 Domain Taxonomy

`AgentRegistry` 集中管理智能体注册（`main.py` 中的 `registry.register_agent()`）、`ToolManifest` 目录和 `domain_taxonomy.py`（定义每个领域及其 `result_key` 和别名）。

**为什么要集中注册？** 没有它，添加一个智能体需要修改 5+ 个文件。有了注册中心，新智能体只需在一个地方声明，即可自动用于路由、规划和执行。

### 4.5. Domain Taxonomy

每个领域都是声明式的 `DomainConfig`：名称、代理、`result_key`（`$steps` 引用的规范键）、`related_domains`、优先级和可路由性。`DOMAIN_REGISTRY` 是三个子系统消费的唯一事实来源：SmartCatalogue（过滤）、语义扩展（相邻领域）和 Initiative 阶段（结构预过滤）。

### 4.6. Tool Manifests

每个工具通过流畅的 `ToolManifestBuilder` 声明一个 `ToolManifest`：参数、输出、成本配置、权限和多语言 `semantic_keywords` 用于路由。清单被规划器（目录注入）、语义路由器（关键词匹配）和代理构建器（工具连接）消费。完整工具架构见第 23 节。

---

## 5. 会话执行管道

### 5.1. 可执行请求的详细流程

1. **接收**：用户消息 → SSE 端点 `/api/v1/chat/stream`
2. **上下文**：`request_tool_manifests_ctx` ContextVar 构建一次（ADR-061：3 层防御）
3. **路由**：带置信度评分的二元分类（high > 0.85、medium > 0.65）
4. **QueryAnalyzer**：通过 LLM + 后扩展验证识别领域（门控过滤器过滤已禁用领域）
5. **SmartPlanner**：生成 `ExecutionPlan`（结构化 JSON DSL）
   - 模式学习：查询贝叶斯缓存（置信度 > 90% 时旁路）
   - 技能检测：确定性 Skills 通过 `_has_potential_skill_match()` 保护
6. **Semantic Validator**：验证步骤间依赖的一致性
7. **HITL Dispatch**：分类审批级别，必要时 `interrupt()`
8. **Task Orchestrator**：通过 `asyncio.gather()` 以并行波次执行步骤
   - 在 gather **之前**过滤已跳过的步骤（ADR-005 — 修复了计划+回退双重执行的 bug）
   - 通过 Data Registry（InMemoryStore）传递上下文
   - FOR_EACH 模式用于批量迭代
9. **Response Node**：合成结果，注入记忆 + 日志 + RAG
10. **SSE 流**：逐 token 发送到前端
11. **后台任务**（fire-and-forget）：记忆提取、日志提取、兴趣检测

### 5.2. ContextVar：隐式状态传播

一个关键机制是使用 Python `ContextVar` 在不进行参数透传的情况下传播状态：

| ContextVar | 角色 | 原因 |
|------------|------|------|
| `current_tracker` | LLM token 追踪的 TrackingContext | 避免在 15 层函数中传递 tracker |
| `request_tool_manifests_ctx` | 按请求过滤的工具清单 | 构建一次，由 7+ 消费者读取（消除 ADR-061 中的重复） |

该方法在 asyncio 上下文中维护每请求的隔离性，而不污染函数签名。

---

## 6. 规划系统（ExecutionPlan DSL）

### 6.1. 计划结构

```python
ExecutionPlan(
    steps=[
        ExecutionStep(
            step_id="get_meetings",
            tool_name="get_events",
            parameters={"date": "tomorrow"},
            dependencies=[]
        ),
        ExecutionStep(
            step_id="send_reminders",
            tool_name="send_email",
            parameters={"subject": "Rappel réunion"},
            dependencies=["get_meetings"],
            for_each="$steps.get_meetings.events",
            for_each_max=10
        )
    ]
)
```

### 6.2. FOR_EACH 模式

**为什么需要专用模式？** 批量操作（例如向 12 个联系人发送邮件）无法规划为 12 个静态步骤 — 元素数量在前一步执行前是未知的。FOR_EACH 通过以下防护机制解决此问题：
- HITL 阈值：任何 >= 1 个元素的变更操作都触发强制审批
- 可配置限制：`for_each_max` 防止无界执行
- 动态引用：`$steps.{step_id}.{field}` 引用前序步骤的结果

### 6.3. 波次并行执行

`parallel_executor.py` 将步骤组织为波次（DAG）：
1. 识别无未解析依赖的步骤 → 下一波次
2. 过滤已跳过的步骤（条件未满足、回退分支）— 在 `asyncio.gather()` **之前**，而非之后（ADR-005：修复了导致 2 倍 API 调用和 2 倍成本的 bug）
3. 以每步错误隔离的方式执行波次
4. 将结果写入 Data Registry
5. 重复直到计划完成

### 6.4. 语义验证器

在 HITL 批准之前，一个专用 LLM（与规划器不同，以避免自我验证偏差）根据四个类别的 14 种问题类型检查计划：**关键**（幻觉能力、幽灵依赖、逻辑循环）、**语义**（基数不匹配、范围溢出/不足、错误参数）、**安全**（危险歧义、隐含假设）和 **FOR_EACH**（缺失基数、无效引用）。简单计划（1 步）短路，乐观 1 秒超时。


此外，一个**自增强反幻觉注册表**（`hallucinated_tools.json`）通过持久化的正则模式检测LLM发明的工具。每次新的幻觉都会自动添加到注册表中。幻觉步骤被移除，规划器被强制使用真实目录工具重新规划。

### 6.5. 引用验证

跨步骤引用（`$steps.get_meetings.events[0].title`）在计划时通过结构化错误消息进行验证：无效字段、可用替代方案和修正示例——使规划器能在重试时自我修正，而非产生静默失败。

### 6.6. 自适应重新规划器（Panic Mode）

执行失败时，基于规则的分析器（无 LLM）对失败模式进行分类（空结果、部分失败、超时、引用错误）并选择恢复策略：相同重试、扩大范围重新规划、上报用户或中止。在 **Panic Mode** 下，SmartCatalogue 扩展为包含所有工具进行一次重试——解决领域过滤过于激进的情况。

---

## 7. Smart Services：智能优化

### 7.1. 解决的问题

未经优化时，扩展到 10+ 领域会导致成本爆炸：从 3 个工具（联系人）增长到 30+ 工具（10 个领域），prompt 大小增长 10 倍，从而每次请求成本增长 10 倍（ADR-003）。Smart Services 旨在将成本降回到单领域系统的水平。

| 服务 | 角色 | 机制 | 实测收益 |
|------|------|------|---------|
| `QueryAnalyzerService` | 路由决策 | LRU 缓存（TTL 5 分钟） | 约 35% 缓存命中 |
| `SmartPlannerService` | 计划生成 | 贝叶斯模式学习 | 置信度 > 90% 时旁路 |
| `SmartCatalogueService` | 工具过滤 | 按领域过滤 | 96% token 缩减 |
| `PlanPatternLearner` | 学习 | 贝叶斯评分 Beta(2,1) | 每次重规划节省约 2,300 token |

### 7.2. PlanPatternLearner

**工作原理**：当计划被验证并成功执行后，其工具序列被记录到 Redis 中（哈希 `plan:patterns:{tool→tool}`，TTL 30 天）。对于后续请求，计算贝叶斯评分：`置信度 = (α + 成功) / (α + β + 成功 + 失败)`。超过 90% 时，直接复用计划而不调用 LLM。

**防护机制**：K-匿名性（最少 3 次观测才建议，10 次才旁路）、领域精确匹配、最多注入 3 个模式（约 45 token 开销）、严格 5 ms 超时。

**冷启动**：启动时预定义 50+ 黄金模式，每个带 20 次模拟成功（= 初始置信度 95.7%）。

### 7.3. QueryIntelligence

QueryAnalyzer 产生的远不止领域检测——它生成深度 `QueryIntelligence` 结构：即时意图与最终目标（`UserGoal`：FIND_INFORMATION、TAKE_ACTION、COMMUNICATE...）、隐含意图（如"查找联系人"可能意味着"发送某物"）、预期回退策略、FOR_EACH 基数提示和 softmax 校准的领域置信度分数。这为规划器提供了比简单关键词提取更丰富的视角。

### 7.4. 语义转换

任何语言的查询在嵌入比较之前自动翻译为英语，提高跨语言准确性。Redis 缓存（TTL 5 分钟，命中 ~5 毫秒 vs 未命中 ~500 毫秒），通过快速 LLM。

---

## 8. 语义路由与语义嵌入

### 8.1. 为什么使用语义嵌入？（ADR-049）

纯 LLM 路由有两个问题：成本（每个请求 = 一次 LLM 调用）和精度（LLM 在约 20% 的多领域场景中判断错误）。语义嵌入同时解决了这两个问题：

| 属性 | 值 |
|------|------|
| 供应商 | OpenAI |
| 语言 | 100+ |
| 精度提升 | 相比纯 LLM 路由，Q/A 匹配提升 +48% |

### 8.2. Semantic Tool Router（ADR-048）

每个 `ToolManifest` 拥有多语言 `semantic_keywords`。请求被转换为嵌入，然后通过余弦相似度与 **max-pooling** 比较（分数 = 每个工具取 MAX，而非平均值 — 避免语义稀释）。双阈值：>= 0.70 = 高置信度，0.60-0.70 = 不确定。

### 8.3. 语义扩展

`expansion_service.py` 通过探索相邻领域来丰富结果。后扩展验证（ADR-061，Layer 1）过滤管理员已禁用的领域 — 修复了 LLM 或扩展可能重新引入已禁用领域的 bug。

---

## 9. Human-in-the-Loop：6 层架构

### 9.1. 为什么在计划层面？（Phase 7 → Phase 8）

最初的方法（Phase 7）在工具调用**期间**中断执行 — 每个敏感工具都生成一次中断。UX 很差（意外暂停），成本很高（每个工具的开销）。

Phase 8（当前方案）在任何执行**之前**将**完整计划**提交给用户。一次中断，全局视图，可编辑参数。权衡：需要信任规划器能生成忠实的计划。

### 9.2. 6 种审批类型

| 类型 | 触发条件 | 机制 |
|------|---------|------|
| `PLAN_APPROVAL` | 破坏性操作 | `interrupt()` 带 PlanSummary |
| `CLARIFICATION` | 检测到歧义 | `interrupt()` 带 LLM 提问 |
| `DRAFT_CRITIQUE` | 邮件/事件/联系人草稿 | `interrupt()` 带序列化草稿 + markdown 模板 |
| `DESTRUCTIVE_CONFIRM` | 删除 >= 3 个元素 | `interrupt()` 带不可逆警告 |
| `FOR_EACH_CONFIRM` | 批量变更 | `interrupt()` 带操作计数 |
| `MODIFIER_REVIEW` | AI 建议的修改 | `interrupt()` 带前后对比 |

### 9.3. 增强型草稿评审

对于草稿，专用提示生成结构化评审，包含按领域的 markdown 模板、字段表情符号、更新时带删除线的前后对比、以及不可逆性警告。HITL 后结果显示 i18n 标签和可点击链接。

### 9.4. 响应分类

当用户回复审批提示时，全 LLM 分类器（非正则表达式）将响应分为 5 种决策：**APPROVE**、**REJECT**、**EDIT**（相同操作，不同参数）、**REPLAN**（完全不同的操作）或 **AMBIGUOUS**。降级逻辑防止误报：缺少参数的 EDIT 被降级为 AMBIGUOUS，触发澄清追问。

### 9.5. 压缩安全

4 个条件阻止在活跃审批流程期间进行 LLM 压缩（旧消息摘要）。没有此保护，摘要可能删除正在进行的中断的关键上下文。

---

## 10. 状态管理与消息窗口化

### 10.1. MessagesState 与自定义 reducer

LangGraph 状态是一个 `TypedDict`，配合 `add_messages_with_truncate` reducer，管理基于 token 的截断、OpenAI 消息序列验证和工具消息去重。

### 10.2. 为什么按节点窗口化？（ADR-007）

**问题**：50+ 条消息的对话产生 100k+ token 上下文，路由器延迟 > 10 秒，成本爆炸。

**解决方案**：每个节点在不同的窗口上操作，根据实际需要校准：

| 节点 | 轮次 | 理由 |
|------|------|------|
| Router | 5 | 快速决策，最小上下文足够 |
| Planner | 10 | 规划需要上下文，但不需要全部历史 |
| Response | 20 | 丰富上下文用于自然合成 |

**实测影响**：端到端延迟 -50%（10 秒 → 5 秒），长对话成本 -77%，质量得以保持，因为 Data Registry 独立于消息存储工具结果。

### 10.3. 上下文压缩

当 token 数超过动态阈值（响应模型上下文窗口的比率）时，生成 LLM 摘要。关键标识符（UUID、URL、邮箱）被保留。节省比率：每次压缩约 60%。`/resume` 命令用于手动触发。

### 10.4. PostgreSQL 检查点

每个节点后完整检查点状态。P95 保存 < 50 ms，P95 加载 < 100 ms，平均大小约 15 KB/对话。

---

## 11. 记忆系统与心理画像

### 11.1. 架构

```
AsyncPostgresStore + Semantic Index (pgvector)
├── Namespace: (user_id, "memories")        → Profil psychologique
├── Namespace: (user_id, "documents", src)  → RAG documentaire
└── Namespace: (user_id, "context", domain) → Contexte outils (Data Registry)
```

### 11.2. 增强记忆模式

每条记忆是一个结构化文档，包含：
- `content`、`category`（偏好、事实、个性、关系、敏感性……）
- `importance`（1-10）、`emotional_weight`（-10 到 +10）
- `usage_nuance`：如何善意地使用此信息
- 嵌入 `text-embedding-3-small`（1536d）通过 pgvector HNSW

**为什么需要情感权重？** 一个知道你母亲生病却把这个事实当作普通数据处理的助手，往好了说是笨拙，往坏了说是伤人的。情感权重允许在涉及敏感话题时激活 `DANGER_DIRECTIVE`（禁止开玩笑、轻描淡写、比较、淡化）。

### 11.3. 提取与注入

**提取**：每次对话后，后台进程分析用户最后一条消息，根据活跃人格进行调整。成本通过 `TrackingContext` 追踪。

**注入**：`memory_injection.py` 中间件搜索语义相近的记忆，构建可注入的心理画像，并在必要时激活 `DANGER_DIRECTIVE`。注入到 Response Node 的系统提示中。

### 11.4. 混合搜索 BM25 + 语义

以可配置的 alpha 进行组合（默认 0.6 语义 / 0.4 BM25）。当两个信号都很强时（> 0.5）提升 10%。BM25 失败时优雅降级为纯语义搜索。性能：有缓存时 40-90 ms。

### 11.5. 日志（Journals）

助手以四个均衡的主题（自我反思、用户观察、想法/分析、学习）撰写内省反思。两个触发器：对话后提取 + 定期整合（4 小时）。OpenAI 1536d 嵌入配合 `search_hints`（用户词汇中的 LLM 关键词）。注入到 **Response Node 和 Planner Node** 的提示中 — 后者使用 `intelligence.original_query` 作为语义查询。

**语义去重守卫**（v1.12.1）：在创建新条目之前，系统会检查与现有条目的语义相似度。如果匹配超过可配置的阈值（`JOURNAL_DEDUP_SIMILARITY_THRESHOLD`，默认 0.72），融合 LLM 会将所有匹配条目合并为一个丰富的指令——N→1 合并并删除次要条目。失败时优雅降级。

反幻觉 UUID：`field_validator`、ID 引用表、在提取和整合中按已知 ID 过滤。

### 11.6. 兴趣系统

通过分析请求进行检测，权重通过贝叶斯演化（衰减 0.01/天）。多源主动通知（Wikipedia、Perplexity、LLM）。用户反馈（点赞/点踩/屏蔽）调整权重。

---

## 12. 多提供商 LLM 基础设施

### 12.1. Factory 模式

```python
llm = get_llm(provider="openai", model="gpt-5.4", temperature=0.7, streaming=True)
```

`get_llm()` 通过 `get_llm_config_for_agent(settings, agent_type)` 解析有效配置（代码默认值 → 数据库管理员覆盖），实例化模型，并应用特定适配器。

### 12.2. 34 种 LLM 配置类型

管道中的每个节点都可通过 Admin UI 独立配置 — 无需重新部署：

| 类别 | 可配置类型 |
|------|-----------|
| 管道 | router、query_analyzer、planner、semantic_validator、context_resolver |
| 响应 | response、hitl_question_generator |
| 后台 | memory_extraction、interest_extraction、journal_extraction、journal_consolidation |
| 智能体 | contacts_agent、emails_agent、calendar_agent、browser_agent 等 |

### 12.3. Token 追踪

`TrackingContext` 追踪每次 LLM 调用，包含 `call_type`（"chat"/"embedding"）、`sequence`（单调递增计数器）、`duration_ms`、token（输入/输出/缓存）、以及从数据库费率计算的成本。追踪器共享 `run_id` 用于聚合。调试面板以统一的时间线视图显示所有调用（管道 + 后台任务）。

---

## 13. 连接器：多供应商抽象

### 13.1. 基于协议的架构

```
ConnectorTool (base.py) → ClientRegistry → resolve_client(type) → Protocol
     ├── GoogleGmailClient       implements EmailClientProtocol
     ├── MicrosoftOutlookClient  implements EmailClientProtocol
     ├── AppleEmailClient        implements EmailClientProtocol
     └── PhilipsHueClient        implements SmartHomeClientProtocol
```

**为什么使用 Python 协议？** 结构化鸭子类型允许在不修改调用方代码的情况下添加新的提供商。`ProviderResolver` 保证每个功能类别只有一个活跃的供应商。

### 13.2. 规范化器

每个提供商以自己的格式返回数据。专用规范化器（`calendar_normalizer`、`contacts_normalizer`、`email_normalizer`、`tasks_normalizer`）将特定于提供商的响应转换为统一的领域模型。添加新提供商只需实现协议和规范化器——调用代码保持不变。

### 13.3. 可复用模式

`BaseOAuthClient`（模板方法，3 个钩子）、`BaseGoogleClient`（通过 pageToken 分页）、`BaseMicrosoftClient`（OData）。断路器、Redis 分布式限流、refresh token 双重检查模式配合 Redis 锁防止惊群效应。

---

## 14. MCP：Model Context Protocol

### 14.1. 架构

`MCPClientManager` 管理连接生命周期（exit stacks）、工具发现（`session.list_tools()`）以及通过 LLM 自动生成领域描述。`ToolAdapter` 将 MCP 工具标准化为 LangChain `@tool` 格式，并对 JSON 响应进行结构化解析为独立项。

### 14.2. MCP 安全性

强制 HTTPS、SSRF 防护（DNS 解析 + IP 黑名单）、Fernet 凭证加密、OAuth 2.1（DCR + PKCE S256）、Redis 按服务器/工具限流、已禁用服务器端点的 API guard 403（ADR-061 Layer 3）。

### 14.3. MCP 迭代模式（ReAct）

`iterative_mode: true` 的 MCP 服务器使用专用 ReAct 智能体（观察/思考/行动循环）代替静态规划器。智能体先读取服务器文档，理解预期格式，然后用正确的参数调用工具。对复杂 API 的服务器（如 Excalidraw）特别有效。可在管理员或用户配置中按服务器启用。由通用 `ReactSubAgentRunner` 驱动（与浏览器智能体共享）。

---

## 15. 语音系统（STT/TTS）

### 15.1. STT

唤醒词（"OK Guy"）通过浏览器中的 Sherpa-onnx WASM 实现（零外部传输）。后端通过 ThreadPoolExecutor 使用 Whisper Small 转录（99+ 语言，离线）。按用户 STT 语言配合线程安全的 `OfflineRecognizer` 按语言缓存。

**延迟优化**：复用 KWS 麦克风流 → 录音（节省约 200-800 ms）、WebSocket 预连接、`getUserMedia` + WS 通过 `Promise.allSettled` 并行化、AudioWorklet 缓存。

### 15.2. TTS

Factory 模式：`TTSFactory.create(mode)` 带自动降级 HD → Standard。Standard = Edge TTS（免费），HD = OpenAI TTS 或 Gemini TTS（高级）。

---

## 16. 主动性：Heartbeat 与计划任务

### 16.1. Heartbeat：2 阶段架构

**阶段 1 — 决策**（高性价比，gpt-4.1-mini）：
1. `EligibilityChecker`：用户 opt-in、时间窗口、冷却期（全局 2 小时、每类型 30 分钟）、近期活跃
2. `ContextAggregator`：通过 `asyncio.gather` 并行获取 7 个源：Calendar、Weather（变化检测）、Tasks、Emails、Interests、Memories、Journals
3. LLM 结构化输出：`skip` | `notify`，带防重复（注入近期历史）

**阶段 2 — 生成**（若 notify）：LLM 以用户人格 + 语言重写。多渠道分发。

### 16.2. Agent Initiative（ADR-062）

后执行 LangGraph 节点：每轮可执行操作后，initiative 分析结果并主动验证跨领域信息（只读）。示例：天气下雨 → 检查日历中的户外活动，邮件提及约会 → 检查可用性，任务截止日期 → 提醒上下文。100% prompt 驱动（无硬编码逻辑），结构化预过滤（相邻领域），注入记忆 + 兴趣点，suggestion 字段用于建议写操作。可通过 `INITIATIVE_ENABLED`、`INITIATIVE_MAX_ITERATIONS`、`INITIATIVE_MAX_ACTIONS` 配置。

### 16.3. 计划任务

APScheduler 配合 Redis 领导者选举（SETNX、TTL 120s、5s 重检）。`FOR UPDATE SKIP LOCKED` 实现隔离。自动批准计划（`plan_approved=True` 注入状态）。连续 5 次失败后自动禁用。瞬时错误重试。

---

## 17. RAG Spaces 与混合搜索

### 17.1. 管道

上传 → 分块 → 嵌入（text-embedding-3-small，1536d） → pgvector HNSW → 混合搜索（余弦 + BM25，alpha 融合） → 注入上下文到 **Response Node**。

注意：RAG 注入在响应节点中进行，而非规划器。规划器则通过 `build_journal_context()` 接收个人日志的注入。

### 17.2. System RAG Spaces（ADR-058）

内置 FAQ（119+ Q/A，17 个分区），从 `docs/knowledge/` 索引。QueryAnalyzer 的 `is_app_help_query` 检测，RoutingDecider 中的 Rule 0 覆盖，App Identity Prompt（约 200 token，懒加载）。SHA-256 过期检测，启动时自动索引。

---

## 18. Browser Control 与 Web Fetch

### 18.1. Web Fetch

URL → SSRF 验证（DNS + IP 黑名单 + 重定向后重检） → 可读性提取（降级为全页面） → HTML 清理 → Markdown → `<external_content>` 包装（防止 prompt 注入）。Redis 缓存 10 分钟。

### 18.2. Browser Control（ADR-059）

自主 ReAct 智能体（Playwright Chromium 无头模式）。Redis 支持的会话池，带跨 worker 恢复。CDP 无障碍树用于按元素交互。反检测（Chrome UA、移除 webdriver 标志、动态区域/时区）。Cookie 横幅自动关闭（20+ 多语言选择器）。读/写分离限流（每个会话各 40 次）。

---

## 19. 安全性：纵深防御

### 19.1. BFF 认证（ADR-002）

**为什么选 BFF 而非 JWT？** localStorage 中的 JWT = XSS 脆弱、90% 大小开销、无法撤销。BFF 模式配合 HTTP-only cookies + Redis 会话消除了这三个问题。v0.3.0 迁移：内存 -90%（1.2 MB → 120 KB），会话查找 P95 < 5 ms，OWASP 评分 B+ → A。

### 19.2. Usage Limits：5 层纵深防御

| 层 | 拦截点 | 为什么需要这一层 |
|----|--------|----------------|
| Layer 0 | Chat 路由器（HTTP 429） | 在 SSE 流之前就阻止 |
| Layer 1 | Agent 服务（SSE 错误） | 覆盖绕过路由器的计划任务 |
| Layer 2 | `invoke_with_instrumentation()` | 覆盖所有后台服务的集中防护 |
| Layer 3 | 主动运行器 | 为被阻止的用户跳过 |
| Layer 4 | 迁移 `.ainvoke()` 直接调用 | 覆盖非集中化的调用 |

**故障开放**设计：基础设施故障不会阻止用户。

### 19.3. 攻击防护

| 攻击向量 | 防护措施 |
|---------|---------|
| XSS | HTTP-only cookies、CSP |
| CSRF | SameSite=Lax |
| SQL 注入 | SQLAlchemy ORM（参数化查询） |
| SSRF | DNS 解析 + IP 黑名单（Web Fetch、MCP、Browser） |
| Prompt 注入 | `<external_content>` 安全标记 |
| 限流 | Redis 分布式滑动窗口（Lua 原子操作） |
| 供应链 | SHA 固定的 GitHub Actions、每周 Dependabot |

---

## 20. 可观测性与监控

### 20.1. 技术栈

| 技术 | 角色 |
|------|------|
| Prometheus | 350+ 自定义指标（RED 模式） |
| Grafana | 18 个生产就绪仪表板 |
| Loki | JSON 结构化日志聚合 |
| Tempo | 跨服务分布式追踪（OTLP gRPC） |
| Langfuse | LLM 专用追踪（prompt 版本、token 用量） |
| structlog | 结构化日志，带 PII 过滤 |

### 20.2. 内嵌调试面板

聊天界面中的调试面板提供按对话的实时内省：意图分析、执行管道、LLM 管道（所有 LLM + embedding 调用的时间线整合）、上下文/记忆、智能（缓存命中、模式学习）、日志（注入 + 后台提取）、生命周期计时。

调试指标持久化在 `sessionStorage` 中（最多 50 条）。

**为什么在 UI 中放调试面板？** 在 AI 智能体以难以调试著称的生态系统中（非确定性行为、不透明的调用链），直接在界面中展示指标消除了打开 Grafana 或阅读日志的摩擦。运维人员可以立即看到为什么某个请求成本很高，或者为什么路由器选择了某个领域。

---

### 20.3. DevOps Claude CLI (v1.13.0 — 仅管理员)

管理员可以直接从LIA对话中与Claude Code CLI交互，使用自然语言诊断服务器问题。Claude CLI安装在API Docker容器内，通过subprocess本地执行，可通过Docker socket检查所有容器。权限可按环境配置，访问仅限超级用户。
## 21. 性能：优化与指标

### 21.1. 关键指标（P95）

| 指标 | 值 | SLO |
|------|------|-----|
| API 延迟 | 450 ms | < 500 ms |
| TTFT（首 token 时间） | 380 ms | < 500 ms |
| 路由器延迟 | 800 ms | < 2 s |
| 规划器延迟 | 2.5 s | < 5 s |
| 语义嵌入 | 约 100 ms | < 200 ms |
| 检查点保存 | < 50 ms | P95 |
| Redis 会话查找 | < 5 ms | P95 |

### 21.2. 已实施的优化

| 优化 | 实测收益 | 权衡 |
|------|---------|------|
| 消息窗口化 | 延迟 -50%，成本 -77% | 丧失旧上下文（由 Data Registry 补偿） |
| Smart Catalogue | 96% token 缩减 | 过度过滤时需要 Panic 模式 |
| 模式学习 | 89% LLM 成本节省 | 需要冷启动（黄金模式） |
| Prompt 缓存 | 90% 折扣 | 取决于供应商支持 |
| 语义嵌入 | 高精度多语言路由 | 依赖 API 供应商可用性 |
| 并行执行 | 延迟 = max(步骤) | 依赖管理复杂度 |
| 上下文压缩 | 每次压缩约 60% | 信息丢失（通过保留 ID 缓解） |

---

## 22. CI/CD 与质量

### 22.1. 管道

```
Pre-commit (local)                GitHub Actions CI
========================          =========================
.bak files check                  Lint Backend (Ruff + Black + MyPy strict)
Secrets grep                      Lint Frontend (ESLint + TypeScript)
Ruff + Black + MyPy               Unit tests + coverage (43 %)
Unit tests rapides                Code Hygiene (i18n, Alembic, .env.example)
Détection patterns critiques      Docker build smoke test
Sync clés i18n                    Secret scan (Gitleaks)
Conflits migration Alembic        ─────────────────────────
Complétude .env.example           Security workflow (hebdomadaire)
ESLint + TypeScript check           CodeQL (Python + JS)
                                    pip-audit + pnpm audit
                                    Trivy filesystem scan
                                    SBOM generation
```

### 22.2. 标准

| 方面 | 工具 | 配置 |
|------|------|------|
| Python 格式化 | Black | line-length=100 |
| Python 检查 | Ruff | E、W、F、I、B、C4、UP |
| 类型检查 | MyPy | strict 模式 |
| 提交 | Conventional Commits | `feat(scope):`、`fix(scope):` |
| 测试 | pytest | `asyncio_mode = "auto"` |
| 覆盖率 | 43% 最低 | CI 中强制执行 |

---

## 23. 横切工程模式

### 23.1. 工具系统：5 层架构

工具系统由五个可组合层构建，将每个工具的样板代码从 ~150 行减少到 ~8 行（94% 减少）：

| 层 | 组件 | 角色 |
|----|------|------|
| 1 | `ConnectorTool[ClientType]` | 通用基础：OAuth 自动刷新、客户端缓存、依赖注入 |
| 2 | `@connector_tool` | 元装饰器组合 `@tool` + 指标 + 速率限制 + 上下文保存 |
| 3 | Formatters | `ContactFormatter`、`EmailFormatter`... — 按领域规范化结果 |
| 4 | `ToolManifest` + Builder | 声明式定义：参数、输出、成本、权限、语义关键词 |
| 5 | Catalogue Loader | 动态内省、清单生成、领域分组 |

速率限制按类别划分：Read（20/分钟）、Write（5/分钟）、Expensive（2/5 分钟）。工具可以产生字符串（旧模式）或结构化的 `UnifiedToolOutput`（Data Registry 模式）。

### 23.2. Data Registry

Data Registry（`InMemoryStore`）将工具结果与消息历史解耦。结果通过 `@auto_save_context` 按请求存储，并在消息窗口化后存活——这是使按节点激进窗口化（5/10/20 轮）在不丢失工具输出上下文的情况下可行的关键。跨步骤引用（`$steps.X.field`）从 registry 解析，而非从消息中。

### 23.3. 错误架构

所有工具返回 `ToolResponse`（成功）或 `ToolErrorModel`（失败），带有 `ToolErrorCode` 枚举（18+ 种类型：INVALID_INPUT、RATE_LIMIT_EXCEEDED、TEMPLATE_EVALUATION_FAILED...）和 `recoverability` 标志。在 API 端，集中的异常引发器（`raise_user_not_found`、`raise_permission_denied`...）在所有地方替代原始 HTTPException——确保一致的错误契约。

### 23.4. 提示系统

`src/domains/agents/prompts/v1/` 中有 57 个版本化的 `.txt` 文件，通过 `load_prompt()` 加载，带 LRU 缓存（32 条目）。版本可通过环境变量配置。

### 23.5. 集中组件激活（ADR-061）

3 层系统解决重复问题：ADR-061 之前，启用/禁用组件的过滤分散在 7+ 个位置。现在：

| 层 | 机制 |
|----|------|
| 层 1 | 领域守门员：验证 LLM 输出的领域是否在 `available_domains` 中 |
| 层 2 | `request_tool_manifests_ctx`：每请求构建一次的 ContextVar |
| 层 3 | MCP 代理端点的 API 守卫 403 |

### 23.6. Feature Flags

每个可选子系统由 `{FEATURE}_ENABLED` 标志控制，在启动（调度器注册）、路由连接和节点入口（即时短路）时检查。这允许部署完整代码库，同时逐步激活子系统。

---

## 24. 架构决策记录（ADR）

59 篇 MADR 格式的 ADR 记录了主要的架构决策。以下是一些代表性示例：

| ADR | 决策 | 解决的问题 | 实测影响 |
|-----|------|-----------|---------|
| 001 | LangGraph 编排 | 需要状态持久化 + HITL 中断 | 检查点 P95 < 50 ms |
| 002 | BFF 模式（JWT → Redis） | JWT XSS 脆弱、无法撤销 | 内存 -90%、OWASP A |
| 003 | 按领域动态过滤 | 10 倍 prompt 大小 = 10 倍成本 | 73-83% 目录缩减 |
| 005 | asyncio.gather 前过滤 | 计划 + 回退并行执行 = 2 倍成本 | 回退计划成本 -50% |
| 007 | 按节点消息窗口化 | 长对话 = 100k+ token | 延迟 -50%、成本 -77% |
| 048 | Semantic Tool Router | 多领域 LLM 路由不精确 | 精度 +48% |
| 049 | 语义嵌入 | 纯 LLM 路由不精确 | 通过语义嵌入精度提升 +48% |
| 057 | 个人日志 | 会话间缺乏反思连续性 | 注入 planner + response |
| 061 | 集中组件激活 | 7+ 个重复过滤位置 | 单一来源、3 层 |

---

## 25. 演进潜力与可扩展性

### 25.1. 扩展点

| 扩展 | 接口 | 文档 |
|------|------|------|
| 新连接器 | `OAuthProvider` Protocol + Client Protocol | `GUIDE_CONNECTOR_IMPLEMENTATION.md` + 检查清单 |
| 新智能体 | `register_agent()` + ToolManifest | `GUIDE_AGENT_CREATION.md` |
| 新工具 | `@tool` + ToolResponse/ToolErrorModel | `GUIDE_TOOL_CREATION.md` |
| 新渠道 | `BaseChannelSender` + `BaseChannelWebhookHandler` | `NEW_CHANNEL_CHECKLIST.md` |
| 新 LLM 提供商 | 适配器 + 模型配置 | 可扩展 Factory |
| 新主动任务 | `ProactiveTask` Protocol | `NEW_PROACTIVE_TASK_CHECKLIST.md` |

### 25.2. 可伸缩性

| 维度 | 当前策略 | 可能的演进 |
|------|---------|-----------|
| 水平扩展 | 4 个 uvicorn worker + Redis 领导者选举 | Kubernetes + HPA |
| 数据 | PostgreSQL + pgvector | 分片、只读副本 |
| 缓存 | Redis 单实例 | Redis Cluster |
| 可观测性 | 完整内嵌技术栈 | 托管 Grafana Cloud |

---

## 26. 心理引擎：动态情感智能

心理引擎赋予助手一个动态的心理状态，随每次互动而演变。5层架构：大五人格特质（永久）→ PAD情绪空间14种情绪（小时）→ 16种离散情感带交叉抑制（分钟）→ 4阶段关系进展（周）→ 好奇心/参与度驱动和自我效能（每次会话）。

**核心原则**：助手从不说"我很高兴"——相反，它的词汇变得更温暖，句子变长，建议变得更大胆。540字的指南（`psyche_usage_directive.txt`）教导LLM如何将每种状态转化为具体行为。通过隐藏的`<psyche_eval/>`XML标签进行零成本自我评估。注入所有面向用户的生成点。

**前端**：每条消息带彩色环的情感头像，4图表仪表板（情绪/情感/关系/动机），7节互动教育指南，可自定义表现力和稳定性。

---

## 结论

LIA 是一项软件工程实践，尝试解决一个具体问题：构建一个生产级的多智能体 AI 助手，透明、安全、可扩展，并且能在 Raspberry Pi 上运行。

59 篇 ADR 不仅记录了做出的决策，还记录了被否决的替代方案和接受的权衡。2,300+ 测试、完整的 CI/CD 和严格的 MyPy 并非虚荣指标 — 它们是让这种复杂度的系统能够无回归演进的机制。

子系统之间的交织 — 心理记忆、贝叶斯学习、语义路由、系统化 HITL、LLM 驱动的主动性、内省日志 — 创造了一个各组件相互增强的系统。HITL 为模式学习提供数据，模式学习降低成本，降低的成本支撑更多功能，更多功能为记忆产生更多数据，记忆改善响应质量。这是一个设计中的良性循环，而非偶然。

---

*本文档基于源代码（`apps/api/src/`、`apps/web/src/`）、技术文档（190+ 份文档）、63 篇 ADR 及变更日志（v1.0 至 v1.12.4）的分析编写。文中引用的所有指标、版本和模式均可在代码库中验证。*
