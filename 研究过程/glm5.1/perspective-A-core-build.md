# 视角A: Claude Code 核心构建分析 (The Core Build)

## 1. Agent 核心类继承体系

### 1.1 任务基类架构 (Task.ts)

Claude Code 的核心是一个基于任务的执行框架，所有 Agent 相关类型都继承自 `Task.ts` 中定义的基础接口：

```typescript
// src/Task.ts (lines 72-77)
export type Task = {
  name: string
  type: TaskType
  kill(taskId: string, setAppState: SetAppState): Promise<void>
}
```

**核心设计特点：**
- **统一接口**：所有任务类型实现相同的 `kill` 方法
- **类型标识**：通过 `type: TaskType` 区分不同的任务类型
- **状态管理**：通过 `setAppState` 统一更新任务状态

### 1.2 任务类型层次结构

```
Task (interface)
├── LocalShellTask (本地Bash任务)
├── LocalAgentTask (本地后台Agent)
├── RemoteAgentTask (远程Agent)
├── InProcessTeammateTask (进程内队友)
├── LocalWorkflowTask (本地工作流)
├── MonitorMcpTask (MCP监控任务)
└── DreamTask (Dream任务)
```

每种任务类型都有对应的状态类型：
```typescript
export type TaskState =
  | LocalShellTaskState
  | LocalAgentTaskState
  | RemoteAgentTaskState
  | InProcessTeammateTaskState
  | LocalWorkflowTaskState
  | MonitorMcpTaskState
  | DreamTaskState
```

### 1.3 任务状态基类 (TaskStateBase)

```typescript
// src/Task.ts (lines 44-57)
export type TaskStateBase = {
  id: string
  type: TaskType
  status: TaskStatus
  description: string
  toolUseId?: string
  startTime: number
  endTime?: number
  totalPausedMs?: number
  outputFile: string
  outputOffset: number
  notified: boolean
}
```

**关键状态字段解析：**
- `status`: 任务生命周期状态（pending/running/completed/failed/killed）
- `outputFile`: 任务输出文件路径（用于磁盘持久化）
- `notified`: 是否已通知用户（防止重复通知）
- `totalPausedMs`: 总暂停时间（用于性能统计）

## 2. 状态管理架构

### 2.1 全局状态 (bootstrap/state.ts)

Claude Code 使用一个单例全局状态对象：

```typescript
// src/bootstrap/state.ts (lines 429, 258-427)
const STATE: State = getInitialState()

function getInitialState(): State {
  return {
    sessionId: randomUUID(),
    startTime: Date.now(),
    cwd: resolvedCwd,
    projectRoot: resolvedCwd,
    totalCostUSD: 0,
    // ... 100+ 其他字段
  }
}
```

**设计模式：**
- **单例模式**：整个应用共享一个全局 STATE 对象
- **不可变更新**：通过专用 setter 函数更新状态（如 `setCwdState()`）
- **功能开关**：通过 `feature()` 宏控制特性可用性

### 2.2 应用状态 (AppState + AppStateStore)

React 组件使用的是基于 createStore 的状态管理：

```typescript
// src/state/store.ts (lines 10-34)
export function createStore<T>(
  initialState: T,
  onChange?: OnChange<T>,
): Store<T> {
  let state = initialState
  const listeners = new Set<Listener>()

  return {
    getState: () => state,
    setState: (updater: (prev: T) => T) => {
      const prev = state
      const next = updater(prev)
      if (Object.is(next, prev)) return
      state = next
      onChange?.({ newState: next, oldState: prev })
      for (const listener of listeners) listener()
    },
    subscribe: (listener: Listener) => { ... }
  }
}
```

**状态管理模式：**
- **观察者模式**：通过 `listeners` Set 实现订阅机制
- **不可变更新**：setState 要求返回新对象（浅比较）
- **React 集成**：通过 `useSyncExternalStore` 集成到 React

## 3. Agent 完整生命周期

### 3.1 生命周期状态机

```
pending → running → [completed | failed | killed]
```

**状态转换规则：**
```typescript
// src/Task.ts (lines 27-29)
export function isTerminalTaskStatus(status: TaskStatus): boolean {
  return status === 'completed' || status === 'failed' || status === 'killed'
}
```

