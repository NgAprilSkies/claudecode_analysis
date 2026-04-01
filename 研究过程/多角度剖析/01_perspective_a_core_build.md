# 视角 A: 核心构建 (The Core Build)

## A.1 Agent 基本结构

### 核心类设计

Claude Code 的 Agent 架构围绕以下核心类构建：

#### 1. QueryEngine (src/QueryEngine.ts)
```typescript
export class QueryEngine {
  private config: QueryEngineConfig
  private mutableMessages: Message[]
  private abortController: AbortController
  private permissionDenials: SDKPermissionDenial[]
  private totalUsage: NonNullableUsage
  private readFileState: FileStateCache

  async *submitMessage(prompt, options): AsyncGenerator<SDKMessage>
  interrupt(): void
  getMessages(): readonly Message[]
}
```

**职责**: 管理对话生命周期，处理消息提交和流式响应

#### 2. Task 系统 (src/Task.ts, src/tasks.ts)
```typescript
type TaskType = 'local_bash' | 'local_agent' | 'remote_agent' |
                'in_process_teammate' | 'local_workflow' | 'monitor_mcp' | 'dream'

type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'killed'

interface TaskContext {
  abortController: AbortController
  getAppState: () => AppState
  setAppState: (f: (prev: AppState) => AppState) => void
}
```

#### 3. AppState (src/state/AppState.tsx)
```typescript
interface AppState {
  // 100+ 字段，包括:
  messages: Message[]
  toolPermissionContext: ToolPermissionContext
  mcp: MCPState
  fileHistory: FileHistoryState
  attribution: AttributionState
  fastMode: FastModeState
  // ... 更多状态字段
}
```

#### 4. Tool 接口 (src/Tool.ts)
```typescript
type Tool<Input, Output, Progress> = {
  name: string
  call(args, context, canUseTool, parentMessage, onProgress): Promise<ToolResult<Output>>
  description(input, options): Promise<string>
  inputSchema: Input
  outputSchema?: Output
  isConcurrencySafe(input): boolean
  isReadOnly(input): boolean
  checkPermissions(input, context): Promise<PermissionResult>
  // ... 更多方法
}
```

---

## A.2 Agent 完整生命周期

### 生命周期流程图

