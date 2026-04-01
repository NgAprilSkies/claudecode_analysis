# 视角B：任务规划（Planning & Reasoning）分析

## 概述

本文档从Harness Engineering视角深度分析Claude Code的Agent任务规划和推理机制。核心关注Agent如何接收输入、利用LLM进行任务拆解、选择决策路径，以及系统的可扩展性、安全边界和可观察性设计。

---

## 一、查询处理流程分析

### 1.1 核心架构组件

| 组件 | 文件路径 | 职责 |
|------|----------|------|
| **query.ts** | `src/query.ts` | 核心查询循环，管理LLM交互和状态机 |
| **QueryEngine** | `src/QueryEngine.ts` | SDK/Headless入口，管理会话生命周期 |
| **context.ts** | `src/context.ts` | 上下文构建（Git状态、用户上下文等） |
| **thinking.ts** | `src/utils/thinking.ts` | 思考模式配置管理 |

### 1.2 查询循环状态机（State Machine）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Query Loop State Machine                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐               │
│  │  Initial    │────▶│  Setup      │────▶│  API Call   │               │
│  │  State      │     │  Phase      │     │  Streaming  │               │
│  └─────────────┘     └─────────────┘     └──────┬──────┘               │
│                                                 │                       │
│                    ┌────────────────────────────┘                       │
│                    │                                                    │
│                    ▼                                                    │
│           ┌─────────────────┐                                           │
│           │  Tool Execution │◄──────────────────┐                      │
│           │  (if tool_use)  │                   │                      │
│           └────────┬────────┘                   │                      │
│                    │                            │                      │
│                    ▼                            │                      │
│           ┌─────────────────┐    ┌──────────────┴───────┐              │
│           │   Stop Hooks    │───▶│  Terminal States     │              │
│           │   Evaluation    │    │  (completed/error)   │              │
│           └─────────────────┘    └──────────────────────┘              │
│                    │                                                    │
│                    └──────────────────────────────────────────▶ (continue loop)
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.3 状态结构（State Interface）

```typescript
// src/query.ts:203-217
type State = {
  messages: Message[]                          // 消息历史
  toolUseContext: ToolUseContext               // 工具上下文
  autoCompactTracking: AutoCompactTrackingState | undefined  // 自动压缩追踪
  maxOutputTokensRecoveryCount: number         // 输出token恢复计数
  hasAttemptedReactiveCompact: boolean         // 是否已尝试反应式压缩
  maxOutputTokensOverride: number | undefined  // 最大输出token覆盖
  pendingToolUseSummary: Promise<ToolUseSummaryMessage | null> | undefined
  stopHookActive: boolean | undefined          // Stop hook激活状态
  turnCount: number                            // 轮次计数（防止无限循环）
  transition: Continue | undefined             // 上一次继续的原因
}
```

### 1.4 查询处理流程详解

**Phase 1: 初始化与上下文准备**
```typescript
// query.ts:295-304
const config = buildQueryConfig()  // 快照不可变配置
using pendingMemoryPrefetch = startRelevantMemoryPrefetch(...)  // 预取相关记忆
```

**Phase 2: 上下文压缩与优化**
1. **Snip Compact** (`HISTORY_SNIP`): 移除过期的历史消息
2. **Micro Compact**: 缓存级别的消息压缩
3. **Context Collapse** (`CONTEXT_COLLAPSE`): 智能上下文折叠
4. **Auto Compact**: 自动大上下文压缩

**Phase 3: LLM API调用**
```typescript
// query.ts:659-708
for await (const message of deps.callModel({...})) {
  // 流式处理响应
  // 支持模型降级回退（fallback）
  // 支持max_output_tokens恢复
}
```

**Phase 4: 工具执行**
```typescript
// query.ts:1380-1408
const toolUpdates = streamingToolExecutor
  ? streamingToolExecutor.getRemainingResults()
  : runTools(toolUseBlocks, assistantMessages, canUseTool, toolUseContext)
```

**Phase 5: Stop Hooks评估**
```typescript
// query.ts:1267-1306
const stopHookResult = yield* handleStopHooks(...)
if (stopHookResult.blockingErrors.length > 0) {
  // 继续循环，将错误信息反馈给LLM
}
```