终端状态用于：
- 防止向已死任务发送消息
- 清理 AppState 中的任务
- 孤儿清理路径

### 3.2 InProcessTeammate 完整生命周期 (inProcessRunner.ts)

进程内队友的生命周期是完整的 Agent 执行流程的代表：

```typescript
// src/utils/swarm/inProcessRunner.ts (lines 883-1534)
export async function runInProcessTeammate(
  config: InProcessRunnerConfig,
): Promise<InProcessRunnerResult> {
  // 阶段1: 初始化 (lines 906-1020)
  const agentContext: AgentContext = { ... }
  const teammateSystemPrompt = await getSystemPrompt(...)
  const resolvedAgentDefinition: CustomAgentDefinition = { ... }

  // 阶段2: 主循环 (lines 1047-1417)
  while (!abortController.signal.aborted && !shouldExit) {
    // 2.1 创建 per-turn abort controller
    const currentWorkAbortController = createAbortController()

    // 2.2 检查是否需要压缩上下文
    if (tokenCount > getAutoCompactThreshold(...)) {
      const compactedSummary = await compactConversation(...)
      contextMessages = buildPostCompactMessages(compactedSummary)
    }

    // 2.3 执行 Agent 循环
    await runWithTeammateContext(teammateContext, async () => {
      return runWithAgentContext(agentContext, async () => {
        for await (const message of runAgent({
          agentDefinition: iterationAgentDefinition,
          promptMessages,
          toolUseContext,
          canUseTool: createInProcessCanUseTool(...),
          // ...
        })) {
          iterationMessages.push(message)
          allMessages.push(message)
          updateProgressFromMessage(tracker, message, ...)
        }
      })
    })

    // 2.4 标记为空闲状态
    updateTaskState(taskId, task => ({
      ...task,
      isIdle: true,
      onIdleCallbacks: []
    }), setAppState)

    // 2.5 发送空闲通知
    await sendIdleNotification(...)

    // 2.6 等待下一个提示或关闭请求
    const waitResult = await waitForNextPromptOrShutdown(...)
    switch (waitResult.type) {
      case 'shutdown_request':
        // 传递给模型决策
        currentPrompt = formatAsTeammateMessage(...)
        break
      case 'new_message':
        // 新消息处理
        currentPrompt = waitResult.message
        break
      case 'aborted':
        shouldExit = true
        break
    }
  }

  // 阶段3: 清理 (lines 1419-1461)
  updateTaskState(taskId, task => ({
    ...task,
    status: 'completed',
    notified: true,
    endTime: Date.now(),
    messages: task.messages?.length ? [task.messages.at(-1)!] : undefined,
    // ...
  }), setAppState)
}
```

### 3.3 生命周期关键设计模式

**1. AsyncLocalStorage 上下文隔离**
```typescript
// 进程内队友使用 AsyncLocalStorage 实现上下文隔离
await runWithTeammateContext(teammateContext, async () => {
  return runWithAgentContext(agentContext, async () => {
    // Agent 执行代码
  })
})
```

**2. 双层 AbortController**
- `lifecycle abortController`: 控制整个队友生命周期
- `currentWorkAbortController`: 控制单次工作（允许 Escape 停止当前工作但不杀死队友）

**3. 消息累积与压缩**
- `allMessages`: 累积所有对话历史
- 自动压缩：当 token 数超过阈值时调用 `compactConversation()`
- 增量更新：通过 `appendCappedMessage` 限制消息数量

## 4. Coordinator 协调机制

### 4.1 Coordinator 模式

Coordinator 模式是一种特殊的 Agent 运行模式，通过环境变量启用：

```typescript
// src/coordinator/coordinatorMode.ts (lines 36-41)
export function isCoordinatorMode(): boolean {
  if (feature('COORDINATOR_MODE')) {
    return isEnvTruthy(process.env.CLAUDE_CODE_COORDINATOR_MODE)
  }
  return false
}
```

### 4.2 Coordinator 系统提示

Coordinator 模式下，系统提示被替换为协调器专用提示：

```typescript
// src/coordinator/coordinatorMode.ts (lines 111-369)
export function getCoordinatorSystemPrompt(): string {
  return `You are Claude Code, an AI assistant that orchestrates software engineering tasks across multiple workers.

