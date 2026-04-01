# Claude Code 任务规划与推理机制分析
## Perspective B: Planning & Reasoning

### 目录
1. [查询处理完整流程](#查询处理完整流程)
2. [LLM 调用链分析](#llm-调用链分析)
3. [任务拆解策略](#任务拆解策略)
4. [决策路径动态调整机制](#决策路径动态调整机制)
5. [Plan Mode 实现原理](#plan-mode-实现原理)
6. [Ultra Planning 机制](#ultra-planning-机制)
7. [Harness Engineering 评价](#harness-engineering-评价)

---

## 1. 查询处理完整流程

### 1.1 入口点：QueryEngine.submitMessage()

`QueryEngine.ts:209-1156` 中的 `submitMessage()` 方法是整个查询处理的核心入口点。

```typescript
async *submitMessage(
  prompt: string | ContentBlockParam[],
  options?: { uuid?: string; isMeta?: boolean },
): AsyncGenerator<SDKMessage, void, unknown>
```

**流程步骤：**

1. **初始化阶段** (L209-431)
   - 设置 `wrappedCanUseTool` 包装器跟踪权限拒绝
   - 获取初始模型配置 (`parseUserSpecifiedModel`)
   - 获取系统提示词各部分 (`fetchSystemPromptParts`)
   - 构建用户上下文 (`userContext`)

2. **用户输入处理** (L416-431)
   - 调用 `processUserInput()` 处理用户输入
   - 处理斜杠命令、关键词触发（如 ultraplan）
   - 返回 `shouldQuery` 标志决定是否需要进行查询

3. **技能和插件加载** (L534-538)
   ```typescript
   const [skills, { enabled: enabledPlugins }] = await Promise.all([
     getSlashCommandToolSkills(getCwd()),
     loadAllPluginsCacheOnly(),
   ])
   ```

4. **查询循环启动** (L675-704)
   ```typescript
   for await (const message of query({
     messages,
     systemPrompt,
     userContext,
     systemContext,
     canUseTool: wrappedCanUseTool,
     toolUseContext: processUserInputContext,
     fallbackModel,
     querySource: 'sdk',
     maxTurns,
     taskBudget,
   })) {
     // 处理消息...
   }
   ```

### 1.2 查询循环核心：query()

`query.ts:241-1729` 中的 `queryLoop()` 函数实现了完整的查询循环机制。

**核心数据结构：**

```typescript
type State = {
  messages: Message[]
  toolUseContext: ToolUseContext
  autoCompactTracking: AutoCompactTrackingState | undefined
  maxOutputTokensRecoveryCount: number
  hasAttemptedReactiveCompact: boolean
  maxOutputTokensOverride: number | undefined
  pendingToolUseSummary: Promise<ToolUseSummaryMessage | null> | undefined
  stopHookActive: boolean | undefined
  turnCount: number
  transition: Continue | undefined
}
```

**循环状态转换：**

```
┌─────────────────────────────────────────────────────────────┐
│                    Query Loop                               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  1. 上下文构建 (microcompact, autocompact, snip)      │  │
│  │  2. LLM API 调用 (queryModel)                         │  │
│  │  3. 工具执行 (runTools / StreamingToolExecutor)       │  │
│  │  4. 停止钩子处理 (handleStopHooks)                    │  │
│  │  5. 继续检查 (token budget, max_turns)                │  │
│  └───────────────────────────────────────────────────────┘  │
│         ↓                                              ↑       │
│         └────────────── Continue ←──────────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. LLM 调用链分析

### 2.1 调用路径

```
QueryEngine.submitMessage
    ↓
query(queryLoop)
    ↓
deps.callModel(query.ts:659-707)
    ↓
queryModel(claude.ts:1017-2892)
    ↓
anthropic.beta.messages.create (SDK)
```

### 2.2 请求构建 (claude.ts:1538-1739)

**参数构建函数 `paramsFromContext()`:**

```typescript
const paramsFromContext = (retryContext: RetryContext) => {
  return {
    model: normalizeModelStringForAPI(options.model),
    messages: addCacheBreakpoints(...),
    system: system,  // 构建的system blocks
    tools: allTools,
    tool_choice: options.toolChoice,
    ...(useBetas && { betas: betasParams }),
    metadata: getAPIMetadata(),
    max_tokens: maxOutputTokens,
    thinking: thinking,  // thinking配置
    ...(contextManagement && { context_management }),
    ...extraBodyParams,
  }
}
```

### 2.3 Beta 特性管理

代码中使用动态 Beta 特性来控制实验性功能：

```typescript
// Beta 头部缓存机制 (claude.ts:1412-1457)
let afkHeaderLatched = getAfkModeHeaderLatched() === true
let fastModeHeaderLatched = getFastModeHeaderLatched() === true
let cacheEditingHeaderLatched = getCacheEditingHeaderLatched() === true
```

**核心 Beta 头部：**
- `CONTEXT_MANAGEMENT_BETA_HEADER`: 上下文管理
- `FAST_MODE_BETA_HEADER`: 快速模式
- `PROMPT_CACHING_SCOPE_BETA_HEADER`: 提示缓存范围
- `REDACT_THINKING_BETA_HEADER`: 思维脱敏
- `TASK_BUDGETS_BETA_HEADER`: 任务预算
- `ADVISOR_BETA_HEADER`: 顾问工具
- `TOOL_SEARCH_TOOL_NAME`: 工具搜索

### 2.4 流式响应处理

```typescript
for await (const part of stream) {
  switch (part.type) {
    case 'message_start':
      partialMessage = part.message
      ttftMs = Date.now() - start
      break
    case 'content_block_delta':
      // 累积内容块增量
      break
    case 'content_block_stop':
      // 产出 AssistantMessage
      yield m
      break
    case 'message_delta':
      // 更新 usage 和 stop_reason
      break
  }
}
```

---

## 3. 任务拆解策略

### 3.1 自动任务拆解

Claude Code 不使用显式的任务拆解算法，而是依赖 LLM 的自然推理能力：

1. **工具调用作为任务原子化**
   - 每个工具调用代表一个原子操作
   - 通过 `tool_use` 和 `tool_result` 循环推进任务

2. **上下文引导**
   - 系统提示词中包含任务处理指导
   - 通过 `getSystemPromptParts()` 获取

### 3.2 工具执行编排

**工具执行服务 (`services/tools/toolOrchestration.ts`):**

```typescript
const toolUpdates = streamingToolExecutor
  ? streamingToolExecutor.getRemainingResults()
  : runTools(toolUseBlocks, assistantMessages, canUseTool, toolUseContext)
```

**关键特性：**
- **流式执行**: `StreamingToolExecutor` 允许在 LLM 流式响应时并行执行工具
- **权限管理**: 通过 `canUseTool` 函数检查每个工具调用的权限
- **结果聚合**: 工具结果作为 `tool_result` 块返回给 LLM

### 3.3 任务摘要生成

```typescript
// query.ts:1411-1482
if (config.gates.emitToolUseSummaries && toolUseBlocks.length > 0) {
  nextPendingToolUseSummary = generateToolUseSummary({
    tools: toolInfoForSummary,
    signal: toolUseContext.abortController.signal,
    isNonInteractiveSession: toolUseContext.options.isNonInteractiveSession,
    lastAssistantText,
  })
}
```

任务摘要使用 Haiku 模型异步生成，在下一轮查询前完成。

---

## 4. 决策路径动态调整机制

### 4.1 重试机制

**withRetry 包装器 (services/api/withRetry.ts):**

```typescript
export async function* withRetry<T>(
  getClient: () => Promise<Client>,
  fn: (client: Client, attempt: number, context: RetryContext) => AsyncGenerator<T>,
  options: RetryOptions
): AsyncGenerator<T>
```

**重试条件：**
- 5xx 错误（服务器过载）
- 网络错误
- 认证错误（触发模式切换）

### 4.2 回退模式

**流式 → 非流式回退 (claude.ts:2403-2650):**

```typescript
if (!didFallBackToNonStreaming) {
  const result = yield* executeNonStreamingRequest(...)
  fallbackMessage = m
  yield m
}
```

**模型回退 (claude.ts:894-951):**

```typescript
if (error instanceof FallbackTriggeredError && fallbackModel) {
  currentModel = fallbackModel
  attemptWithFallback = true
  yield* yieldMissingToolResultBlocks(assistantMessages, 'Model fallback triggered')
}
```

### 4.3 错误恢复路径

```
┌──────────────────────────────────────────────────────────────┐
│                      错误恢复机制                            │
│                                                               │
│  ┌────────────┐    ┌──────────────┐    ┌─────────────────┐  │
│  │ Max Output │ → │ Escalate     │ → │ Recovery Message │  │
│  │ Tokens     │    │ (64k)         │    │ (continue work)  │  │
│  └────────────┘    └──────────────┘    └─────────────────┘  │
│                                                               │
│  ┌────────────┐    ┌──────────┐    ┌─────────────────┐  │
│  │ Prompt Too │ → │ Collapse │ → │ Reactive Compact │  │
│  │ Long       │    │ Drain    │    │ (summarize)     │  │
│  └────────────┘    └──────────┘    └─────────────────┘  │
│                                                               │
│  ┌────────────┐    ┌──────────┐                              │
│  │ API Error  │ → │ Non-Stream│                              │
│  │            │    │ Fallback │                              │
│  └────────────┘    └──────────┘                              │
└──────────────────────────────────────────────────────────────┘
```

### 4.4 Max Output Tokens 恢复

```typescript
// query.ts:1188-1252
if (isWithheldMaxOutputTokens(lastMessage)) {
  // 升级到64k token限制
  if (capEnabled && maxOutputTokensOverride === undefined) {
    state = {
      ...state,
      maxOutputTokensOverride: ESCALATED_MAX_TOKENS,
      transition: { reason: 'max_output_tokens_escalate' },
    }
    continue
  }
  
  // 多轮恢复
  if (maxOutputTokensRecoveryCount < MAX_OUTPUT_TOKENS_RECOVERY_LIMIT) {
    const recoveryMessage = createUserMessage({
      content: `Output token limit hit. Resume directly — no apology...`,
      isMeta: true,
    })
    // 添加恢复消息并继续
  }
}
```

---

## 5. Plan Mode 实现原理

### 5.1 Plan Mode 激活

`commands/plan/plan.tsx:64-92`:

```typescript
if (currentMode !== 'plan') {
  handlePlanModeTransition(currentMode, 'plan')
  setAppState(prev => ({
    ...prev,
    toolPermissionContext: applyPermissionUpdate(
      prepareContextForPlanMode(prev.toolPermissionContext),
      { type: 'setMode', mode: 'plan', destination: 'session' }
    )
  }))
}
```

### 5.2 Plan Mode 特性

1. **权限模式变更**: 从默认模式切换到 `plan` 模式
2. **上下文准备**: `prepareContextForPlanMode()` 准备 Plan 特定的上下文
3. **持久化**: Plan 状态持久化到 session

### 5.3 Plan 内容管理

```typescript
// utils/plans.ts
export function getPlan(): string | null {
  // 从计划文件读取计划内容
}

export function getPlanFilePath(): string {
  // 返回计划文件路径
}
```

### 5.4 Plan 交互流程

```
用户输入 /plan
    ↓
检查当前模式
    ↓
[非 Plan Mode] → 切换到 Plan Mode → 准备上下文
    ↓
[已为 Plan Mode] → 读取并显示计划
    ↓
[open 参数] → 在编辑器中打开计划文件
```

---

## 6. Ultra Planning 机制

### 6.1 Ultra Planning 入口

`commands/ultraplan.tsx:234-293` 中的 `launchUltraplan()` 函数：

```typescript
export async function launchUltraplan(opts: {
  blurb: string
  seedPlan?: string
  getAppState: () => AppState
  setAppState: (f: (prev: AppState) => AppState) => void
  signal: AbortSignal
  ...
}): Promise<string>
```

### 6.2 Ultra Planning 流程

```
┌─────────────────────────────────────────────────────────────┐
│                    Ultra Planning 流程                        │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 1. 关键词检测 (keyword.ts)                             │  │
│  │    - 跳过引号/路径中的 "ultraplan"                    │  │
│  │    - 替换为 "plan" 以保持语法正确                   │  │
│  └──────────────────────────────────────────────────────┘  │
│         ↓                                                      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 2. 远程会话创建 (teleportToRemote)                   │  │
│  │    - 构建 ultraplan 提示词                             │  │
│  │    - 设置 permissionMode='plan'                       │  │
│  │    - 使用 Opus 模型                                    │  │
│  └──────────────────────────────────────────────────────┘  │
│         ↓                                                      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 3. 异步轮询 (ccrSession.ts)                           │  │
│  │    - ExitPlanModeScanner 扫描事件流                │  │
│  │    - 状态: running → needs_input → plan_ready        │  │
│  └──────────────────────────────────────────────────────┘  │
│         ↓                                                      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 4. 用户决策                                           │  │
│  │    - approved (在 CCR 执行)                          │  │
│  │    - teleport (传送回本地执行)                      │  │
│  │    - rejected (继续等待)                              │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 6.3 ExitPlanModeScanner 状态机

`utils/ultraplan/ccrSession.ts:80-181`:

```typescript
export class ExitPlanModeScanner {
  ingest(newEvents: SDKMessage[]): ScanResult {
    for (const m of newEvents) {
      if (m.type === 'assistant') {
        // 扫描 ExitPlanMode tool_use
      } else if (m.type === 'user') {
        // 记录 tool_result
      } else if (m.type === 'result' && m.subtype !== 'success') {
        // 检查会话终止
      }
    }
    
    return {
      kind: 'approved' | 'teleport' | 'rejected' | 'pending' | 'terminated' | 'unchanged'
    }
  }
}
```

### 6.4 Ultra Planning 提示词

`commands/ultraplan.tsx:63-73`:

```typescript
export function buildUltraplanPrompt(blurb: string, seedPlan?: string): string {
  const parts: string[] = []
  if (seedPlan) {
    parts.push('Here is a draft plan to refine:', '', seedPlan, '')
  }
  parts.push(ULTRAPLAN_INSTRUCTIONS)
  if (blurb) {
    parts.push('', blurb)
  }
  return parts.join('\n')
}
```

---

## 7. Harness Engineering 评价

### 7.1 优点

1. **模块化设计**
   - 清晰的关注点分离：QueryEngine、query、queryModel 各司其职
   - 可插拔的工具系统：`Tools` 类型定义良好的接口

2. **错误恢复机制完善**
   - 多层回退策略：流式→非流式、主模型→回退模型
   - 细粒度的错误分类和处理

3. **性能优化**
   - 提示词缓存减少 API 调用成本
   - 异步任务摘要不阻塞主流程
   - 流式工具执行提高响应速度

4. **可扩展性**
   - Beta 特性门控机制支持实验性功能
   - 插件系统允许扩展新功能

### 7.2 缺陷

1. **复杂的状态管理**
   - `queryLoop` 中的 `State` 类型包含 9 个字段
   - 状态转换逻辑分散在多处，难以追踪

2. **隐藏的控制流**
   - 通过 `yield*` 实现的异步控制流不够直观
   - Continue 机制隐式传递状态

3. **过度依赖 LLM 推理**
   - 没有显式的任务拆解表示
   - 任务进度跟踪依赖 LLM 的"记忆"

4. **错误处理的不一致性**
   - 某些错误通过 yield 返回，某些通过 throw
   - `isWithheldMaxOutputTokens` 等机制增加了理解难度

### 7.3 改进建议

1. **显式任务状态机**
   ```typescript
   enum TaskState {
     PLANNING, EXECUTING, WAITING_INPUT, COMPLETED, FAILED
   }
   ```

2. **统一的错误处理策略**
   - 所有错误通过统一通道报告
   - 避免 withholding 后再 yield 的两阶段模式

3. **更清晰的决策路径记录**
   - 在消息中添加 `transition_reason` 字段
   - 支持事后审计和调试

4. **Plan Mode 增强**
   - 支持计划的版本控制
   - 允许计划的渐进式完善

---

## 8. 关键代码位置索引

| 组件 | 文件路径 | 关键行号 |
|------|---------|---------|
| QueryEngine | src/QueryEngine.ts | 209-1156 |
| Query Loop | src/query.ts | 241-1729 |
| LLM API 调用 | src/services/api/claude.ts | 1017-2892 |
| Plan Mode | src/commands/plan/plan.tsx | 64-121 |
| Ultra Planning | src/commands/ultraplan.tsx | 234-410 |
| Ultra Planning Polling | src/utils/ultraplan/ccrSession.ts | 198-306 |
| 用户输入处理 | src/utils/processUserInput/processUserInput.ts | 85-270 |
| Brief Mode | src/commands/brief.ts | 全文 |
| Advisor | src/commands/advisor.ts | 全文 |

---

## 9. 总结

Claude Code 的任务规划和推理机制采用了**LLM 驱动的隐式任务管理**方式，而不是传统的显式任务分解和状态机。这种设计充分利用了 Claude 模型的推理能力，但也带来了控制流不够直观的问题。

主要特点：
- **流式处理**: 整个查询过程是流式的，支持实时响应
- **多层恢复**: 丰富的错误恢复和回退机制
- **动态调整**: 根据运行时状态动态调整策略
- **模式切换**: 支持 Plan Mode 和 Ultra Planning 等特殊模式

从 Harness Engineering 角度评价，该系统具有良好的可扩展性和容错性，但在可维护性和可调试性方面存在改进空间。
