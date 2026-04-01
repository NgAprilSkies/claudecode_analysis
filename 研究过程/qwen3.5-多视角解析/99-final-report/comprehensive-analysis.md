# Claude Code 架构深度解析

**分析日期**: 2026-04-01  
**分析师**: Qwen3.5 多视角分析团队  
**版本**: 1.0

---

## 执行摘要

Claude Code 是一个高度工程化的 Agent 框架，其设计体现了成熟的 Harness Engineering 思维。本解析从四个核心视角深度剖析其架构设计。

### 关键发现

1. **分层架构清晰**: 从主查询循环到工具执行，层次分明，职责单一
2. **安全边界严密**: 多层权限验证、沙箱机制、分类器决策
3. **可观察性强**: 完整的日志、指标追踪、调试工具
4. **性能优化精细**: 缓存策略、并发控制、token 预算管理

---

## 视角 A：核心构建（The Core Build）

### A.1 Agent 基本结构

Claude Code 的 Agent 架构围绕以下几个核心概念构建：

#### 核心组件层次

```
┌─────────────────────────────────────────────────────────────┐
│                      main.tsx                                │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │ getSystemContext│  │  getUserContext │                   │
│  │ (Git 状态等)     │  │  (CLAUDE.md 等)  │                   │
│  └─────────────────┘  └─────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      query.ts                                │
│                   主查询循环 (queryLoop)                     │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │
│  │ Token 预算检查 │ │ 上下文压缩   │ │ LLM 调用      │         │
│  └──────────────┘ └──────────────┘ └──────────────┘         │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   toolOrchestration.ts                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              runTools() - 工具编排                    │   │
│  │  ┌─────────────┐    ┌─────────────┐                  │   │
│  │  │ 并发安全工具 │    │ 非安全工具   │                  │   │
│  │  │ (并行执行)  │    │ (串行执行)  │                  │   │
│  │  └─────────────┘    └─────────────┘                  │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

#### 状态管理核心：AppState 和 ToolUseContext

**ToolUseContext** 是贯穿整个 Agent 生命周期的核心状态容器：

```typescript
export type ToolUseContext = {
  options: {
    commands: Command[]           // 可用命令
    tools: Tools                   // 可用工具
    mainLoopModel: string          // 主循环模型
    mcpClients: MCPServerConnection[]  // MCP 客户端
    agentDefinitions: AgentDefinitionsResult
    // ... 更多配置
  }
  abortController: AbortController
  readFileState: FileStateCache
  getAppState(): AppState
  setAppState(f: (prev: AppState) => AppState): void
  // ... 40+ 个状态和方法
}
```

**Harness Engineering 评价**:
- **可扩展性**: ⭐⭐⭐⭐⭐ 通过上下文对象传递状态，新增状态只需扩展类型
- **安全边界**: ⭐⭐⭐⭐ 通过 abortController 提供取消机制
- **可观察性**: ⭐⭐⭐⭐ 通过 getAppState/setAppState 提供调试入口
- **性能损耗**: ⭐⭐⭐ 对象展开复制可能带来开销

### A.2 Agent 生命周期

```
┌──────────────────────────────────────────────────────────────────┐
│                     Agent 生命周期                                │
│                                                                   │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐       │
│  │ 初始化  │───>│ 运行中  │───>│ 完成/失败│───>│ 清理    │       │
│  └─────────┘    └─────────┘    └─────────┘    └─────────┘       │
│       │              │              │              │             │
│       ▼              ▼              ▼              ▼             │
│  - 加载配置      - 查询循环    - 成功返回    - 释放资源        │
│  - 构建上下文    - 工具执行    - 错误处理    - 持久化状态      │
│  - 注册工具      - 状态更新    - 结果输出    - 通知监听器      │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

#### 初始化阶段 (main.tsx)