## 1. Your Role
You are a **coordinator**. Your job is to:
- Help the user achieve their goal
- Direct workers to research, implement and verify code changes
- Synthesize results and communicate with the user
// ...
```

**Coordinator 的核心特点：**
- **并行编排**：强调通过并行工具调用启动多个 workers
- **结果综合**：要求 coordinator 理解研究发现后自己综合
- **避免懒惰委托**：明确禁止 "based on your findings" 类提示

### 4.3 Worker 工具限制

Coordinator 模式下 workers 的工具访问受限：

```typescript
// src/coordinator/coordinatorMode.ts (lines 81-108)
export function getCoordinatorUserContext(...): { [k: string]: string } {
  const workerTools = isEnvTruthy(process.env.CLAUDE_CODE_SIMPLE)
    ? [BASH_TOOL_NAME, FILE_READ_TOOL_NAME, FILE_EDIT_TOOL_NAME].sort().join(', ')
    : Array.from(ASYNC_AGENT_ALLOWED_TOOLS)
        .filter(name => !INTERNAL_WORKER_TOOLS.has(name))
        .sort().join(', ')

  let content = `Workers spawned via the ${AGENT_TOOL_NAME} tool have access to these tools: ${workerTools}`
  // ...
}
```

**内部工具列表：**
```typescript
// src/coordinator/coordinatorMode.ts (lines 29-34)
const INTERNAL_WORKER_TOOLS = new Set([
  TEAM_CREATE_TOOL_NAME,
  TEAM_DELETE_TOOL_NAME,
  SEND_MESSAGE_TOOL_NAME,
  SYNTHETIC_OUTPUT_TOOL_NAME,
])
```

## 5. Swarm 编排机制

### 5.1 队友创建 (spawnInProcess.ts)

Swarm 的基础是队友创建机制：

```typescript
// src/utils/swarm/spawnInProcess.ts (lines 104-216)
export async function spawnInProcessTeammate(
  config: InProcessSpawnConfig,
  context: SpawnContext,
): Promise<InProcessSpawnOutput> {
  const { name, teamName, prompt, color, planModeRequired, model } = config
  const { setAppState } = context

  // 1. 生成确定性 Agent ID
  const agentId = formatAgentId(name, teamName)
  const taskId = generateTaskId('in_process_teammate')

  // 2. 创建独立的 AbortController
  const abortController = createAbortController()

  // 3. 创建队友身份 (存储为纯数据)
  const identity: TeammateIdentity = {
    agentId,
    agentName: name,
    teamName,
    color,
    planModeRequired,
    parentSessionId: getSessionId(),
  }

  // 4. 创建队友上下文 (AsyncLocalStorage)
  const teammateContext = createTeammateContext({
    agentId,
    agentName: name,
    teamName,
    color,
    planModeRequired,
    parentSessionId,
    abortController,
  })

  // 5. 注册清理处理器
  const unregisterCleanup = registerCleanup(async () => {
    abortController.abort()
  })

  // 6. 创建任务状态
  const taskState: InProcessTeammateTaskState = {
    ...createTaskStateBase(taskId, 'in_process_teammate', description, ...),
    type: 'in_process_teammate',
    status: 'running',
    identity,
    prompt,
    model,
    abortController,
    // ...
  }

  // 7. 在 AppState 中注册任务
  registerTask(taskState, setAppState)

  return { success: true, agentId, taskId, abortController, teammateContext }
}
```

### 5.2 邮箱通信系统 (teammateMailbox.ts)

队友之间通过文件系统邮箱通信：

```typescript
// src/utils/swarm/teammateMailbox.ts (概念性引用)
// 写入邮箱
await writeToMailbox(recipient, {
  from,
  text,
  timestamp: new Date().toISOString(),
  color,
}, teamName)