---

## 二、任务拆解机制分析

### 2.1 思考模式（Thinking Mode）

```typescript
// src/utils/thinking.ts:10-13
export type ThinkingConfig =
  | { type: 'adaptive' }           // 自适应思考
  | { type: 'enabled'; budgetTokens: number }  // 固定预算
  | { type: 'disabled' }           // 禁用
```

**关键特性：**
- **Adaptive Thinking**: Claude 4.6+ 模型支持，根据任务复杂度动态调整
- **Ultrathink**: 通过关键词触发深度思考模式
- **模型感知**: 不同模型支持不同的思考模式 (`modelSupportsThinking`)

### 2.2 Token预算与任务边界

```typescript
// src/query/tokenBudget.ts:1-93
const COMPLETION_THRESHOLD = 0.9     // 90%预算阈值
const DIMINISHING_THRESHOLD = 500    // 收益递减阈值

export function checkTokenBudget(
  tracker: BudgetTracker,
  agentId: string | undefined,
  budget: number | null,
  globalTurnTokens: number,
): TokenBudgetDecision {
  // 1. 检查是否达到预算上限
  // 2. 检测收益递减（连续3次增量<500 tokens）
  // 3. 决定是否继续或停止
}
```

### 2.3 任务预算（Task Budget）机制

```typescript
// query.ts:196-197
// API task_budget (output_config.task_budget, beta task-budgets-2026-03-13)
taskBudget?: { total: number }
```

**设计要点：**
- `total`: 整个agentic turn的预算
- `remaining`: 每次迭代从累积API使用中计算
- 在上下文压缩后，需要向API报告pre-compact的final window

---

## 三、决策路径选择分析

### 3.1 决策路径图

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         Decision Path Selection                            │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  API Response                                                              │
│      │                                                                     │
│      ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐          │
│  │  Is Prompt Too Long (413)?                                  │          │
│  └─────────────────────────────────────────────────────────────┘          │
│      │ Yes                                                                │
│      ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐          │
│  │  1. Try Context Collapse Drain                              │          │
│  │  2. Try Reactive Compact                                    │          │
│  │  3. Surface Error                                           │          │
│  └─────────────────────────────────────────────────────────────┘          │
│      │ No                                                                 │
│      ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐          │
│  │  Is Max Output Tokens Hit?                                  │          │
│  └─────────────────────────────────────────────────────────────┘          │
│      │ Yes                                    │ No                         │
│      ▼                                         ▼                           │
│  ┌─────────────────────────┐          ┌─────────────────────────┐          │
│  │  Escalate to 64k        │          │  Has Tool Use?          │          │
│  │  or Recovery Loop       │          │                         │          │
│  │  (max 3 retries)        │          │                         │          │
│  └─────────────────────────┘          └───────────┬─────────────┘          │
│                                                   │ Yes                    │
│                                                   ▼                        │
│                                           ┌───────────────┐                │
│                                           │ Execute Tools │                │
│                                           └───────┬───────┘                │
│                                                   │                        │
│                                                   ▼                        │
│                                           ┌───────────────┐                │
│                                           │ Stop Hooks    │                │
│                                           │ Evaluation    │                │
│                                           └───────┬───────┘                │
│                                                   │                        │
│                          ┌────────────────────────┼────────────────────┐   │
│                          ▼                        ▼                    ▼   │
│                   ┌──────────┐           ┌──────────┐           ┌─────────┐│
│                   │ Blocking │           │ Continue │           │ Prevent ││
│                   │ Errors   │           │ (next)   │           │ Stop    ││
│                   └──────────┘           └──────────┘           └─────────┘│
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Transition类型定义

```typescript
// 隐式定义在query.ts中的State.transition
// 记录每次循环继续的原因，用于：
// 1. 调试和日志
// 2. 防止无限循环（配合circuit breaker）
// 3. 测试断言

type TransitionReason =
  | 'collapse_drain_retry'       // 上下文折叠恢复
  | 'reactive_compact_retry'     // 反应式压缩恢复
  | 'max_output_tokens_escalate' // Token上限升级
  | 'max_output_tokens_recovery' // Token上限恢复
  | 'stop_hook_blocking'         // Stop hook阻塞
  | 'token_budget_continuation'  // Token预算继续
  | 'next_turn'                  // 正常下一轮
```

