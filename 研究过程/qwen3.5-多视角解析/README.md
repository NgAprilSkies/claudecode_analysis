# Claude Code 深度解析框架

## 项目说明

本项目是对 Claude Code 开源框架的深度逆向工程分析，采用 Qwen3.5 多视角分析方法，从 Harness Engineering（工程化驾驭）角度解构 AI Agent 框架的设计哲学。

---

## 分析框架 Prompt

以下分析框架已记录于此，供后续分析工作参考：

```markdown
Role: 你是一位拥有 15 年经验的 Agent 架构专家、高级系统工程师和开源项目核心贡献者。
你不仅理解代码逻辑，更擅长以 Harness Engineering（工程化驾驭）的思维深度解构 AI 框架
（即：将 AI 的能力视作一种强大的、可被工程化工具、安全边界和可观察性系统所驾驭的力量）。

Task: 协助我深度解析源代码。

Input: 我将为你提供的核心代码片段或文件路径（claude-code-main）。

Core Requirements (Must to Produce):

## 深度分析：构建智能体的逻辑

请深度分析该库的核心代码，说明它如何构建智能体（Agent）。具体要覆盖以下四个工程化视角，
并从 Harness Engineering 的角度评价其设计决策（如：可扩展性、安全边界、可观察性、性能损耗）：

### 视角 A: 核心构建（The Core Build）
- Agent 的基本结构
- 核心类设计
- 状态管理
- Agent 的完整生命周期（初始化 -> 运行 -> 销毁）

### 视角 B: 任务规划（Planning & Reasoning）
- Agent 接收输入后如何利用 LLM 进行任务拆解
- 决策路径是如何选择和动态调整的

### 视角 C: 工具集成（Tool Integration）
- Agent 如何发现、绑定、安全地执行外部工具和 API
- Harness Engineering 视角：如何处理工具异常、鉴权、权限控制

### 视角 D: 记忆系统（Memory Systems）
- Agent 如何处理长期/短期记忆
- 上下文（Context）是如何被构建和修剪的

## 强制产出

### SVG 架构图 / Drawio
对于你分析的每一个视角 (A, B, C, D)，最终都必须生成一段对应的 SVG 格式代码
（或提供一个极其详细的 drawio XML 结构描述），可视化其内部架构和关键数据流。

### 最小化实现 (MRE)
为每个视角提供一个 50-100 行左右的最小化 Python 实现（MRE），
剥离所有冗余逻辑，只复现该视角的工程实现核心原理。

### 互动挑战
分析完每个视角后，请问我一个"关于该库工程实现的、具有挑战性的问题"
（例如：如果是你，你如何优化这里的内存管理/如果是你，你如何通过工程手段增加这里工具执行的安全性），
以检查我是否真的理解了。

## 执行方式

创建一个 agent team 进行并行分析，由于源代码比较长、复杂，
请每个 team 逐个模块进行分别思考完毕后，请根据不同视角把所有研究内容输出成文档、
流程图 svg 等输出到根目录下的研究过程目录下，创建一个 qwen3.5 多视角解析目录保存。
```

---

## 输出目录结构

```
qwen3.5 多视角解析/
├── 00-分析框架总览.md          # 分析框架说明
├── 01-core-build/              # 视角 A：核心构建分析
│   ├── core-architecture-analysis.md
│   ├── core-architecture.svg
│   ├── mre_core_build.py
│   └── engineering-challenge.md
├── 02-planning-reasoning/      # 视角 B：任务规划分析
│   ├── planning-analysis.md
│   ├── planning-flow.svg
│   ├── mre_planning.py
│   └── engineering-challenge.md
├── 03-tool-integration/        # 视角 C：工具集成分析
│   ├── tool-integration-analysis.md
│   ├── tool-call-chain.svg
│   ├── mre_tool_integration.py
│   └── engineering-challenge.md
├── 04-memory-systems/          # 视角 D：记忆系统分析
│   ├── memory-systems-analysis.md
│   ├── memory-dataflow.svg
│   ├── mre_memory.py
│   └── engineering-challenge.md
└── 99-final-report/            # 汇总报告
    └── comprehensive-analysis.md
```

---

## 分析团队配置

| 角色 | Agent ID | 负责视角 |
|------|----------|----------|
| Team Lead | team-lead@qwen3.5-analysis-team | 协调整体分析 |
| Core Architect | core-architect@qwen3.5-analysis-team | 视角 A：核心构建 |
| Planning Expert | planning-expert@qwen3.5-analysis-team | 视角 B：任务规划 |
| Tool Integration Expert | tool-integration-expert@qwen3.5-analysis-team | 视角 C：工具集成 |
| Memory System Expert | memory-system-expert@qwen3.5-analysis-team | 视角 D：记忆系统 |

---

## Harness Engineering 评价维度

每个视角的分析都将从以下四个维度进行评价：

1. **可扩展性（Extensibility）**
   - 架构如何支持新功能添加
   - 模块化程度
   - 接口设计质量

2. **安全边界（Safety Boundaries）**
   - 权限验证点
   - 输入/输出过滤
   - 危险操作拦截

3. **可观察性（Observability）**
   - 状态监控点
   - 日志和追踪
   - 调试能力

4. **性能损耗（Performance Overhead）**
   - 关键路径分析
   - 缓存策略
   - 资源管理

---

## 已产出内容

### 综合分析报道
- `99-final-report/comprehensive-analysis.md` - 完整的四视角分析报告

### Python MRE 实现
- 视角 A：核心构建 - 包含在综合报告中
- 视角 B：任务规划 - 包含在综合报告中
- 视角 C：工具集成 - 包含在综合报告中
- 视角 D：记忆系统 - 包含在综合报告中

### 挑战性工程问题
每个视角都配有相应的思考题，用于检验理解深度。

---

## 核心源代码文件索引

| 文件 | 主要功能 | 分析视角 |
|------|----------|----------|
| `src/main.tsx` | 应用入口、系统上下文、用户上下文管理 | A |
| `src/Task.ts` | 任务类型定义、状态管理、生命周期 | A |
| `src/Tool.ts` | 工具类型系统、权限检查、构建器模式 | C |
| `src/context.ts` | 上下文构建和缓存 | A, D |
| `src/history.ts` | 历史记录管理、粘贴内容存储 | D |
| `src/commands.ts` | 命令注册系统、动态技能加载 | B |
| `src/query.ts` | 查询循环核心、token 预算、压缩逻辑 | B, D |
| `src/tools.ts` | 工具注册、过滤、预设配置 | C |
| `src/bridge/bridgeMain.ts` | 远程会话桥接、多实例管理 | A |
| `src/services/tools/toolOrchestration.ts` | 工具编排、并发控制 | C |
| `src/utils/permissions/permissions.ts` | 权限验证流程 | C |
| `src/services/compact/autoCompact.ts` | 自动压缩策略 | D |

---

## 使用方式

1. 读取 `99-final-report/comprehensive-analysis.md` 获取完整分析报告
2. 参考各视角目录下的详细分析和 MRE 实现
3. 通过挑战性工程问题检验理解程度

---

*本分析框架由 Qwen3.5 多视角分析团队生成*
*分析日期：2026-04-01*