// 读取邮箱
const allMessages = await readMailbox(agentName, teamName)
```

**通信消息类型：**
1. **普通消息**：队友之间的普通通信
2. **关闭请求**：leader 请求队友关闭
3. **权限响应**：权限决策结果

### 5.3 任务列表集成

队友可以与任务列表集成，自动认领任务：

```typescript
// src/utils/swarm/inProcessRunner.ts (lines 594-657)
function findAvailableTask(tasks: Task[]): Task | undefined {
  const unresolvedTaskIds = new Set(
    tasks.filter(t => t.status !== 'completed').map(t => t.id),
  )

  return tasks.find(task => {
    if (task.status !== 'pending') return false
    if (task.owner) return false
    return task.blockedBy.every(id => !unresolvedTaskIds.has(id))
  })
}

async function tryClaimNextTask(...): Promise<string | undefined> {
  const tasks = await listTasks(taskListId)
  const availableTask = findAvailableTask(tasks)

  if (!availableTask) return undefined

  const result = await claimTask(taskListId, availableTask.id, agentName)
  if (!result.success) return undefined

  await updateTask(taskListId, availableTask.id, { status: 'in_progress' })

  return formatTaskAsPrompt(availableTask)
}
```

## 6. Harness Engineering 评价

### 6.1 可扩展性 (Extensibility)

**优点：**
- **插件化任务类型**：通过实现 `Task` 接口轻松添加新任务类型
- **定义驱动**：通过 `TaskType` 和 `TaskState` 联合类型实现类型安全
- **后端抽象**：`LocalAgentTask` 可切换不同后端（进程/tmux/iTerm2）

**缺点：**
- **全局状态膨胀**：bootstrap/state.ts 的 STATE 对象包含 100+ 字段，扩展困难
- **隐式依赖**：许多功能隐式依赖全局状态，难以测试和重构

### 6.2 安全边界 (Safety Boundaries)

**优点：**
- **AbortController 层级控制**：双层 abort 允许精细控制生命周期
- **权限系统**：队友工具权限通过 `canUseTool` 函数集中控制
- **终端状态检查**：`isTerminalTaskStatus()` 防止向死任务发送消息

**安全机制：**
```typescript
// src/Task.ts (lines 27-29)
export function isTerminalTaskStatus(status: TaskStatus): boolean {
  return status === 'completed' || status === 'failed' || status === 'killed'
}
```

**潜在风险：**
- **邮箱文件竞争**：多进程通过文件系统通信可能存在竞争条件
- **状态不一致**：AppState 和磁盘状态可能不同步

### 6.3 可观察性 (Observability)

**优点：**
- **丰富的进度跟踪**：`AgentProgress` 包含工具使用、token 消耗等信息
- **Perfetto 集成**：支持性能追踪和层级可视化
- **Telemetry 支持**：完整的 OpenTelemetry 集成

**进度跟踪实现：**
```typescript
// src/tasks/LocalAgentTask/LocalAgentTask.ts (lines 40-104)
export type ProgressTracker = {
  toolUseCount: number
  latestInputTokens: number
  cumulativeOutputTokens: number
  recentActivities: ToolActivity[]
}

export function updateProgressFromMessage(
  tracker: ProgressTracker,
  message: Message,
  resolveActivityDescription?: ActivityDescriptionResolver,
  tools?: Tools
): void {
  if (message.type !== 'assistant') return

  const usage = message.message.usage
  tracker.latestInputTokens = usage.input_tokens + ...
  tracker.cumulativeOutputTokens += usage.output_tokens

  for (const content of message.message.content) {
    if (content.type === 'tool_use') {
      tracker.toolUseCount++
      tracker.recentActivities.push({
        toolName: content.name,
        input,
        activityDescription: resolveActivityDescription?.(content.name, input),
        // ...
      })
    }
  }
}
```

### 6.4 性能损耗 (Performance Overhead)

**优化措施：**
1. **消息上限**：通过 `appendCappedMessage` 限制内存中的消息数量
2. **自动压缩**：超过 token 阈值时自动压缩对话历史
3. **增量更新**：状态更新使用浅比较和不可变更新

**性能瓶颈：**
- **全局状态读写**：所有状态更新都需要访问全局 STATE 对象
- **文件 I/O**：邮箱通信依赖文件系统读写
- **AsyncLocalStorage**：虽然隔离性好，但有额外开销

## 7. 关键代码片段引用

### 7.1 任务 ID 生成 (Task.ts:98-106)

```typescript
const TASK_ID_ALPHABET = '0123456789abcdefghijklmnopqrstuvwxyz'

