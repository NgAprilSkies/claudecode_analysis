# Claude Code 源码分析与复现研究

> 本项目是对 **Claude Code** 源码的深入分析与复现研究，基于 2026 年 3 月 31 日通过 npm source map 暴露的源码快照。

---

## 项目简介

Claude Code 是 Anthropic 官方推出的命令行工具，允许开发者直接在终端中与 Claude AI 交互，执行软件工程任务如编辑文件、运行命令、搜索代码库等。

本项目包含：
- **源码快照**：完整的 Claude Code TypeScript 源码（~1,900 文件，~527K 行代码）
- **架构分析**：详细的模块分析与系统架构梳理
- **复现指南**：从零开始复现 Claude Code 的完整路线图
- **研究过程**：多角度的研究笔记与分析

---

## 目录结构

```
.
├── claude-code-main/          # Claude Code 源码快照
│   ├── src/                   # 源代码目录
│   ├── assets/                # 资源文件
│   └── README.md              # 源码文档
│
├── 复现指南/                   # 复现与分析文档
│   ├── 00-README-文档索引.md    # 文档索引
│   ├── 01-项目概述与架构分析.md  # 项目概述
│   ├── 02-核心工具实现分析.md    # 工具系统分析
│   ├── 03-命令系统与服务层分析.md # 命令与服务分析
│   ├── 04-完整复现路线图.md      # 复现路线图
│   └── 05-核心功能深度分析总结.md # 功能总结
│
├── 参考资料/                   # 参考资料与外部文献
│
└── 研究过程/                   # 研究过程笔记
    ├── kimi 多视角解析/
    ├── qwen3.5-多视角解析/
    ├── 多角度剖析/
    └── glm5.1/                 # GLM-5.1 四视角深度分析
        ├── perspective-A-core-build.md
        ├── perspective-A-architecture.svg
        ├── perspective-A-mre.py
        ├── perspective-B-planning.md
        ├── perspective-B-architecture.svg
        ├── perspective-B-mre.py
        ├── perspective-C-tool-integration.md
        ├── perspective-C-architecture.svg
        ├── perspective-C-mre.py
        ├── perspective-D-memory.md
        ├── perspective-D-architecture.svg
        └── perspective-D-mre.py
```

---

## 技术栈