```typescript
// 系统上下文（缓存）
export const getSystemContext = memoize(async () => {
  const gitStatus = await getGitStatus()
  return {
    ...(gitStatus && { gitStatus }),
    // ...其他系统信息
  }
})

// 用户上下文（缓存）
export const getUserContext = memoize(async () => {
  const claudeMd = getClaudeMds(await getMemoryFiles())
  return {
    ...(claudeMd && { claudeMd }),
    currentDate: `Today's date is ${getLocalISODate()}`,
  }
})
```

#### 运行阶段 (query.ts)

核心查询循环处理流程：

```typescript
async function* queryLoop(params, consumedCommandUuids) {
  let state: State = {
    messages: params.messages,
    toolUseContext: params.toolUseContext,
    // ...状态初始化
  }
  
  while (true) {
    // 1. 内存预取
    using pendingMemoryPrefetch = startRelevantMemoryPrefetch(...)
    
    // 2. 技能发现预取
    const pendingSkillPrefetch = skillPrefetch?.startSkillDiscoveryPrefetch(...)
    
    // 3. 工具结果预算应用
    messagesForQuery = await applyToolResultBudget(...)
    
    // 4. 历史压缩 (Snip)
    if (feature('HISTORY_SNIP')) {
      const snipResult = snipModule!.snipCompactIfNeeded(...)
    }
    
    // 5. 微压缩 (Microcompact)
    const microcompactResult = await deps.microcompact(...)
    
    // 6. 自动压缩 (Autocompact)
    const { compactionResult } = await deps.autocompact(...)
    
    // 7. 构建查询配置
    const config = buildQueryConfig()
    
    // 8. 调用 LLM API
    // ...
    
    // 9. 执行工具
    for await (const update of runTools(...)) {
      // ...
    }
    
    // 10. 状态继续或终止
    // continue 站点有 9 个不同路径
  }
}
```

### A.3 Python MRE - 核心构建

```python
#!/usr/bin/env python3
"""
最小化实现：Agent 核心构建模式
展示：状态管理、生命周期、上下文传递
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from enum import Enum
import uuid


class AgentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentState:
    """Agent 状态存储 - 类似 AppState"""
    messages: list = field(default_factory=list)
    tools: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    
    def update(self, updater: Callable[['AgentState'], 'AgentState']) -> 'AgentState':
        """不可变更新模式 - 类似 setAppState"""
        return updater(self)


@dataclass  
class ToolUseContext:
    """工具执行上下文 - 类似 ToolUseContext"""
    state: AgentState
    options: dict
    abort_controller: Optional[Any] = None
    
    def clone(self, **overrides) -> 'ToolUseContext':
        """克隆上下文（用于子 agent）"""
        return ToolUseContext(
            state=overrides.get('state', self.state),
            options=overrides.get('options', self.options.copy()),
            abort_controller=overrides.get('abort_controller', self.abort_controller)
        )


class Agent:
    """简化 Agent 核心"""
    
    def __init__(self, system_prompt: str, tools: list):
        self.id = str(uuid.uuid4())[:8]
        self.system_prompt = system_prompt
        self._state = AgentState(tools={t.name: t for t in tools})
        self._status = AgentStatus.PENDING
        
    @property
    def status(self) -> AgentStatus:
        return self._status
    
    def get_state(self) -> AgentState:
        return self._state
    
    def set_state(self, updater: Callable[[AgentState], AgentState]):
        """不可变状态更新"""
        self._state = self._state.update(updater)
        
    async def run(self, messages: list, context: Optional[ToolUseContext] = None):
        """Agent 主循环"""
        self._status = AgentStatus.RUNNING
        
        # 初始化上下文
        if context is None:
            context = ToolUseContext(
                state=self._state,
                options={'max_turns': 10}
            )
            
        # 主循环
        turn = 0
        while turn < context.options['max_turns']:
            # 1. 检查终止
            if context.abort_controller and context.abort_controller.aborted:
                self._status = AgentStatus.FAILED
                break
                
            # 2. 处理消息
            response = await self._call_llm(messages, context)
            
            # 3. 执行工具
            if response.tool_calls:
                for tool_call in response.tool_calls:
                    result = await self._execute_tool(tool_call, context)
                    messages.append({'role': 'tool', 'content': result})
            else:
                self._status = AgentStatus.COMPLETED
                return response.content
                
            turn += 1
            
        self._status = AgentStatus.FAILED
        return "Max turns exceeded"
    
    async def _call_llm(self, messages, context):
        """模拟 LLM 调用"""
        # 实际实现会调用 Claude API
        return type('Response', (), {
            'tool_calls': [],
            'content': 'Response'
        })()
    
    async def _execute_tool(self, tool_call, context):
        """工具执行"""
        tool = context.state.tools.get(tool_call.name)
        if tool:
            return await tool.execute(tool_call.args, context)
        return f"Tool not found: {tool_call.name}"


# 使用示例
async def demo():
    # 定义工具
    class SimpleTool:
        def __init__(self, name):
            self.name = name
        async def execute(self, args, context):
            return f"Executed {self.name}"
    
    # 创建 Agent
    agent = Agent(
        system_prompt="You are a helpful assistant",
        tools=[SimpleTool("bash"), SimpleTool("read")]
    )
    
    # 运行
    result = await agent.run([{"role": "user", "content": "Hello"}])
    print(f"Result: {result}")
    print(f"Status: {agent.status}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(demo())
```

### A.4 挑战性工程问题

**问题**: 在当前的状态管理中，`ToolUseContext` 通过展开复制 (`{...toolUseContext, ...overrides}`) 来创建新上下文。当 Agent 嵌套层级很深时（如：coordinator 模式下的多层子 agent），这种模式会导致：

1. 深层嵌套时的性能问题
2. 状态一致性难以保证
3. 调试困难（难以追踪状态变更来源）

**思考题**: 如果是你，你会如何重新设计这个状态管理系统？考虑以下方案：
- 使用不可变数据结构库（如 Immer）
- 采用事件溯源（Event Sourcing）模式
- 引入响应式状态管理（如 RxJS）
- 使用基于原型的继承链而非复制

请分析每种方案的优缺点，并给出你的推荐实现。

---

## 视角 B：任务规划（Planning & Reasoning）

### B.1 决策架构

Claude Code 的决策系统采用多层架构：

```
┌─────────────────────────────────────────────────────────────────┐
│                    决策层次架构                                  │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Layer 0: 用户输入解析                                    │   │
│  │ - 命令识别 (getCommands)                                 │   │
│  │ - 意图分类                                               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            │                                    │
│                            ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Layer 1: LLM 决策层                                       │   │
│  │ - 任务拆解 (通过 LLM)                                    │   │
│  │ - 工具选择 (通过 ToolSearch)                             │   │
│  │ - 参数生成                                               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            │                                    │
│                            ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Layer 2: 验证层                                          │   │
│  │ - validateInput() - 输入验证                            │   │
│  │ - checkPermissions() - 权限检查                         │   │
│  │ - classifierDecision - 分类器决策                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            │                                    │
│                            ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Layer 3: 执行层                                          │   │
│  │ - 并发安全工具 → 并行执行                                │   │
│  │ - 非安全工具 → 串行执行                                  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### B.2 任务拆解流程

```typescript
// query.ts 中的决策流程
while (true) {
  // 1. 构建查询
  const config = buildQueryConfig()
  
  // 2. LLM 调用生成工具调用
  const response = await callLLM(messages, config)
  
  // 3. 提取工具调用
  const toolUseMessages = response.content
    .filter(c => c.type === 'tool_use')
  
  // 4. 工具编排执行
  for await (const update of runTools(
    toolUseMessages,
    canUseTool,
    toolUseContext
  )) {
    // 5. 每个工具的执行前验证
    const validationResult = await tool.validateInput?.(input, context)
    if (!validationResult.result) {
      // 验证失败处理
    }
    
    // 6. 权限检查
    const permissionResult = await canUseTool(tool, input)
    if (permissionResult.behavior === 'deny') {
      // 拒绝处理
    }
    
    // 7. 实际执行
    const result = await tool.call(input, context, canUseTool)
  }
  
  // 8. 结果处理和下一轮决策
}
```

### B.3 动态调整机制

通过 9 个 continue 站点实现决策路径的动态调整：

1. **工具执行成功** → 继续下一轮
2. **工具执行失败** → 错误处理
3. **token 超限** → 触发压缩
4. **用户中断** → 清理并终止
5. **最大输出 token** → 恢复循环
6. **Hook 激活** → 暂停等待
7. **缓存中断** → 重新查询
8. **反应式压缩** → 主动压缩
9. **正常完成** → 返回结果

### B.4 Python MRE - 任务规划

```python
#!/usr/bin/env python3
"""
最小化实现：任务规划与决策系统
展示：任务拆解、决策路径、动态调整
"""

from dataclasses import dataclass, field
from typing import Optional, Callable, Any
from enum import Enum
import asyncio


class DecisionType(Enum):
    CONTINUE = "continue"
    TERMINATE = "terminate"
    COMPACT = "compact"
    RECOVER = "recover"
    ERROR = "error"


@dataclass
class Decision:
    """决策结果"""
    decision_type: DecisionType
    reason: str
    data: Optional[dict] = None


@dataclass
class ToolCall:
    """工具调用"""
    name: str
    args: dict
    id: str


@dataclass
class LLMResponse:
    """LLM 响应"""
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class DecisionEngine:
    """决策引擎 - 核心规划逻辑"""
    
    def __init__(
        self,
        llm_client: Any,
        tools: dict,
        max_turns: int = 10
    ):
        self.llm_client = llm_client
        self.tools = tools
        self.max_turns = max_turns
        self._turn_count = 0
        
    async def plan_and_execute(
        self,
        initial_messages: list[dict],
        dynamic_adjustment: bool = True
    ) -> str:
        """
        规划并执行任务
        
        Args:
            initial_messages: 初始消息
            dynamic_adjustment: 是否启用动态调整
            
        Returns:
            执行结果
        """
        messages = list(initial_messages)
        self._turn_count = 0
        
        while self._turn_count < self.max_turns:
            self._turn_count += 1
            
            # 1. LLM 决策
            response = await self._call_llm(messages)
            
            # 2. 没有工具调用，直接返回
            if not response.tool_calls:
                return response.content
            
            # 3. 执行工具调用
            for tool_call in response.tool_calls:
                result, decision = await self._execute_with_decision(
                    tool_call, 
                    messages,
                    dynamic_adjustment
                )
                
                # 4. 根据决策调整路径
                if decision.decision_type == DecisionType.TERMINATE:
                    return result
                elif decision.decision_type == DecisionType.COMPACT:
                    messages = await self._compact_context(messages)
                    continue
                elif decision.decision_type == DecisionType.RECOVER:
                    # 恢复逻辑
                    messages.append({'role': 'system', 'content': 'Retrying...'})
                    continue
                elif decision.decision_type == DecisionType.ERROR:
                    return f"Error: {decision.reason}"
                    
                messages.append({
                    'role': 'tool',
                    'content': str(result),
                    'tool_call_id': tool_call.id
                })
        
        return "Max turns exceeded"
    
    async def _execute_with_decision(
        self,
        tool_call: ToolCall,
        messages: list,
        dynamic_adjustment: bool
    ) -> tuple[Any, Decision]:
        """带决策的执行"""
        tool = self.tools.get(tool_call.name)
        
        if not tool:
            return None, Decision(
                DecisionType.ERROR,
                f"Tool not found: {tool_call.name}"
            )
        
        try:
            # 1. 验证
            if hasattr(tool, 'validate'):
                valid, error = await tool.validate(tool_call.args)
                if not valid:
                    return None, Decision(
                        DecisionType.ERROR,
                        f"Validation failed: {error}"
                    )
            
            # 2. 执行
            result = await tool.execute(tool_call.args)
            
            # 3. 动态调整决策
            if dynamic_adjustment:
                decision = await self._make_decision(result, messages)
                return result, decision
                
            return result, Decision(DecisionType.CONTINUE, "OK")
            
        except Exception as e:
            return None, Decision(DecisionType.RECOVER, str(e))
    
    async def _make_decision(
        self, 
        result: Any, 
        messages: list
    ) -> Decision:
        """根据执行结果做决策"""
        # 简化决策逻辑
        if isinstance(result, str) and 'error' in result.lower():
            return Decision(DecisionType.RECOVER, result)
        
        if len(str(result)) > 10000:
            return Decision(
                DecisionType.COMPACT, 
                "Result too large",
                {'size': len(str(result))}
            )
            
        return Decision(DecisionType.CONTINUE, "OK")
    
    async def _call_llm(self, messages: list) -> LLMResponse:
        """模拟 LLM 调用"""
        # 实际实现调用 LLM API
        return LLMResponse(content="Processing...", tool_calls=[])
    
    async def _compact_context(self, messages: list) -> list:
        """压缩上下文"""
        # 实际实现会调用压缩逻辑
        print("Compacting context...")
        return messages[-5:]  # 简化：只保留最近 5 条


# 工具定义
class Tool:
    def __init__(self, name: str, execute_fn: Callable):
        self.name = name
        self._execute = execute_fn
        
    async def execute(self, args: dict) -> Any:
        return await self._execute(args)
    
    async def validate(self, args: dict) -> tuple[bool, Optional[str]]:
        return True, None


# 使用示例
async def demo():
    # 定义工具
    async def bash_execute(args):
        cmd = args.get('command', 'echo hello')
        return f"Output of: {cmd}"
    
    async def read_execute(args):
        path = args.get('path', 'file.txt')
        return f"Content of {path}"
    
    tools = {
        'Bash': Tool('Bash', bash_execute),
        'Read': Tool('Read', read_execute),
    }
    
    # 创建决策引擎
    engine = DecisionEngine(
        llm_client=None,  # 模拟
        tools=tools,
        max_turns=5
    )
    
    # 执行
    messages = [{'role': 'user', 'content': 'Check the project'}]
    result = await engine.plan_and_execute(messages)
    print(f"Final result: {result}")


if __name__ == "__main__":
    asyncio.run(demo())
```

### B.5 挑战性工程问题

**问题**: 当前的决策系统有 9 个 continue 站点，每个站点代表一种决策路径。这种设计的缺点是：

1. 决策逻辑分散，难以全局理解
2. 新增决策路径需要修改核心循环
3. 决策之间的优先级关系不明确

**思考题**: 如果要设计一个更加模块化、可扩展的决策系统，你会采用什么架构模式？考虑：

- **状态机模式**: 将每个决策状态显式化
- **责任链模式**: 决策处理器链式传递
- **策略模式**: 可插拔的决策策略
- **规则引擎**: 基于规则的决策系统

请设计一个新架构，能够支持：
1. 运行时动态注册新的决策处理器
2. 决策优先级的可配置
3. 决策过程的完整可追溯

---

## 视角 C：工具集成（Tool Integration）

### C.1 工具类型系统

Claude Code 使用强大的 TypeScript 类型系统来定义工具：

```typescript
export type Tool<Input, Output, Progress> = {
  // 基本信息
  name: string
  aliases?: string[]
  searchHint?: string
  
  // 核心执行
  call(
    args: z.infer<Input>,
    context: ToolUseContext,
    canUseTool: CanUseToolFn,
    onProgress?: ToolCallProgress<P>
  ): Promise<ToolResult<Output>>
  
  // 验证和权限
  validateInput?(input, context): Promise<ValidationResult>
  checkPermissions(input, context): Promise<PermissionResult>
  
  // 行为特征
  isConcurrencySafe(input): boolean
  isReadOnly(input): boolean
  isDestructive?(input): boolean
  interruptBehavior?(): 'cancel' | 'block'
  
  // UI 渲染（多个生命周期方法）
  renderToolUseMessage(input, options): React.ReactNode
  renderToolResultMessage(content, progress, options): React.ReactNode
  renderToolUseProgressMessage?(progress, options): React.ReactNode
  
  // 其他元数据
  maxResultSizeChars: number
  shouldDefer?: boolean
  alwaysLoad?: boolean
}
```

### C.2 工具编排系统

```typescript
// toolOrchestration.ts

async function* runTools(
  toolUseMessages: ToolUseBlock[],
  canUseTool: CanUseToolFn,
  toolUseContext: ToolUseContext
): AsyncGenerator<MessageUpdate> {
  
  // 1. 分区：并发安全工具 vs 非安全工具
  for (const { isConcurrencySafe, blocks } of partitionToolCalls(...)) {
    
    if (isConcurrencySafe) {
      // 2a. 并发安全 → 并行执行
      const queuedContextModifiers = {}
      for await (const update of runToolsConcurrently(...)) {
        // 收集上下文修改器
        if (update.contextModifier) {
          // 排队等待应用
        }
        yield update
      }
      // 应用所有上下文修改
      for (const modifier of modifiers) {
        currentContext = modifier(currentContext)
      }
      
    } else {
      // 2b. 非安全 → 串行执行
      for await (const update of runToolsSerially(...)) {
        if (update.newContext) {
          currentContext = update.newContext
        }
        yield update
      }
    }
  }
}
```

### C.3 权限验证流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    工具调用权限验证流程                          │
│                                                                  │
│  ┌─────────────────┐                                           │
│  │ 1. validateInput│ - 输入格式验证                             │
│  │                 │   - Zod schema 验证                         │
│  │                 │   - 自定义验证逻辑                         │
│  └────────┬────────┘                                           │
│           │ 通过                                                 │
│           ▼                                                     │
│  ┌─────────────────┐                                           │
│  │ 2. checkPermissions (工具级)                                 │
│  │                 │                                           │
│  │                 │ - 工具特定权限逻辑                         │
│  │                 │ - 返回 PermissionResult                    │
│  └────────┬────────┘                                           │
│           │ 需要通用检查                                         │
│           ▼                                                     │
│  ┌─────────────────┐                                           │
│  │ 3. canUseTool   │ - 通用权限检查入口                         │
│  │                 │                                           │
│  │ ┌─────────────┐ │                                           │
│  │ │a. Deny Rules│ │ - 匹配拒绝规则                            │
│  │ │b. Allow Rules││ - 匹配允许规则                            │
│  │ │c. Ask Rules │ │ - 匹配询问规则                            │
│  │ └─────┬───────┘ │                                           │
│  └───────┼─────────┘                                           │
│           │ 需要用户确认                                         │
│           ▼                                                     │
│  ┌─────────────────┐                                           │
│  │ 4. 权限请求对话框 │                                          │
│  │                 │                                           │
│  │ - Always allow  │                                           │
│  │ - Always deny   │                                           │
│  │ - This time only│                                           │
│  └────────┬────────┘                                           │
│           │ 用户选择                                             │
│           ▼                                                     │
│  ┌─────────────────┐                                           │
│  │ 5. Hook 执行     │ - PreToolUse hooks                       │
│  │                 │ - PostToolUse hooks                       │
│  └────────┬────────┘                                           │
│           │ 通过                                                 │
│           ▼                                                     │
│  ┌─────────────────┐                                           │
│  │ 6. 实际执行     │                                           │
│  └─────────────────┘                                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### C.4 工具注册机制

```typescript
// tools.ts - 工具注册中心

export function getAllBaseTools(): Tools {
  return [
    AgentTool,
    BashTool,
    FileReadTool,
    FileEditTool,
    // ... 50+ 内置工具
    
    // 条件加载的工具
    ...(hasEmbeddedSearchTools() ? [] : [GlobTool, GrepTool]),
    ...(isEnvTruthy(process.env.ENABLE_LSP_TOOL) ? [LSPTool] : []),
    ...(isWorktreeModeEnabled() ? [EnterWorktreeTool, ExitWorktreeTool] : []),
  ]
}

export function getTools(permissionContext): Tools {
  const allTools = getAllBaseTools()
  
  // 1. 简单模式过滤
  if (isEnvTruthy(process.env.CLAUDE_CODE_SIMPLE)) {
    return [BashTool, FileReadTool, FileEditTool]
  }
  
  // 2. 权限规则过滤
  return filterToolsByDenyRules(allTools, permissionContext)
}
```

### C.5 Python MRE - 工具集成

```python
#!/usr/bin/env python3
"""
最小化实现：工具集成系统
展示：工具注册、权限验证、编排执行
"""

from dataclasses import dataclass, field
from typing import Optional, Callable, Any, Dict, List, Tuple
from enum import Enum
import asyncio
from abc import ABC, abstractmethod


class PermissionBehavior(Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


@dataclass
class PermissionResult:
    """权限验证结果"""
    behavior: PermissionBehavior
    reason: Optional[str] = None
    updated_input: Optional[dict] = None


@dataclass
class ToolDefinition:
    """工具定义"""
    name: str
    description: str
    input_schema: dict
    is_read_only: bool = False
    is_destructive: bool = False


class BaseTool(ABC):
    """工具基类"""
    
    def __init__(self, definition: ToolDefinition):
        self.definition = definition
        
    @abstractmethod
    async def execute(self, args: dict, context: Any) -> Any:
        """执行工具"""
        pass
    
    async def validate_input(self, args: dict) -> Tuple[bool, Optional[str]]:
        """验证输入"""
        # 默认实现：检查必需字段
        required = self.definition.input_schema.get('required', [])
        for field in required:
            if field not in args:
                return False, f"Missing required field: {field}"
        return True, None
    
    async def check_permissions(
        self, 
        args: dict, 
        context: Any
    ) -> PermissionResult:
        """权限检查"""
        # 默认允许，子类可覆盖
        return PermissionResult(PermissionBehavior.ALLOW)


class BashTool(BaseTool):
    """Bash 工具示例"""
    
    def __init__(self):
        super().__init__(ToolDefinition(
            name="Bash",
            description="Execute bash commands",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string"}
                },
                "required": ["command"]
            },
            is_destructive=True
        ))
    
    async def execute(self, args: dict, context: Any) -> str:
        cmd = args.get('command')
        # 实际实现会调用 subprocess
        return f"[Bash output] {cmd}"
    
    async def check_permissions(self, args, context) -> PermissionResult:
        # 自定义权限逻辑：拒绝危险命令
        cmd = args.get('command', '')
        dangerous = ['rm -rf /', 'sudo rm', 'mkfs']
        if any(d in cmd for d in dangerous):
            return PermissionResult(
                PermissionBehavior.DENY,
                "Dangerous command detected"
            )
        return PermissionResult(PermissionBehavior.ALLOW)


class ToolOrchestrator:
    """工具编排器"""
    
    def __init__(self, tools: List[BaseTool]):
        self.tools = {t.definition.name: t for t in tools}
        self._permission_rules: List[Callable] = []
        
    def register_permission_rule(self, rule: Callable):
        """注册权限规则"""
        self._permission_rules.append(rule)
        
    async def can_use_tool(
        self,
        tool_name: str,
        args: dict,
        context: Any
    ) -> PermissionResult:
        """检查工具是否可用"""
        tool = self.tools.get(tool_name)
        if not tool:
            return PermissionResult(
                PermissionBehavior.DENY,
                f"Tool not found: {tool_name}"
            )
        
        # 1. 工具级权限检查
        tool_result = await tool.check_permissions(args, context)
        if tool_result.behavior != PermissionBehavior.ALLOW:
            return tool_result
        
        # 2. 全局规则检查
        for rule in self._permission_rules:
            rule_result = await rule(tool_name, args, context)
            if rule_result.behavior == PermissionBehavior.DENY:
                return rule_result
        
        return PermissionResult(PermissionBehavior.ALLOW)
    
    async def execute_tool(
        self,
        tool_name: str,
        args: dict,
        context: Any,
        can_use_tool_fn: Callable
    ) -> Any:
        """执行工具（带权限检查）"""
        # 1. 权限检查
        permission = await can_use_tool_fn(
            tool_name, 
            args, 
            context
        )
        
        if permission.behavior == PermissionBehavior.DENY:
            raise PermissionError(
                f"Tool {tool_name} denied: {permission.reason}"
            )
        
        if permission.behavior == PermissionBehavior.ASK:
            # 实际实现会显示 UI 询问用户
            user_choice = await self._ask_user(tool_name, args)
            if not user_choice:
                raise PermissionError("User denied")
        
        # 2. 输入验证
        tool = self.tools.get(tool_name)
        valid, error = await tool.validate_input(args)
        if not valid:
            raise ValueError(f"Invalid input: {error}")
        
        # 3. 应用输入更新（权限规则可能修改输入）
        if permission.updated_input:
            args = permission.updated_input
        
        # 4. 执行
        return await tool.execute(args, context)
    
    async def _ask_user(self, tool_name: str, args: dict) -> bool:
        """询问用户（简化实现）"""
        # 实际实现会显示 UI
        print(f"Permission requested: {tool_name}")
        print(f"Arguments: {args}")
        return True  # 默认允许
    
    async def execute_multiple(
        self,
        tool_calls: List[Tuple[str, dict]],
        context: Any,
        concurrency_safe: bool = True
    ) -> List[Any]:
        """执行多个工具调用"""
        if concurrency_safe:
            # 并行执行
            return await asyncio.gather(*[
                self.execute_tool(name, args, context, self.can_use_tool)
                for name, args in tool_calls
            ])
        else:
            # 串行执行
            results = []
            for name, args in tool_calls:
                result = await self.execute_tool(
                    name, args, context, self.can_use_tool
                )
                results.append(result)
            return results


# 使用示例
async def demo():
    # 创建工具
    tools = [
        BashTool(),
        # ... 更多工具
    ]
    
    # 创建编排器
    orchestrator = ToolOrchestrator(tools)
    
    # 注册全局权限规则
    async def no_sudo_rule(tool_name, args, context):
        if 'sudo' in args.get('command', ''):
            return PermissionResult(
                PermissionBehavior.ASK,
                "sudo requires confirmation"
            )
        return PermissionResult(PermissionBehavior.ALLOW)
    
    orchestrator.register_permission_rule(no_sudo_rule)
    
    # 执行工具
    context = None  # 简化
    result = await orchestrator.execute_tool(
        "Bash",
        {"command": "echo hello"},
        context,
        orchestrator.can_use_tool
    )
    print(f"Result: {result}")
    
    # 并行执行多个工具
    results = await orchestrator.execute_multiple(
        [
            ("Bash", {"command": "ls"}),
            ("Bash", {"command": "pwd"}),
        ],
        context,
        concurrency_safe=True
    )
    print(f"Parallel results: {results}")


if __name__ == "__main__":
    asyncio.run(demo())
```

### C.6 挑战性工程问题

**问题**: 当前的工具系统设计非常灵活，但存在以下安全隐患：

1. **输入验证分散**: 每个工具自己实现 `validateInput`，标准不一致
2. **权限规则冲突**: 多条规则可能产生冲突的决策
3. **工具注入风险**: 动态加载的工具可能绕过来路检查
4. **沙箱逃逸**: Bash 工具的沙箱可能不是绝对安全

**思考题**: 设计一个更安全的工具执行框架，需要考虑：

1. **统一输入验证层**: 基于 Schema 的集中验证
2. **规则冲突解决**: 定义明确的优先级和解决策略
3. **工具签名验证**: 确保工具来源可信
4. **执行沙箱**: 多层隔离机制

请设计一个安全架构，包含：
- 工具信任链验证（类似代码签名）
- 多层沙箱执行（类似浏览器安全模型）
- 审计日志系统（用于事后分析）

---

## 视角 D：记忆系统（Memory Systems）

### D.1 记忆系统层次

```
┌─────────────────────────────────────────────────────────────────┐
│                     记忆系统架构                                 │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ L1: 短期记忆 (对话上下文)                                │   │
│  │ - messages 数组 (当前会话消息)                           │   │
│  │ - 通过 tokenCountWithEstimation 管理大小                 │   │
│  │ - 超出阈值时触发压缩                                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            │                                    │
│           自动压缩/手动压缩                                       │
│                            ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ L2: 中期记忆 (会话历史)                                  │   │
│  │ - history.jsonl (全局历史文件)                           │   │
│  │ - 粘贴内容存储 (paste store)                             │   │
│  │ - 项目级历史索引                                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            │                                    │
│           会话结束/持久化                                         │
│                            ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ L3: 长期记忆 (持久化存储)                                │   │
│  │ - CLAUDE.md (项目文档)                                   │   │
│  │ - .claude/ 目录配置                                      │   │
│  │ - 技能库 (skills)                                        │   │
│  │ - 插件配置 (plugins)                                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            │                                    │
│           主动检索/被动触发                                       │
│                            ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ L4: 外部记忆 (按需加载)                                  │   │
│  │ - Session Memory (远程记忆服务)                          │   │
│  │ - Relevant Memory Prefetch (相关性预取)                   │   │
│  │ - Skill Discovery (技能发现)                             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### D.2 上下文压缩策略

Claude Code 实现了多层压缩策略：

```typescript
// query.ts 中的压缩流程

// 1. Snip Compact (快速删除消息)
if (feature('HISTORY_SNIP')) {
  const snipResult = snipModule!.snipCompactIfNeeded(messagesForQuery)
  messagesForQuery = snipResult.messages
  snipTokensFreed = snipResult.tokensFreed
}

// 2. Microcompact (微压缩)
const microcompactResult = await deps.microcompact(
  messagesForQuery,
  toolUseContext,
  querySource
)

// 3. AutoCompact (自动压缩)
const { compactionResult } = await deps.autocompact(
  messagesForQuery,
  toolUseContext,
  cacheSafeParams,
  querySource,
  tracking,
  snipTokensFreed
)

// 4. ReactiveCompact (反应式压缩 - API 触发)
if (feature('REACTIVE_COMPACT')) {
  // 当 API 返回 prompt_too_long 错误时触发
}
```

### D.3 Token 预算管理

```typescript
// autoCompact.ts

// 阈值定义
export const AUTOCOMPACT_BUFFER_TOKENS = 13_000  // 自动压缩触发余量
export const WARNING_THRESHOLD_BUFFER_TOKENS = 20_000  // 警告阈值
export const ERROR_THRESHOLD_BUFFER_TOKENS = 20_000   // 错误阈值
export const MANUAL_COMPACT_BUFFER_TOKENS = 3_000     // 手动压缩余量

// 有效上下文窗口
export function getEffectiveContextWindowSize(model: string): number {
  const reservedTokensForSummary = Math.min(
    getMaxOutputTokensForModel(model),
    MAX_OUTPUT_TOKENS_FOR_SUMMARY,  // 20,000
  )
  let contextWindow = getContextWindowForModel(model)
  
  // 环境变量覆盖
  const autoCompactWindow = process.env.CLAUDE_CODE_AUTO_COMPACT_WINDOW
  if (autoCompactWindow) {
    contextWindow = Math.min(contextWindow, parseInt(autoCompactWindow))
  }
  
  return contextWindow - reservedTokensForSummary
}

// 自动压缩阈值
export function getAutoCompactThreshold(model: string): number {
  const effectiveContextWindow = getEffectiveContextWindowSize(model)
  return effectiveContextWindow - AUTOCOMPACT_BUFFER_TOKENS
}
```

### D.4 记忆检索流程

```
┌─────────────────────────────────────────────────────────────────┐
│                     记忆检索流程                                 │
│                                                                  │
│  ┌─────────────────┐                                           │
│  │ 用户输入         │                                           │
│  └────────┬────────┘                                           │
│           │                                                     │
│           ▼                                                     │
│  ┌─────────────────┐                                           │
│  │ 1. 内存预取     │ (startRelevantMemoryPrefetch)             │
│  │                 │ - 后台异步执行                            │
│  │                 │ - 不阻塞主流程                            │
│  └────────┬────────┘                                           │
│           │                                                     │
│           ▼                                                     │
│  ┌─────────────────┐                                           │
│  │ 2. 技能发现预取 │ (startSkillDiscoveryPrefetch)             │
│  │                 │ - 检查写操作触发点                        │   │
│  │                 │ - 动态发现相关技能                        │
│  └────────┬────────┘                                           │
│           │                                                     │
│           ▼                                                     │
│  ┌─────────────────┐                                           │
│  │ 3. 附件处理     │ (getAttachmentMessages)                    │
│  │                 │ - 图像缓存检索                            │
│  │                 │ - 粘贴内容展开                            │
│  └────────┬────────┘                                           │
│           │                                                     │
│           ▼                                                     │
│  ┌─────────────────┐                                           │
│  │ 4. Session Memory│ (trySessionMemoryCompaction)              │
│  │                 │ - 远程记忆服务查询                        │
│  │                 │ - 相关性排序                              │
│  └────────┬────────┘                                           │
│           │                                                     │
│           ▼                                                     │
│  ┌─────────────────┐                                           │
│  │ 5. 上下文构建   │                                            │
│  │                 │ - 合并所有记忆源                          │
│  │                 │ - 应用 token 预算                          │
│  └─────────────────┘                                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### D.5 Python MRE - 记忆系统

```python
#!/usr/bin/env python3
"""
最小化实现：记忆系统
展示：上下文管理、压缩策略、记忆检索
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from collections import deque
import hashlib
import time
import json


