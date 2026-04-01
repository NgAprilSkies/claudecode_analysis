# Claude Code 架构深度分析报告

## 执行摘要

本报告从 Harness Engineering（工程化驾驭）视角，深度解构 Claude Code 智能体框架的四大核心架构视角。分析基于对源代码的系统性审查，涵盖 Agent 构建、任务规划、工具集成和记忆系统。

---

## 分析概览

### 视角 A: 核心构建 (The Core Build)
- **核心类**: `QueryEngine`, `Task`, `Tool`, `AppState`
- **生命周期**: 初始化 → 运行 (query loop) → 销毁 (abort)
- **状态管理**: 不可变 AppState + Store 模式
- **Harness 评价**: 高度模块化，但状态碎片化增加了复杂性

### 视角 B: 任务规划 (Planning & Reasoning)
- **核心引擎**: `query()` 函数 (query.ts)
- **决策机制**: 流式工具执行 + 多轮对话循环
- **动态调整**: 自动压缩 (autoCompact), 反应式压缩 (reactiveCompact), 上下文折叠 (contextCollapse)
- **Harness 评价**: 多层上下文管理策略提供弹性，但增加了可观察性复杂度

### 视角 C: 工具集成 (Tool Integration)
- **工具系统**: `Tool` 接口 + `buildTool()` 工厂
- **安全边界**: 权限系统 (PermissionMode) + 拒绝规则
- **执行模型**: 流式执行器 (StreamingToolExecutor) + 编排 (toolOrchestration)
- **Harness 评价**: 健壮的权限和异常处理，性能开销可控

### 视角 D: 记忆系统 (Memory Systems)
- **短期记忆**: `mutableMessages` + `FileStateCache`
- **长期记忆**: `history.jsonl` + `MEMORY.md` + 会话存储
- **上下文修剪**: 自动压缩 (autoCompact) + Snip + 上下文折叠
- **Harness 评价**: 多层次记忆管理有效，但修剪策略复杂

---

## 关键架构模式

1. **Feature Flags 驱动开发**: `feature('FLAG_NAME')` 用于死代码消除
2. **异步生成器**: 流式工具执行和查询结果
3. **不可变状态**: `DeepImmutable<AppState>` + 函数式更新
4. **记忆化**: `lodash-es/memoize` 用于昂贵计算
5. **依赖注入**: `QueryDeps` 用于可测试性
6. **工具结果预算**: `applyToolResultBudget()` 用于上下文管理

---

## Harness Engineering 总体评价

| 维度 | 评分 | 评价 |
|------|------|------|
| 可扩展性 | 8/10 | 模块化设计良好，但状态管理复杂 |
| 安全边界 | 9/10 | 多层权限系统，工具隔离清晰 |
| 可观察性 | 7/10 | 日志和分析完善，但调试复杂 |
| 性能损耗 | 7/10 | 记忆化和缓存有效，但上下文管理有开销 |

---

*报告生成日期：2026-03-31*
*分析模型：Claude Code 源代码深度审查*