```svg
<svg viewBox="0 0 1200 800" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" fill="#333"/>
    </marker>
    <linearGradient id="grad1" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" style="stop-color:#4A90D9;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#0066CC;stop-opacity:1" />
    </linearGradient>
    <linearGradient id="grad2" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" style="stop-color:#5CB85C;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#449D44;stop-opacity:1" />
    </linearGradient>
    <linearGradient id="grad3" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" style="stop-color:#F0AD4E;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#EC971F;stop-opacity:1" />
    </linearGradient>
  </defs>

  <!-- Background -->
  <rect width="1200" height="800" fill="#f8f9fa"/>

  <!-- Title -->
  <text x="600" y="40" text-anchor="middle" font-size="24" font-weight="bold" fill="#333">
    Claude Code Agent 生命周期 (Lifecycle)
  </text>

  <!-- Phase 1: Initialization -->
  <g transform="translate(50, 80)">
    <rect x="0" y="0" width="1100" height="120" rx="10" fill="url(#grad1)" opacity="0.1" stroke="#4A90D9" stroke-width="2"/>
    <text x="550" y="30" text-anchor="middle" font-size="18" font-weight="bold" fill="#4A90D9">阶段 1: 初始化 (Initialization)</text>

    <!-- Init Steps -->
    <rect x="30" y="50" width="200" height="50" rx="5" fill="#4A90D9" stroke="#2E5C8A" stroke-width="2"/>
    <text x="130" y="80" text-anchor="middle" font-size="14" fill="white">QueryEngine 构造</text>

    <rect x="260" y="50" width="200" height="50" rx="5" fill="#4A90D9" stroke="#2E5C8A" stroke-width="2"/>
    <text x="360" y="75" text-anchor="middle" font-size="13" fill="white">加载系统上下文</text>
    <text x="360" y="92" text-anchor="middle" font-size="11" fill="white">(Git, CLAUDE.md)</text>

    <rect x="490" y="50" width="200" height="50" rx="5" fill="#4A90D9" stroke="#2E5C8A" stroke-width="2"/>
    <text x="590" y="75" text-anchor="middle" font-size="13" fill="white">构建工具池</text>
    <text x="590" y="92" text-anchor="middle" font-size="11" fill="white">(Built-in + MCP)</text>

    <rect x="720" y="50" width="200" height="50" rx="5" fill="#4A90D9" stroke="#2E5C8A" stroke-width="2"/>
    <text x="820" y="75" text-anchor="middle" font-size="13" fill="white">权限上下文</text>
    <text x="820" y="92" text-anchor="middle" font-size="11" fill="white">(PermissionMode)</text>

    <rect x="950" y="50" width="120" height="50" rx="5" fill="#4A90D9" stroke="#2E5C8A" stroke-width="2"/>
    <text x="1010" y="80" text-anchor="middle" font-size="14" fill="white">系统提示</text>

    <!-- Arrows -->
    <line x1="230" y1="75" x2="255" y2="75" stroke="#4A90D9" stroke-width="2" marker-end="url(#arrowhead)"/>
    <line x1="460" y1="75" x2="485" y2="75" stroke="#4A90D9" stroke-width="2" marker-end="url(#arrowhead)"/>
    <line x1="690" y1="75" x2="715" y2="75" stroke="#4A90D9" stroke-width="2" marker-end="url(#arrowhead)"/>
    <line x1="920" y1="75" x2="945" y2="75" stroke="#4A90D9" stroke-width="2" marker-end="url(#arrowhead)"/>
  </g>

  <!-- Phase 2: Query Loop -->
  <g transform="translate(50, 230)">
    <rect x="0" y="0" width="1100" height="280" rx="10" fill="url(#grad2)" opacity="0.1" stroke="#5CB85C" stroke-width="2"/>
    <text x="550" y="30" text-anchor="middle" font-size="18" font-weight="bold" fill="#5CB85C">阶段 2: 查询循环 (Query Loop)</text>

    <!-- Loop Steps -->
    <rect x="30" y="50" width="180" height="60" rx="5" fill="#5CB85C" stroke="#3D8B3D" stroke-width="2"/>
    <text x="120" y="75" text-anchor="middle" font-size="13" fill="white">处理用户输入</text>
    <text x="120" y="95" text-anchor="middle" font-size="11" fill="white">(processUserInput)</text>

    <line x1="210" y1="80" x2="235" y2="80" stroke="#5CB85C" stroke-width="2" marker-end="url(#arrowhead)"/>

    <rect x="240" y="50" width="180" height="60" rx="5" fill="#5CB85C" stroke="#3D8B3D" stroke-width="2"/>
    <text x="330" y="70" text-anchor="middle" font-size="13" fill="white">上下文管理</text>
    <text x="330" y="87" text-anchor="middle" font-size="10" fill="white">(Snip/Micro/Auto/</text>
    <text x="330" y="100" text-anchor="middle" font-size="10" fill="white">Collapse)</text>

    <line x1="420" y1="80" x2="445" y2="80" stroke="#5CB85C" stroke-width="2" marker-end="url(#arrowhead)"/>

    <rect x="450" y="50" width="180" height="60" rx="5" fill="#5CB85C" stroke="#3D8B3D" stroke-width="2"/>
    <text x="540" y="75" text-anchor="middle" font-size="13" fill="white">调用 LLM API</text>
    <text x="540" y="92" text-anchor="middle" font-size="11" fill="white">(streaming)</text>

    <line x1="630" y1="80" x2="655" y2="80" stroke="#5CB85C" stroke-width="2" marker-end="url(#arrowhead)"/>

    <rect x="660" y="50" width="180" height="60" rx="5" fill="#5CB85C" stroke="#3D8B3D" stroke-width="2"/>
    <text x="750" y="70" text-anchor="middle" font-size="13" fill="white">工具执行</text>
    <text x="750" y="87" text-anchor="middle" font-size="10" fill="white">(StreamingTool</text>
    <text x="750" y="100" text-anchor="middle" font-size="10" fill="white">Executor)</text>

    <line x1="840" y1="80" x2="865" y2="80" stroke="#5CB85C" stroke-width="2" marker-end="url(#arrowhead)"/>

    <rect x="870" y="50" width="180" height="60" rx="5" fill="#5CB85C" stroke="#3D8B3D" stroke-width="2"/>
    <text x="960" y="75" text-anchor="middle" font-size="13" fill="white">Stop Hooks</text>
    <text x="960" y="92" text-anchor="middle" font-size="11" fill="white">(后置评估)</text>

    <!-- Decision Diamond -->
    <polygon points="550,160 600,190 550,220 500,190" fill="#F0AD4E" stroke="#EC971F" stroke-width="2"/>
    <text x="550" y="195" text-anchor="middle" font-size="12" fill="white">需要</text>
    <text x="550" y="210" text-anchor="middle" font-size="12" fill="white">继续？</text>

    <!-- Loop back arrow -->
    <path d="M 500,190 L 200,190 L 200,110 L 235,110" fill="none" stroke="#5CB85C" stroke-width="2" marker-end="url(#arrowhead)"/>
    <text x="350" y="105" font-size="11" fill="#5CB85C" font-weight="bold">是 (needsFollowUp)</text>

    <!-- Exit arrow -->
    <line x1="550" y1="220" x2="550" y2="260" stroke="#5CB85C" stroke-width="2" marker-end="url(#arrowhead)"/>
    <text x="570" y="245" font-size="11" fill="#5CB85C" font-weight="bold">否</text>

    <!-- Sub-steps box -->
    <rect x="30" y="140" width="400" height="50" rx="5" fill="#E8F5E9" stroke="#5CB85C" stroke-width="1" stroke-dasharray="5,5"/>
    <text x="230" y="160" text-anchor="middle" font-size="12" fill="#333">每次迭代状态更新:</text>
    <text x="230" y="178" text-anchor="middle" font-size="11" fill="#666">messages | toolUseContext | turnCount | tracking</text>
  </g>

  <!-- Phase 3: Termination -->
  <g transform="translate(50, 540)">
    <rect x="0" y="0" width="1100" height="180" rx="10" fill="url(#grad3)" opacity="0.1" stroke="#F0AD4E" stroke-width="2"/>
    <text x="550" y="30" text-anchor="middle" font-size="18" font-weight="bold" fill="#F0AD4E">阶段 3: 终止 (Termination)</text>

    <!-- Termination Reasons -->
    <rect x="50" y="60" width="200" height="90" rx="5" fill="#F0AD4E" stroke="#C49A3A" stroke-width="2"/>
    <text x="150" y="90" text-anchor="middle" font-size="14" fill="white" font-weight="bold">正常完成</text>
    <text x="150" y="115" text-anchor="middle" font-size="11" fill="white">• completed</text>
    <text x="150" y="135" text-anchor="middle" font-size="11" fill="white">• end_turn</text>

    <rect x="280" y="60" width="200" height="90" rx="5" fill="#D9534F" stroke="#C9302C" stroke-width="2"/>
    <text x="380" y="90" text-anchor="middle" font-size="14" fill="white" font-weight="bold">错误终止</text>
    <text x="380" y="115" text-anchor="middle" font-size="11" fill="white">• max_turns_reached</text>
    <text x="380" y="135" text-anchor="middle" font-size="11" fill="white">• prompt_too_long</text>

    <rect x="510" y="60" width="200" height="90" rx="5" fill="#D9534F" stroke="#C9302C" stroke-width="2"/>
    <text x="610" y="90" text-anchor="middle" font-size="14" fill="white" font-weight="bold">用户中断</text>
    <text x="610" y="115" text-anchor="middle" font-size="11" fill="white">• aborted_streaming</text>
    <text x="610" y="135" text-anchor="middle" font-size="11" fill="white">• aborted_tools</text>

    <rect x="740" y="60" width="200" height="90" rx="5" fill="#F0AD4E" stroke="#C49A3A" stroke-width="2"/>
    <text x="840" y="90" text-anchor="middle" font-size="14" fill="white" font-weight="bold">预算耗尽</text>
    <text x="840" y="115" text-anchor="middle" font-size="11" fill="white">• max_budget_usd</text>
    <text x="840" y="135" text-anchor="middle" font-size="11" fill="white">• token_budget</text>

    <!-- Final Step -->
    <rect x="450" y="170" width="200" height="50" rx="5" fill="#6f42c1" stroke="#5a32a3" stroke-width="2"/>
    <text x="550" y="200" text-anchor="middle" font-size="14" fill="white">记录会话 (Transcript)</text>
  </g>

  <!-- State Carriers -->
  <g transform="translate(50, 740)">
    <text x="0" y="20" font-size="12" fill="#666" font-weight="bold">跨迭代状态载体 (State between iterations):</text>
    <rect x="280" y="5" width="120" height="25" rx="3" fill="#e9ecef" stroke="#6c757d" stroke-width="1"/>
    <text x="340" y="22" text-anchor="middle" font-size="10" fill="#333">messages</text>
    <rect x="410" y="5" width="120" height="25" rx="3" fill="#e9ecef" stroke="#6c757d" stroke-width="1"/>
    <text x="470" y="22" text-anchor="middle" font-size="10" fill="#333">toolUseContext</text>
    <rect x="540" y="5" width="120" height="25" rx="3" fill="#e9ecef" stroke="#6c757d" stroke-width="1"/>
    <text x="600" y="22" text-anchor="middle" font-size="10" fill="#333">autoCompactTracking</text>
    <rect x="670" y="5" width="120" height="25" rx="3" fill="#e9ecef" stroke="#6c757d" stroke-width="1"/>
    <text x="730" y="22" text-anchor="middle" font-size="10" fill="#333">turnCount</text>
    <rect x="800" y="5" width="120" height="25" rx="3" fill="#e9ecef" stroke="#6c757d" stroke-width="1"/>
    <text x="860" y="22" text-anchor="middle" font-size="10" fill="#333">transition</text>
  </g>
</svg>
```