export function generateTaskId(type: TaskType): string {
  const prefix = getTaskIdPrefix(type)
  const bytes = randomBytes(8)
  let id = prefix
  for (let i = 0; i < 8; i++) {
    id += TASK_ID_ALPHABET[bytes[i]! % TASK_ID_ALPHABET.length]
  }
  return id
}
```

### 7.2 队友权限检查 (inProcessRunner.ts:128-451)

```typescript
function createInProcessCanUseTool(
  identity: TeammateIdentity,
  abortController: AbortController,
  onPermissionWaitMs?: (waitMs: number) => void,
): CanUseToolFn {
  return async (tool, input, toolUseContext, ...) => {
    const result = await hasPermissionsToUseTool(...)

    if (result.behavior !== 'ask') {
      return result
    }

    // Bash 分类器自动审批
    if (feature('BASH_CLASSIFIER') && tool.name === BASH_TOOL_NAME && ...) {
      const classifierDecision = await awaitClassifierAutoApproval(...)
      if (classifierDecision) {
        return { behavior: 'allow', ... }
      }
    }

    // 使用 leader 的 ToolUseConfirm 对话框
    if (setToolUseConfirmQueue) {
      return new Promise<PermissionDecision>(resolve => {
        setToolUseConfirmQueue(queue => [
          ...queue,
          {
            assistantMessage,
            tool: tool as Tool,
            description,
            input,
            toolUseContext,
            toolUseID,
            permissionResult: result,
            workerBadge: identity.color ? { name: identity.agentName, color: identity.color } : undefined,
            onAllow(...) { resolve({ behavior: 'allow', ... }) },
            onReject(...) { resolve({ behavior: 'ask', message, ... }) },
            // ...
          },
        ])
      })
    }

    // 降级到邮箱系统
    return new Promise<PermissionDecision>(resolve => {
      const request = createPermissionRequest({ ... })
      registerPermissionCallback({ ... })
      void sendPermissionRequestViaMailbox(request)
      // ...
    })
  }
}
```

### 7.3 空闲等待循环 (inProcessRunner.ts:689-868)

```typescript
async function waitForNextPromptOrShutdown(
  identity: TeammateIdentity,
  abortController: AbortController,
  ...,
): Promise<WaitResult> {
  const POLL_INTERVAL_MS = 500

  while (!abortController.signal.aborted) {
    // 1. 检查内存中的待处理消息
    const appState = getAppState()
    const task = appState.tasks[taskId]
    if (task && task.type === 'in_process_teammate' && task.pendingUserMessages.length > 0) {
      const message = task.pendingUserMessages[0]!
      // 弹出消息队列
      return { type: 'new_message', message, from: 'user' }
    }

    // 2. 等待下次轮询
    if (pollCount > 0) {
      await sleep(POLL_INTERVAL_MS)
    }
    pollCount++

    // 3. 检查邮箱消息
    const allMessages = await readMailbox(identity.agentName, identity.teamName)

    // 4. 优先扫描关闭请求
    for (let i = 0; i < allMessages.length; i++) {
      const m = allMessages[i]
      if (m && !m.read) {
        const parsed = isShutdownRequest(m.text)
        if (parsed) {
          return { type: 'shutdown_request', request: parsed, originalMessage: m.text }
        }
      }
    }

    // 5. 检查任务列表
    const taskPrompt = await tryClaimNextTask(taskListId, identity.agentName)
    if (taskPrompt) {
      return { type: 'new_message', message: taskPrompt, from: 'task-list' }
    }
  }

  return { type: 'aborted' }
}
```

## 8. 总结

Claude Code 的核心构建展现了一个精心设计的 Agent 系统：

1. **类型安全**：充分利用 TypeScript 联合类型实现类型安全的任务系统
2. **状态管理**：全局状态 + React 状态的混合模式
3. **生命周期**：清晰的状态机设计和双层 Abort 控制
4. **协调机制**：Coordinator 模式实现多 Agent 编排
5. **Swarm 编排**：基于 AsyncLocalStorage 和邮箱通信的队友系统

从 Harness Engineering 视角，该系统在可扩展性和可观察性方面表现优秀，但全局状态的膨胀和文件系统通信的性能开销是潜在的改进点。
