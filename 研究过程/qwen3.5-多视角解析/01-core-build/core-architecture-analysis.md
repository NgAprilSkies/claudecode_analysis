# 视角 A：核心构建分析 (The Core Build)

## A.1 Agent 基本结构

### 核心类设计

Claude Code 的 Agent 架构围绕以下几个核心概念构建：

#### 1. ToolUseContext - 状态容器

```typescript
export type ToolUseContext = {
  options: {
    commands: Command[]           // 可用命令
    tools: Tools                   // 可用工具
    mainLoopModel: string          // 主循环模型
    mcpClients: MCPServerConnection[]  // MCP 客户端
    agentDefinitions: AgentDefinitionsResult
  }
  abortController: AbortController
  readFileState: FileStateCache
  getAppState(): AppState
  setAppState(f: (prev: AppState) => AppState): void
  // ... 40+ 个状态和方法
}
```

**设计特点**:
- 通过上下文对象传递状态，新增状态只需扩展类型
- 通过 abortController 提供取消机制
- 通过 getAppState/setAppState 提供调试入口
- 对象展开复制可能带来开销

#### 2. AppState - 全局状态存储

```typescript
export type AppState = {
  // 会话相关
  sessionId: string
  messages: Message[]
  
  // 工具相关
  tools: Map<string, Tool>
  inProgressToolUseIDs: Set<string>
  
  // 配置相关
  permissions: PermissionMode
  theme: ThemeName
  
  // ... 更多状态
}
```

### Harness Engineering 评价

| 维度 | 评分 | 说明 |
|------|------|------|
| 可扩展性 | ⭐⭐⭐⭐⭐ | 上下文对象扩展 | 状态不可变更新 | 模块化设计 |
| 安全边界 | ⭐⭐⭐⭐ | abortController 取消 | 资源清理注册 | 错误边界 |
| 可观察性 | ⭐⭐⭐⭐ | getAppState 调试入口 | 日志追踪 | 状态快照 |
| 性能损耗 | ⭐⭐⭐ | 对象展开复制开销 | memoize 缓存优化 | 深层嵌套问题 |

---

## A.2 Agent 生命周期

### 完整生命周期流程

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

### 初始化阶段 (main.tsx)

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

### 运行阶段 (query.ts)

核心查询循环处理流程：

```typescript
async function* queryLoop(params, consumedCommandUuids) {
  let state: State = {
    messages: params.messages,
    toolUseContext: params.toolUseContext,
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
    
    // 10. 状态继续或终止 (9 个 continue 站点)
  }
}
```

---

## A.3 9 个 Continue 站点（决策路径）

| 序号 | 触发条件 | 处理逻辑 |
|------|----------|----------|
| 1 | 工具执行成功 | 添加结果→继续下一轮 |
| 2 | 工具执行失败 | 错误消息→返回 |
| 3 | Token 超限 | 压缩后→重试 |
| 4 | 用户中断 | 清理→终止 |
| 5 | max_output_tokens | 恢复循环 |
| 6 | Hook 激活 | 等待→恢复 |
| 7 | 缓存中断 | 重新查询 |
| 8 | 反应式压缩 | 主动压缩 |
| 9 | 正常完成 | 返回结果 |

---

## A.4 Python MRE - 核心构建

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
        
        if context is None:
            context = ToolUseContext(
                state=self._state,
                options={'max_turns': 10}
            )
            
        turn = 0
        while turn < context.options['max_turns']:
            if context.abort_controller and context.abort_controller.aborted:
                self._status = AgentStatus.FAILED
                break
                
            response = await self._call_llm(messages, context)
            
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
```

---

## A.5 挑战性工程问题

### 问题：深层嵌套时的状态管理优化

**背景**: 当前的状态管理中，`ToolUseContext` 通过展开复制 (`{...toolUseContext, ...overrides}`) 来创建新上下文。当 Agent 嵌套层级很深时（如：coordinator 模式下的多层子 agent），这种模式会导致：

1. **深层嵌套时的性能问题** - 每次复制都需要展开整个对象
2. **状态一致性难以保证** - 多层嵌套可能导致状态不一致
3. **调试困难** - 难以追踪状态变更来源

### 思考题

如果是你，你会如何重新设计这个状态管理系统？考虑以下方案：

| 方案 | 优点 | 缺点 |
|------|------|------|
| **A) Immer 不可变数据结构** | 结构共享 | 性能优 | 需要额外库 |
| **B) 事件溯源（Event Sourcing）** | 完整历史可追溯 | 实现复杂度高 |
| **C) 响应式状态管理（如 RxJS）** | 自动依赖追踪 | 学习曲线陡峭 |
| **D) 基于原型的继承链** | 轻量级 | 原型链查找开销 |

### 推荐方案分析

**推荐**: 组合方案 - **A + D**

```python
# 基于结构共享的不可变状态树
class ImmutableState:
    def __init__(self, data=None, parent=None):
        self._data = data or {}
        self._parent = parent  # 原型链
        self._version = 0
    
    def with_updates(self, **kwargs):
        """创建新版本，共享未修改部分"""
        new_data = {**self._data, **kwargs}
        return ImmutableState(new_data, self)
    
    def get(self, key, default=None):
        """原型链查找"""
        if key in self._data:
            return self._data[key]
        if self._parent:
            return self._parent.get(key, default)
        return default
```

---

*本分析报告由 Qwen3.5 多视角分析团队生成 - 视角 A*