### 生命周期关键代码位置

| 阶段 | 文件 | 函数/类 | 行号范围 |
|------|------|--------|----------|
| 初始化 | QueryEngine.ts | `constructor()` | 200-207 |
| 初始化 | query.ts | `query()` | 219-239 |
| 循环主体 | query.ts | `queryLoop()` | 241-1729 |
| 上下文管理 | query.ts | 400-548 (Snip/Micro/Auto/Collapse) |
| 工具执行 | query.ts | 1363-1410 |
| 终止处理 | QueryEngine.ts | `submitMessage()` result handling | 1082-1156 |

---

## A.3 Harness Engineering 设计决策评价

### 可扩展性 (Scalability) - 8/10

**优点**:
- 模块化设计：QueryEngine 与 query() 分离，职责清晰
- 工具系统可扩展：`buildTool()` 工厂模式便于添加新工具
- Feature flags 支持：`feature('FLAG_NAME')` 实现渐进式发布

**缺点**:
- 状态碎片化：`State` 对象在 queryLoop 中携带，增加了追踪复杂度
- 循环复杂性：queryLoop 超过 1400 行，包含 7 个 continue 站点

**代码证据**:
```typescript
// query.ts:268-279 - 状态载体设计
let state: State = {
  messages: params.messages,
  toolUseContext: params.toolUseContext,
  maxOutputTokensOverride: params.maxOutputTokensOverride,
  autoCompactTracking: undefined,
  stopHookActive: undefined,
  maxOutputTokensRecoveryCount: 0,
  hasAttemptedReactiveCompact: false,
  turnCount: 1,
  pendingToolUseSummary: undefined,
  transition: undefined,
}
```

