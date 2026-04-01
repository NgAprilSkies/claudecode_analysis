# Claude Code 架构深度研究 - 综合索引

## 研究文档导航

本目录包含对 Claude Code 智能体框架的深度架构分析，从四个核心工程化视角进行解构：

| 文档 | 内容 | 文件大小 |
|------|------|----------|
| [00_executive_summary.md](./00_executive_summary.md) | 执行摘要与总体评价 | ~2KB |
| [01_perspective_a_core_build.md](./01_perspective_a_core_build.md) | 视角 A: 核心构建 (Agent 结构、生命周期) | ~25KB |
| [02_perspective_b_planning.md](./02_perspective_b_planning.md) | 视角 B: 任务规划 (决策路径、上下文管理) | ~35KB |
| [03_perspective_c_tools.md](./03_perspective_c_tools.md) | 视角 C: 工具集成 (发现、执行、安全) | ~30KB |
| [04_perspective_d_memory.md](./04_perspective_d_memory.md) | 视角 D: 记忆系统 (层次结构、修剪策略) | ~30KB |

---

## 快速参考图

### 架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Claude Code 架构全景图                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  用户输入 → QueryEngine → query() 循环                              │
│                                │                                    │
│                                ├─→ 上下文管理 (Snip/Micro/Auto)     │
│                                ├─→ LLM API 调用 (流式)               │
│                                ├─→ 工具执行 (StreamingToolExecutor) │
│                                └─→ 后置评估 (Stop Hooks)            │
│                                                                     │
│  工具系统：Agent, Bash, Read, Edit, Glob, Grep, WebSearch, MCP...  │
│                                                                     │
│  记忆系统：Working → Session → Project → User (4 层)                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 核心文件地图

| 组件 | 核心文件 | 关键类/函数 |
|------|----------|-------------|
| 查询引擎 | src/QueryEngine.ts | `QueryEngine`, `submitMessage()` |
| 查询循环 | src/query.ts | `query()`, `queryLoop()` |
| 工具系统 | src/Tool.ts, src/tools.ts | `Tool`, `buildTool()`, `assembleToolPool()` |
| 上下文管理 | src/context.ts | `getSystemContext()`, `getUserContext()` |
| 自动压缩 | src/services/compact/autoCompact.ts | `autoCompactIfNeeded()`, `shouldAutoCompact()` |
| 会话存储 | src/utils/sessionStorage.ts | `recordTranscript()`, `loadTranscriptFromFile()` |
| 历史管理 | src/history.ts | `addToHistory()`, `getHistory()` |
| 权限系统 | src/utils/permissions/permissions.ts | `getAllowRules()`, `getDenyRuleForTool()` |

---

## Harness Engineering 评价汇总

| 维度 | 视角 A | 视角 B | 视角 C | 视角 D | 平均 |
|------|--------|--------|--------|--------|------|
| **可扩展性** | 8/10 | 8/10 | 9/10 | 8/10 | **8.25/10** |
| **安全边界** | 9/10 | 9/10 | 9/10 | 8/10 | **8.75/10** |
| **可观察性** | 7/10 | 7/10 | 8/10 | 7/10 | **7.25/10** |
| **性能损耗** | 7/10 | 7/10 | 7/10 | 7/10 | **7.00/10** |

### 总体评价

Claude Code 展现了一个**高度工程化**的智能体框架设计：

- **优势**: 模块化架构、多层安全边界、灵活的 feature flag 系统
- **劣势**: 状态管理复杂、调试困难、上下文管理策略耦合
- **建议**: 增加状态快照能力、统一日志格式、简化上下文管理决策流程

---

## SVG 图表索引

| 图表 | 描述 | 所在文档 |
|------|------|----------|
| Agent 生命周期图 | 初始化 → 运行 → 销毁三阶段流程 | 01_perspective_a_core_build.md |
| 查询循环决策树 | 7 个 continue 站点的决策逻辑 | 02_perspective_b_planning.md |
| 规划数据流图 | 用户输入 → 上下文 → LLM → 工具 → 状态更新 | 02_perspective_b_planning.md |
| 工具集成架构图 | 发现 → 绑定 → 执行 → 安全边界四层 | 03_perspective_c_tools.md |
| 记忆系统层次图 | L1-L4 记忆 + 5 层上下文管理策略 | 04_perspective_d_memory.md |