### 3.3 Circuit Breaker模式

```typescript
// src/services/compact/autoCompact.ts:67-70
const MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3

// query.ts:260-265
if (
  tracking?.consecutiveFailures !== undefined &&
  tracking.consecutiveFailures >= MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES
) {
  return { wasCompacted: false }  // 熔断，停止尝试
}
```

---

## 四、Harness Engineering评价

### 4.1 可扩展性设计

#### 4.1.1 依赖注入（Dependency Injection）

```typescript
// src/query/deps.ts:21-40
export type QueryDeps = {
  callModel: typeof queryModelWithStreaming
  microcompact: typeof microcompactMessages
  autocompact: typeof autoCompactIfNeeded
  uuid: () => string
}

export function productionDeps(): QueryDeps {
  return {
    callModel: queryModelWithStreaming,
    microcompact: microcompactMessages,
    autocompact: autoCompactIfNeeded,
    uuid: randomUUID,
  }
}
```

**优点：**
- 测试时可注入mock，无需spyOn
- 模块边界清晰
- 支持渐进式重构

#### 4.1.2 Feature Gates（特性门控）

```typescript
// 使用bun:bundle的feature()进行编译时树摇
const reactiveCompact = feature('REACTIVE_COMPACT')
  ? require('./services/compact/reactiveCompact.js')
  : null

// 运行时门控使用GrowthBox/Statsig
const streamingToolExecution = checkStatsigFeatureGate_CACHED_MAY_BE_STALE(
  'tengu_streaming_tool_execution2'
)
```

#### 4.1.3 查询配置快照

```typescript
// src/query/config.ts:15-27
export type QueryConfig = {
  sessionId: SessionId
  gates: {
    streamingToolExecution: boolean
    emitToolUseSummaries: boolean
    isAnt: boolean
    fastModeEnabled: boolean
  }
}
```

### 4.2 安全边界设计

#### 4.2.1 多层防护机制

| 层级 | 机制 | 实现位置 |
|------|------|----------|
| **Token上限** | maxTurns | `QueryParams.maxTurns` |
| **预算控制** | Token Budget | `tokenBudget.ts` |
| **熔断器** | Circuit Breaker | `autoCompact.ts:70` |
| **上下文限制** | Blocking Limit | `query.ts:636-648` |
| **响应大小** | maxOutputTokens | `query.ts:164` |

#### 4.2.2 Max Turns限制

```typescript
// QueryEngine.ts:1705-1712
if (maxTurns && nextTurnCount > maxTurns) {
  yield createAttachmentMessage({
    type: 'max_turns_reached',
    maxTurns,
    turnCount: nextTurnCount,
  })
  return { reason: 'max_turns', turnCount: nextTurnCount }
}
```

#### 4.2.3 USD预算限制

```typescript
// QueryEngine.ts:972-1001
if (maxBudgetUsd !== undefined && getTotalCost() >= maxBudgetUsd) {
  yield {
    type: 'result',
    subtype: 'error_max_budget_usd',
    errors: [`Reached maximum budget ($${maxBudgetUsd})`],
  }
}
```

### 4.3 可观察性设计

#### 4.3.1 查询性能检查点

```typescript
// src/utils/queryProfiler.ts
export function queryCheckpoint(label: string) {
  // 记录关键路径时间戳
}

// 使用示例：
queryCheckpoint('query_fn_entry')
queryCheckpoint('query_snip_start')
queryCheckpoint('query_microcompact_start')
queryCheckpoint('query_autocompact_start')
queryCheckpoint('query_setup_start')
queryCheckpoint('query_api_loop_start')
queryCheckpoint('query_tool_execution_start')
```

#### 4.3.2 事件日志系统