---

### 安全边界 (Safety Boundary) - 9/10

**优点**:
- 多层权限系统：`PermissionMode` (default/auto/bypass/plan)
- 工具隔离：`isConcurrencySafe()`, `isReadOnly()`, `isDestructive()`
- 中断处理：`abortController` 贯穿整个生命周期

**代码证据**:
```typescript
// Tool.ts:123-138 - 权限上下文
export type ToolPermissionContext = DeepImmutable<{
  mode: PermissionMode
  alwaysAllowRules: ToolPermissionRulesBySource
  alwaysDenyRules: ToolPermissionRulesBySource
  alwaysAskRules: ToolPermissionRulesBySource
  shouldAvoidPermissionPrompts?: boolean
  // ...
}>
```

---

### 可观察性 (Observability) - 7/10

**优点**:
- 事件日志：`logEvent()` 用于分析追踪
- 性能分析：`queryCheckpoint()` 和 `headlessProfilerCheckpoint()`
- 错误追踪：`logError()` 和内存错误缓冲区

**缺点**:
- 日志分散：调试日志分布在多个模块中
- 状态快照有限：难以重现特定时刻的完整状态

**代码证据**:
```typescript
// query.ts:357-358 - 分析元数据
const queryChainIdForAnalytics =
  queryTracking.chainId as AnalyticsMetadata_I_VERIFIED_THIS_IS_NOT_CODE_OR_FILEPATHS
```