---

## MRE (最小化参考实现) 索引

每个视角都提供了一个 Python MRE，剥离冗余逻辑，复现核心原理：

| MRE | 行数 | 核心概念 |
|-----|------|----------|
| [视角 A: 核心构建](./01_perspective_a_core_build.md#a4-最小化实现-mre---python) | ~80 行 | `QueryEngine`, `Tool`, `TaskStatus`, 查询循环 |
| [视角 B: 任务规划](./02_perspective_b_planning.md#b5-最小化实现-mre---python) | ~90 行 | `PlanningEngine`, `State`, `TransitionReason`, continue 模式 |
| [视角 C: 工具集成](./03_perspective_c_tools.md#c5-最小化实现-mre---python) | ~85 行 | `ToolPermissionSystem`, `ToolExecutor`, 权限检查 |
| [视角 D: 记忆系统](./04_perspective_d_memory.md#d5-最小化实现-mre---python) | ~95 行 | `FileStateCache`, `SessionStorage`, `ContextManager`, 压缩策略 |

---

## 挑战性思考问题

每个视角分析后都提出了一个具有挑战性的工程问题：

### 问题 A: 状态管理与内存泄漏
> 如何重新设计 QueryEngine 的状态管理架构，平衡完整历史保留、内存效率和上下文质量？

### 问题 B: 上下文管理策略的选择
> 如果要重新设计上下文管理层次结构，选择统一调度器、反馈控制环路还是预测式压缩？

### 问题 C: 工具执行安全性增强
> 如何设计增强的工具执行安全系统：静态分析沙箱、动态执行沙箱还是能力系统？

### 问题 D: 记忆系统的一致性与恢复
> 如何保证记忆系统的强一致性和可靠恢复：WAL、事件溯源还是两阶段提交？

---

## 关键代码引用索引

| 主题 | 文件 | 行号范围 | 描述 |
|------|------|----------|------|
| QueryEngine 构造 | QueryEngine.ts | 200-207 | 引擎初始化 |
| 查询循环主体 | query.ts | 241-1729 | 主循环实现 |
| 上下文管理 | query.ts | 400-548 | Snip/Micro/Auto/Collapse |
| 工具执行 | query.ts | 1363-1410 | StreamingToolExecutor / runTools |
| 停止钩子 | query.ts | 1267-1280 | handleStopHooks() |
| Token Budget | query.ts | 1308-1354 | 预算检查与继续 |
| 工具组装 | tools.ts | 345-367 | assembleToolPool() |
| 自动压缩 | autoCompact.ts | 241-351 | autoCompactIfNeeded() |
| 历史管理 | history.ts | 355-434 | addToPromptHistory() |
| 会话存储 | sessionStorage.ts | - | recordTranscript() |

---

## 研究方法论

本研究采用以下方法论：

1. **代码审查**: 深度阅读核心源文件 (QueryEngine.ts, query.ts, Tool.ts, etc.)
2. **静态分析**: 追踪函数调用链、数据流、状态转换
3. **架构抽取**: 从代码中提取设计模式、架构决策
4. **Harness Engineering 评价**: 从可扩展性、安全边界、可观察性、性能四个维度评价

---

## 如何使用本研究

### 对于智能体开发者
- 参考 MRE 实现理解核心概念
- 学习 Claude Code 的模块化架构设计
- 借鉴工具系统和权限管理设计

### 对于架构师
- 研究多层上下文管理策略
- 学习 feature flag 驱动的渐进式发布
- 借鉴状态管理和持久化设计

### 对于研究者
- 思考每个视角的挑战性问题
- 探索智能体架构的最佳实践
- 比较不同框架的设计取舍

---

*研究完成日期：2026-03-31*
*分析模型：Claude Code 源代码深度审查*
*研究方法论：Harness Engineering 视角*
