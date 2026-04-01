# Claude Code 源码分析与复现研究

> 本项目是对 **Claude Code** 源码的深入分析与复现研究，基于 2026年3月31日通过 npm source map 暴露的源码快照。

---

## 项目简介

Claude Code 是 Anthropic 官方推出的命令行工具，允许开发者直接在终端中与 Claude AI 交互，执行软件工程任务如编辑文件、运行命令、搜索代码库等。

本项目包含：
- **源码快照**：完整的 Claude Code TypeScript 源码（~1,900文件，~527K行代码）
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
└── 研究过程/                   # 研究过程笔记
    ├── kimi多视角解析/
    └── 多角度剖析/
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

## 源码获取背景

2026年3月31日，[Chaofan Shou (@Fried_rice)](https://x.com/Fried_rice) 公开指出 Claude Code 的源码通过 npm 包中的 source map 文件泄露：

> **"Claude code source code has been leaked via a map file in their npm registry!"**  
> — [@Fried_rice, 2026年3月31日](https://x.com/Fried_rice/status/2038894956459290963)

发布的 source map 引用了托管在 Anthropic R2 存储桶中的未混淆 TypeScript 源码，使得源码快照可以被公开下载。

---

## 相关阅读

- [*Is legal the same as legitimate: AI reimplementation and the erosion of copyleft*](https://writings.hongminhee.org/2026/03/legal-vs-legitimate/) — 关于 AI 重新实现与 copyleft 的分析文章（2026年3月9日）

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