---

### 性能损耗 (Performance Overhead) - 7/10

**优点**:
- 记忆化优化：`memoize()` 用于系统/用户上下文
- 文件状态缓存：`FileStateCache` LRU 缓存
- 懒加载：工具池按需过滤

**缺点**:
- 上下文管理开销：每次迭代都要执行 Snip/Micro/Auto/Collapse 检查
- 消息序列化：`recordTranscript()` 异步但可能阻塞

**代码证据**:
```typescript
// context.ts:36-111 - Git 状态记忆化
export const getGitStatus = memoize(async (): Promise<string | null> => {
  // Git 状态计算只执行一次
})

// context.ts:116-150 - 系统上下文记忆化
export const getSystemContext = memoize(async () => {
  // 会话期间缓存
})
```

---

## A.4 最小化实现 (MRE) - Python

```python
"""
Agent Core Build - Minimal Reference Implementation
视角 A: 核心构建最小化实现 (约 80 行)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from enum import Enum
import uuid


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


@dataclass
class Message:
    """消息类型 - 对话基本单元"""
    type: str  # 'user', 'assistant', 'system'
    content: Any
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class ToolResult:
    """工具执行结果"""
    data: Any
    new_messages: List[Message] = field(default_factory=list)


@dataclass
class ToolContext:
    """工具执行上下文"""
    abort_controller: Any  # 用于中断
    messages: List[Message]
    get_state: Callable[[], Dict]
    set_state: Callable[[Dict], None]


class Tool:
    """工具基类"""
    name: str = "base_tool"

    def call(self, args: Dict, context: ToolContext) -> ToolResult:
        raise NotImplementedError

    def check_permissions(self, args: Dict, context: ToolContext) -> bool:
        return True

    def is_concurrency_safe(self, args: Dict) -> bool:
        return False


class QueryEngine:
    """查询引擎 - Agent 核心"""

    def __init__(
        self,
        tools: List[Tool],
        can_use_tool: Callable[[Tool, Dict], bool],
        get_state: Callable[[], Dict],
        set_state: Callable[[Dict], None],
    ):
        self.config = {
            'tools': tools,
            'can_use_tool': can_use_tool,
            'get_state': get_state,
            'set_state': set_state,
        }
        self.messages: List[Message] = []
        self.abort_controller = None
        self.usage = {'input': 0, 'output': 0}

    async def submit_message(self, prompt: str) -> Any:
        """提交消息并流式返回结果"""
        # 1. 添加用户消息
        user_msg = Message(type='user', content=prompt)
        self.messages.append(user_msg)

        # 2. 执行查询循环
        async for message in self._query_loop():
            yield message

        # 3. 返回最终结果
        return self._build_result()

    async def _query_loop(self):
        """核心查询循环"""
        turn_count = 0
        max_turns = 10

        while turn_count < max_turns:
            turn_count += 1

            # 调用 LLM (模拟)
            assistant_msg = await self._call_llm()
            yield assistant_msg

            # 检查是否需要工具执行
            if self._needs_tool_use(assistant_msg):
                tool_messages = await self._execute_tools(assistant_msg)
                for msg in tool_messages:
                    yield msg
                self.messages.extend(tool_messages)
            else:
                # 无需工具，完成
                break

        self.messages.append(assistant_msg)

    async def _call_llm(self) -> Message:
        """调用 LLM API (模拟)"""
        # 实际实现会调用 Claude API
        return Message(type='assistant', content='Response')

    def _needs_tool_use(self, message: Message) -> bool:
        """检查是否需要工具执行"""
        return False  # 简化实现

    async def _execute_tools(self, message: Message) -> List[Message]:
        """执行工具调用"""
        results = []
        for tool in self.config['tools']:
            if self.config['can_use_tool'](tool, {}):
                result = tool.call({}, ToolContext(
                    abort_controller=self.abort_controller,
                    messages=self.messages,
                    get_state=self.config['get_state'],
                    set_state=self.config['set_state'],
                ))
                results.extend(result.new_messages)
        return results

    def _build_result(self) -> Dict:
        """构建最终结果"""
        return {
            'messages': self.messages,
            'usage': self.usage,
            'status': 'completed',
        }

    def interrupt(self):
        """中断当前执行"""
        if self.abort_controller:
            self.abort_controller.abort()


# 使用示例
async def main():
    # 定义简单工具
    class ReadTool(Tool):
        name = "Read"
        def call(self, args, context) -> ToolResult:
            return ToolResult(data="file content")

    # 创建引擎
    engine = QueryEngine(
        tools=[ReadTool()],
        can_use_tool=lambda t, a: True,
        get_state=lambda: {},
        set_state=lambda s: None,
    )

    # 执行
    async for msg in engine.submit_message("读取文件"):
        print(f"收到消息：{msg.type}")
```