@dataclass
class MemoryEntry:
    """记忆条目"""
    id: str
    content: str
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    token_estimate: int = 0


@dataclass
class CompressedMemory:
    """压缩后的记忆"""
    summary: str
    original_ids: List[str]
    compression_ratio: float
    timestamp: float


class TokenBudget:
    """Token 预算管理"""
    
    def __init__(self, max_tokens: int = 100000):
        self.max_tokens = max_tokens
        self.warning_threshold = max_tokens - 20000
        self.error_threshold = max_tokens - 40000
        
    def check_status(self, used_tokens: int) -> Dict[str, bool]:
        """检查 token 使用状态"""
        remaining = self.max_tokens - used_tokens
        return {
            'is_above_warning': used_tokens >= self.warning_threshold,
            'is_above_error': used_tokens >= self.error_threshold,
            'remaining_tokens': remaining,
            'percent_used': (used_tokens / self.max_tokens) * 100
        }


class MemoryStore:
    """记忆存储"""
    
    def __init__(self):
        self.entries: Dict[str, MemoryEntry] = {}
        self.timeline: deque = deque(maxlen=1000)
        self.compressed: Dict[str, CompressedMemory] = {}
        
    def add(self, content: str, metadata: Dict = None) -> str:
        """添加记忆"""
        entry_id = hashlib.md5(
            f"{content}{time.time()}".encode()
        ).hexdigest()[:12]
        
        entry = MemoryEntry(
            id=entry_id,
            content=content,
            timestamp=time.time(),
            metadata=metadata or {},
            token_estimate=len(content) // 4  # 简化估算
        )
        
        self.entries[entry_id] = entry
        self.timeline.append(entry_id)
        return entry_id
    
    def get_recent(self, limit: int = 50) -> List[MemoryEntry]:
        """获取最近的记忆"""
        recent_ids = list(self.timeline)[-limit:]
        return [self.entries[eid] for eid in recent_ids if eid in self.entries]
    
    def compress(
        self, 
        entries: List[str], 
        compressor: Callable[[List[str]], str]
    ) -> CompressedMemory:
        """压缩记忆"""
        contents = [
            self.entries[eid].content 
            for eid in entries 
            if eid in self.entries
        ]
        
        summary = compressor(contents)
        original_tokens = sum(
            self.entries[eid].token_estimate for eid in entries
        )
        compressed_tokens = len(summary) // 4
        
        compressed = CompressedMemory(
            summary=summary,
            original_ids=entries,
            compression_ratio=compressed_tokens / max(original_tokens, 1),
            timestamp=time.time()
        )
        
        # 存储压缩结果
        for eid in entries:
            if eid in self.entries:
                del self.entries[eid]
                self.timeline.remove(eid)
        
        comp_id = hashlib.md5(
            f"compressed{time.time()}".encode()
        ).hexdigest()[:12]
        self.compressed[comp_id] = compressed
        
        # 将压缩摘要添加到时间线
        summary_entry = MemoryEntry(
            id=comp_id,
            content=summary,
            timestamp=time.time(),
            metadata={'type': 'compressed', 'original_count': len(entries)},
            token_estimate=compressed_tokens
        )
        self.entries[comp_id] = summary_entry
        self.timeline.append(comp_id)
        
        return compressed