| 类别 | 技术 |
|------|------|
| 运行时 | [Bun](https://bun.sh) |
| 语言 | TypeScript (strict mode) |
| 终端 UI | [React](https://react.dev) + [Ink](https://github.com/vadimdemedes/ink) |
| CLI 解析 | [Commander.js](https://github.com/tj/commander.js) |
| 架构验证 | [Zod v4](https://zod.dev) |
| 代码搜索 | [ripgrep](https://github.com/BurntSushi/ripgrep) |
| 协议支持 | MCP, LSP |
| API | Anthropic SDK |

---

## 核心架构

### 1. 工具系统 (`src/tools/`)

Claude Code 实现了约 40 个工具，每个工具都是独立的模块：

| 工具 | 描述 |
|------|------|
| `BashTool` | 执行 Shell 命令 |
| `FileReadTool` | 读取文件（支持图片、PDF、Notebook） |
| `FileWriteTool` | 创建/覆盖文件 |
| `FileEditTool` | 部分修改文件（字符串替换） |
| `GlobTool` | 文件模式匹配搜索 |
| `GrepTool` | 基于 ripgrep 的内容搜索 |
| `AgentTool` | 子 Agent 创建 |
| `WebFetchTool` | 获取 URL 内容 |
| `WebSearchTool` | 网页搜索 |
| `TaskCreateTool` / `TaskUpdateTool` | 任务管理 |
| `TeamCreateTool` / `TeamDeleteTool` | 团队管理 |
| `MCPTool` | MCP 服务器工具调用 |
| `NotebookEditTool` | Jupyter Notebook 编辑 |

### 2. 命令系统 (`src/commands/`)

用户通过 `/` 前缀调用命令：

| 命令 | 描述 |
|------|------|
| `/commit` | 创建 Git 提交 |
| `/review` | 代码审查 |
| `/compact` | 上下文压缩 |
| `/mcp` | MCP 服务器管理 |
| `/config` | 设置管理 |
| `/doctor` | 环境诊断 |
| `/memory` | 持久化内存管理 |
| `/skills` | 技能管理 |
| `/tasks` | 任务管理 |
| `/vim` | Vim 模式切换 |

### 3. 服务层 (`src/services/`)

- **API 服务**: Anthropic API 客户端、文件 API
- **MCP 服务**: Model Context Protocol 服务器管理
- **LSP 服务**: 语言服务器协议支持
- **OAuth 服务**: 身份验证流程
- **分析服务**: 功能标志和遥测

### 4. 桥接系统 (`src/bridge/`)

连接 IDE 扩展（VS Code、JetBrains）与 Claude Code CLI 的双向通信层。

### 5. 权限系统 (`src/hooks/toolPermission/`)

每个工具调用都经过权限检查，支持多种模式：`default`、`plan`、`bypassPermissions`、`auto` 等。

---

## GLM-5.1 深度分析（四视角）

基于 Harness Engineering 方法论，使用 GLM-5.1 模型从四个工程化视角对 Claude Code 进行深度源码分析。每个视角产出分析文档、SVG 架构图和 Python 最小化可运行实现（MRE）。

### 视角 A: 核心构建（The Core Build）

分析 Agent 的基本结构、核心类设计、状态管理及完整生命周期（初始化 → 运行 → 销毁）。

- `perspective-A-core-build.md` — Task 基类继承体系、LocalAgentTask/InProcessTeammateTask 生命周期、Swarm 编排、Coordinator 协调机制
- `perspective-A-architecture.svg` — 核心类层次结构与状态机架构图
- `perspective-A-mre.py` — Agent 基类、生命周期管理、状态机的最小化复现

### 视角 B: 任务规划（Planning & Reasoning）

分析 Agent 接收输入后如何利用 LLM 进行任务拆解，决策路径的选择和动态调整。

- `perspective-B-planning.md` — QueryEngine 查询处理、LLM 调用链、Plan mode 实现、上下文构建流程
- `perspective-B-architecture.svg` — 用户输入到 LLM 调用的完整数据流与决策树
- `perspective-B-mre.py` — 简化查询引擎、LLM 调用模拟、Plan mode 状态机

### 视角 C: 工具集成（Tool Integration）

分析 Agent 如何发现、绑定、安全地执行外部工具和 API，重点关注 5 层纵深防御权限系统。

- `perspective-C-tool-integration.md` — Tool 接口设计、buildTool 工厂、BashTool 23 个安全验证器、MCP 协议集成、沙箱执行
- `perspective-C-architecture.svg` — 工具继承层次与 5 层权限控制流程图
- `perspective-C-mre.py` — Tool 注册、权限规则引擎、安全验证器链的最小化复现

### 视角 D: 记忆系统（Memory Systems）

分析 Agent 如何处理长期/短期记忆，上下文的构建和修剪策略。

- `perspective-D-memory.md` — Session Memory、Context 压缩、记忆提取与持久化、团队记忆同步
- `perspective-D-architecture.svg` — 记忆层次架构与上下文修剪流程
- `perspective-D-mre.py` — 分层记忆存储、Context 修剪、记忆持久化的最小化复现

---

## 源码获取背景

2026 年 3 月 31 日，[Chaofan Shou (@Fried_rice)](https://x.com/Fried_rice) 公开指出 Claude Code 的源码通过 npm 包中的 source map 文件泄露：

> **"Claude code source code has been leaked via a map file in their npm registry!"**  
> — [@Fried_rice, 2026 年 3 月 31 日](https://x.com/Fried_rice/status/2038894956459290963)

发布的 source map 引用了托管在 Anthropic R2 存储桶中的未混淆 TypeScript 源码，使得源码快照可以被公开下载。

---

## 相关阅读

- [*Is legal the same as legitimate: AI reimplementation and the erosion of copyleft*](https://writings.hongminhee.org/2026/03/legal-vs-legitimate/) — 关于 AI 重新实现与 copyleft 的分析文章（2026 年 3 月 9 日）

---

## 分析提示词 (Prompt)

使用以下提示词来引导深度源码分析：

```text
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
流程图 svg 等输出到根目录下的研究过程目录下，创建一个 glm5.1 目录保存。
```

---

## 研究目标

本项目旨在：

1. **架构学习** - 理解现代 Agentic CLI 系统的设计模式
2. **安全研究** - 分析软件供应链泄露和构建产物暴露
3. **教育目的** - 学习 TypeScript、React Ink、Bun 等技术栈的最佳实践
4. **复现探索** - 探索从零构建类似系统的可行性

---

## 免责声明

- 本项目为**教育和防御性安全研究**存档
- 原始 Claude Code 源码归 **Anthropic** 所有
- 本项目**不隶属于、不认可、不由 Anthropic 维护**
- 源码仅用于学习和研究目的

---

## 许可证

原始源码版权归 Anthropic 所有。本项目的分析和文档遵循相应的开源规范。

---

*Maintained for research and educational purposes.*