---

## A.5 挑战性思考问题

### 问题 A: 状态管理与内存泄漏

**场景**: 在长运行会话中（如持续数小时的 Agent 任务），`mutableMessages` 数组可能增长到数千条消息。虽然 Claude Code 实现了自动压缩 (autoCompact) 和 Snip 机制，但在某些边缘情况下（如频繁的工具执行但低文本输出），内存使用仍可能持续增长。

**挑战问题**:
> 如果让你重新设计 `QueryEngine` 的状态管理架构，你会如何平衡以下三个相互冲突的目标？
>
> 1. **完整历史保留**: 用户可能需要回溯查看早期的对话内容
> 2. **内存效率**: 长运行会话不应无限制消耗内存
> 3. **上下文质量**: 压缩后的上下文应保持足够的语义信息供 LLM 使用
>
> **具体要求**:
> - 提出一种具体的数据结构或策略（例如：增量快照 + 差异存储、向量数据库索引、分层记忆系统）
> - 说明如何在工程上实现你提出的方案（需要修改哪些文件，添加什么接口）
> - 分析你的方案对现有 Harness Engineering 四个维度（可扩展性、安全边界、可观察性、性能）的影响

**提示**: 考虑参考数据库 WAL（预写日志）模式、Git 的对象存储模型、或操作转换（OT）系统的思路。

---

*视角 A 分析完成*