class ContextManager:
    """上下文管理器"""
    
    def __init__(
        self,
        budget: TokenBudget,
        memory_store: MemoryStore,
        auto_compress_threshold: float = 0.8
    ):
        self.budget = budget
        self.memory_store = memory_store
        self.auto_compress_threshold = auto_compress_threshold
        self.current_messages: List[Dict] = []
        
    def add_message(self, role: str, content: str) -> str:
        """添加消息并管理上下文"""
        # 添加到当前上下文
        self.current_messages.append({
            'role': role,
            'content': content,
            'timestamp': time.time()
        })
        
        # 添加到长期记忆
        self.memory_store.add(content, {'role': role})
        
        # 检查是否需要压缩
        self._maybe_auto_compress()
        
        return self.current_messages[-1]['id'] if 'id' in self.current_messages[-1] else str(len(self.current_messages))
    
    def get_context(self) -> List[Dict]:
        """获取当前上下文（在预算内）"""
        current_tokens = self._count_tokens()
        status = self.budget.check_status(current_tokens)
        
        if status['is_above_warning']:
            # 返回裁剪后的上下文
            return self._trim_to_budget()
        
        return list(self.current_messages)
    
    def _count_tokens(self) -> int:
        """估算当前 token 数"""
        return sum(
            len(msg.get('content', '')) // 4 
            for msg in self.current_messages
        )
    
    def _maybe_auto_compress(self):
        """自动压缩检查"""
        current_tokens = self._count_tokens()
        status = self.budget.check_status(current_tokens)
        
        if status['percent_used'] >= self.auto_compress_threshold * 100:
            # 触发压缩
            self._compress_old_messages()
    
    def _compress_old_messages(
        self, 
        compressor: Callable[[List[str]], str] = None
    ):
        """压缩旧消息"""
        if compressor is None:
            # 默认压缩器：简单连接
            compressor = lambda contents: "[Summary] " + "... ".join(
                c[:100] for c in contents
            )
        
        # 获取要压缩的消息（最旧的一半）
        compress_count = max(1, len(self.current_messages) // 2)
        to_compress = self.current_messages[:compress_count]
        
        if not to_compress:
            return
        
        # 执行压缩
        summary = compressor([m['content'] for m in to_compress])
        
        # 替换为压缩摘要
        self.current_messages = [{
            'role': 'system',
            'content': summary,
            'id': 'compressed',
            'timestamp': time.time()
        }] + self.current_messages[compress_count:]
    
    def _trim_to_budget(self) -> List[Dict]:
        """裁剪到预算内"""
        max_tokens = self.budget.warning_threshold
        result = []
        current_tokens = 0
        
        # 从后往前添加（保留最新的）
        for msg in reversed(self.current_messages):
            msg_tokens = len(msg.get('content', '')) // 4
            if current_tokens + msg_tokens > max_tokens:
                break
            result.insert(0, msg)
            current_tokens += msg_tokens
        
        return result


# 使用示例
def demo():
    # 创建组件
    budget = TokenBudget(max_tokens=100000)
    memory = MemoryStore()
    context_mgr = ContextManager(
        budget, 
        memory,
        auto_compress_threshold=0.7
    )
    
    # 模拟对话
    for i in range(20):
        context_mgr.add_message(
            'user', 
            f"Message {i}: " + "Hello " * 100
        )
        context_mgr.add_message(
            'assistant',
            f"Response {i}: " + "World " * 100
        )
        
        # 显示状态
        tokens = context_mgr._count_tokens()
        status = budget.check_status(tokens)
        print(f"After {i+1} turns: {tokens} tokens, "
              f"warning={status['is_above_warning']}")
    
    # 获取最终上下文
    context = context_mgr.get_context()
    print(f"\nFinal context: {len(context)} messages")
    print(f"First message preview: {context[0]['content'][:50]}...")


if __name__ == "__main__":
    demo()
```

### D.6 挑战性工程问题

**问题**: 当前的记忆系统设计存在以下挑战：

1. **压缩质量不一致**: 不同压缩策略（snip/micro/autocompact）产生的摘要质量参差不齐
2. **记忆检索效率**: 线性搜索在大规模记忆中效率低下
3. **上下文污染**: 不相关信息可能混入压缩摘要
4. **记忆一致性**: 多 agent 场景下记忆同步困难

**思考题**: 设计一个更智能的记忆系统，考虑：

1. **语义压缩**: 使用 embedding 和向量相似度进行智能压缩
2. **分层检索**: 结合关键词和语义的混合检索
3. **记忆评分**: 基于重要性、时效性、使用频率的记忆权重
4. **记忆图**: 使用知识图谱组织记忆之间的关系

请设计一个下一代记忆系统架构，能够：
- 自动识别和保留关键信息
- 高效检索相关记忆
- 支持多 agent 共享记忆
- 提供记忆可解释性（为什么保留/删除某条记忆）

---

## 总结

本分析从四个视角深度剖析了 Claude Code 的架构设计：

| 视角 | 核心发现 | Harness Engineering 评分 |
|------|----------|-------------------------|
| **核心构建** | 分层架构清晰，状态管理灵活 | ⭐⭐⭐⭐ |
| **任务规划** | 9 个决策路径，动态调整能力强 | ⭐⭐⭐⭐ |
| **工具集成** | 类型安全，权限验证严密 | ⭐⭐⭐⭐⭐ |
| **记忆系统** | 多层压缩策略，token 预算精细 | ⭐⭐⭐⭐ |

### 总体评价

Claude Code 展现了一个成熟、工程化的 Agent 框架应有的设计水准：

1. **安全性**: 多层权限验证、沙箱机制、输入过滤
2. **可扩展性**: 模块化设计、清晰的接口定义
3. **可观察性**: 完整的日志、指标、调试工具
4. **性能**: 缓存策略、并发控制、资源管理

### 改进建议

1. **状态管理**: 考虑引入不可变数据结构或事件溯源
2. **决策系统**: 模块化决策处理器，支持动态注册
3. **工具安全**: 统一输入验证层，多层沙箱隔离
4. **记忆系统**: 语义压缩和检索，记忆评分机制

---

*本分析报告由 Qwen3.5 多视角分析团队生成*