```typescript
// 关键事件记录
logEvent('tengu_query_error', {...})
logEvent('tengu_auto_compact_succeeded', {...})
logEvent('tengu_model_fallback_triggered', {...})
logEvent('tengu_orphaned_messages_tombstoned', {...})
logEvent('tengu_stop_hook_error', {...})
logEvent('tengu_token_budget_completed', {...})
```

#### 4.3.3 Query Chain追踪

```typescript
// query.ts:346-363
const queryTracking = toolUseContext.queryTracking
  ? {
      chainId: toolUseContext.queryTracking.chainId,
      depth: toolUseContext.queryTracking.depth + 1,
    }
  : {
      chainId: deps.uuid(),
      depth: 0,
    }
```

### 4.4 性能损耗分析

#### 4.4.1 性能优化策略

| 策略 | 实现 | 收益 |
|------|------|------|
| **预取** | `startRelevantMemoryPrefetch` | 隐藏I/O延迟 |
| **流式执行** | `StreamingToolExecutor` | 并行化工具调用 |
| **缓存** | Prompt Caching | 减少API成本 |
| **压缩** | Auto/Micro Compact | 控制上下文大小 |
| **懒加载** | Feature-gated requires | 减少启动时间 |

#### 4.4.2 关键性能指标

```typescript
// Headless Profiler检查点
headlessProfilerCheckpoint('before_getSystemPrompt')
headlessProfilerCheckpoint('after_getSystemPrompt')
headlessProfilerCheckpoint('before_skills_plugins')
headlessProfilerCheckpoint('after_skills_plugins')
headlessProfilerCheckpoint('system_message_yielded')
```

#### 4.4.3 上下文管理成本

```
┌─────────────────────────────────────────────────────────────┐
│              Context Management Performance                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Snip Compact      ~O(n)      移除过期消息                  │
│  Micro Compact     ~O(1)      缓存操作                      │
│  Context Collapse  ~O(n)      智能折叠                      │
│  Auto Compact      ~O(n)      API调用（Haiku ~1s）          │
│                                                             │
│  注：Auto Compact使用Haiku模型，与主模型流并行执行          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 五、MRE代码说明

### 5.1 最小可复现实现（Python）

见同目录下的 `视角B-MRE.py` 文件，该实现展示了：

1. **状态机模式**：使用State dataclass管理循环状态
2. **依赖注入**：通过QueryDeps接口解耦组件
3. **熔断器模式**：防止无限重试
4. **过渡追踪**：记录每次循环继续的原因
5. **安全检查**：max_turns、token_budget等多层防护

### 5.2 关键设计模式映射

| Claude Code实现 | MRE对应实现 |
|----------------|-------------|
| `query.ts` State | `State` dataclass |
| `query.ts` queryLoop | `QueryEngine.query()` 生成器 |
| `QueryDeps` | `QueryDeps` Protocol |
| `tokenBudget.ts` | `TokenBudget` class |
| `autoCompact.ts` circuit breaker | `CircuitBreaker` class |

---

## 六、总结

### 6.1 架构亮点

1. **清晰的状态管理**：使用不可变config + 可变state分离关注点
2. **防御性编程**：多层circuit breaker防止级联故障
3. **渐进式扩展**：Feature gates支持功能渐进 rollout
4. **流式架构**：全链路流式处理，支持大响应和实时反馈

### 6.2 潜在改进点

1. **复杂度**：query.ts 1700+行，可考虑进一步模块化
2. **状态分散**：State、ToolUseContext、AppState有重叠
3. **错误处理**：部分路径使用throw，部分使用yield error message

---

## 七、互动挑战

**问题：如果是你，你会如何通过工程手段防止LLM推理过程中的无限循环？**

基于以上分析，Claude Code采用了以下策略：
1. **maxTurns硬限制**
2. **Token预算限制**
3. **Circuit Breaker熔断**
4. **Transition追踪与重复检测**

你认为还有哪些补充手段？例如：
- 基于语义的循环检测（检测重复输出模式）
- 动态超时机制
- 用户干预提示
- 其他...

欢迎讨论！

---

*文档生成时间：2026-04-01*  
*分析视角：Harness Engineering*  
*版本：v1.0*
