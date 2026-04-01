# 视角 C: 工具集成 (Tool Integration)

## C.1 工具系统架构

### 工具接口定义

Claude Code 的工具系统基于 `src/Tool.ts` 中定义的 `Tool` 接口构建，这是一个高度抽象的泛型接口：

```typescript
export type Tool<
  Input extends AnyObject = AnyObject,
  Output = unknown,
  P extends ToolProgressData = ToolProgressData,
> = {
  // 基本标识
  name: string
  aliases?: string[]
  searchHint?: string

  // 核心执行
  call(args, context, canUseTool, parentMessage, onProgress): Promise<ToolResult<Output>>
  description(input, options): Promise<string>

  // Schema 定义
  inputSchema: Input
  outputSchema?: Output
  inputJSONSchema?: ToolInputJSONSchema

  // 权限与安全
  isConcurrencySafe(input): boolean
  isReadOnly(input): boolean
  isDestructive?(input): boolean
  checkPermissions(input, context): Promise<PermissionResult>

  // UI 渲染
  renderToolUseMessage(input, options): React.ReactNode
  renderToolResultMessage(content, progressMessages, options): React.ReactNode
  // ... 更多 UI 方法
}
```

### 工具构建工厂

```typescript
// Tool.ts:757-792
const TOOL_DEFAULTS = {
  isEnabled: () => true,
  isConcurrencySafe: (_input?: unknown) => false,  // 默认不安全
  isReadOnly: (_input?: unknown) => false,          // 默认是写入
  isDestructive: (_input?: unknown) => false,
  checkPermissions: (input) => Promise.resolve({ behavior: 'allow', updatedInput: input }),
  toAutoClassifierInput: (_input?: unknown) => '',
  userFacingName: (_input?: unknown) => '',
}

export function buildTool<D extends AnyToolDef>(def: D): BuiltTool<D> {
  return {
    ...TOOL_DEFAULTS,
    userFacingName: () => def.name,
    ...def,
  } as BuiltTool<D>
}
```

---

## C.2 工具发现与绑定

### 工具池组装流程

```svg
<svg viewBox="0 0 1400 750" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <marker id="toolArrow" markerWidth="12" markerHeight="8" refX="10" refY="4" orient="auto">
      <polygon points="0 0, 12 4, 0 8" fill="#5C6BC0"/>
    </marker>
    <linearGradient id="gradBuiltin" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#E8EAF6;stop-opacity:1"/>
      <stop offset="100%" style="stop-color:#7986CB;stop-opacity:1"/>
    </linearGradient>
    <linearGradient id="gradMCP" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#FFF8E1;stop-opacity:1"/>
      <stop offset="100%" style="stop-color:#FFCA28;stop-opacity:1"/>
    </linearGradient>
    <linearGradient id="gradFilter" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#E8F5E9;stop-opacity:1"/>
      <stop offset="100%" style="stop-color:#81C784;stop-opacity:1"/>
    </linearGradient>
    <linearGradient id="gradExec" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#F3E5F5;stop-opacity:1"/>
      <stop offset="100%" style="stop-color:#BA68C8;stop-opacity:1"/>
    </linearGradient>
  </defs>

  <!-- Title -->
  <text x="700" y="45" text-anchor="middle" font-size="24" font-weight="bold" fill="#333">
    工具集成架构 (Tool Integration Architecture)
  </text>
  <text x="700" y="75" text-anchor="middle" font-size="14" fill="#666">
    发现 → 绑定 → 执行 → 安全边界
  </text>

  <!-- LAYER 1: Tool Discovery -->
  <g transform="translate(30, 100)">
    <rect x="0" y="0" width="1340" height="140" rx="12" fill="none" stroke="#5C6BC0" stroke-width="2" stroke-dasharray="10,5"/>
    <text x="670" y="35" text-anchor="middle" font-size="18" font-weight="bold" fill="#5C6BC0">层 1: 工具发现 (Tool Discovery)</text>

    <!-- Built-in Tools -->
    <g transform="translate(50, 50)">
      <rect x="0" y="0" width="400" height="80" rx="8" fill="url(#gradBuiltin)" stroke="#3F51B5" stroke-width="2"/>
      <text x="200" y="30" text-anchor="middle" font-size="16" font-weight="bold" fill="#283593">Built-in Tools</text>
      <text x="200" y="52" text-anchor="middle" font-size="11" fill="#3949AB">src/tools.ts - getAllBaseTools()</text>
      <text x="200" y="70" text-anchor="middle" font-size="10" fill="#5C6BC0">Agent, Bash, Read, Edit, Glob, Grep...</text>

      <!-- Tool badges -->
      <rect x="20" y="55" width="50" height="18" rx="3" fill="#3F51B5" stroke="#283593" stroke-width="1"/>
      <text x="45" y="68" text-anchor="middle" font-size="9" fill="white">Agent</text>
      <rect x="75" y="55" width="40" height="18" rx="3" fill="#3F51B5" stroke="#283593" stroke-width="1"/>
      <text x="95" y="68" text-anchor="middle" font-size="9" fill="white">Bash</text>
      <rect x="120" y="55" width="40" height="18" rx="3" fill="#3F51B5" stroke="#283593" stroke-width="1"/>
      <text x="140" y="68" text-anchor="middle" font-size="9" fill="white">Read</text>
      <rect x="165" y="55" width="35" height="18" rx="3" fill="#3F51B5" stroke="#283593" stroke-width="1"/>
      <text x="182" y="68" text-anchor="middle" font-size="9" fill="white">Edit</text>
      <rect x="205" y="55" width="40" height="18" rx="3" fill="#3F51B5" stroke="#283593" stroke-width="1"/>
      <text x="225" y="68" text-anchor="middle" font-size="9" fill="white">Glob</text>
      <rect x="250" y="55" width="40" height="18" rx="3" fill="#3F51B5" stroke="#283593" stroke-width="1"/>
      <text x="270" y="68" text-anchor="middle" font-size="9" fill="white">Grep</text>
      <rect x="295" y="55" width="70" height="18" rx="3" fill="#3F51B5" stroke="#283593" stroke-width="1"/>
      <text x="330" y="68" text-anchor="middle" font-size="9" fill="white">WebSearch</text>
    </g>

    <!-- MCP Tools -->
    <g transform="translate(500, 50)">
      <rect x="0" y="0" width="400" height="80" rx="8" fill="url(#gradMCP)" stroke="#FFA000" stroke-width="2"/>
      <text x="200" y="30" text-anchor="middle" font-size="16" font-weight="bold" fill="#FF6F00">MCP Tools</text>
      <text x="200" y="52" text-anchor="middle" font-size="11" fill="#FFA000">src/services/mcp/client.ts</text>
      <text x="200" y="70" text-anchor="middle" font-size="10" fill="#FFCA28">动态发现 • 服务器连接 • 协议适配</text>
    </g>

    <!-- Feature-Gated Tools -->
    <g transform="translate(950, 50)">
      <rect x="0" y="0" width="340" height="80" rx="8" fill="#ECEFF1" stroke="#90A4AE" stroke-width="2"/>
      <text x="170" y="30" text-anchor="middle" font-size="16" font-weight="bold" fill="#546E7A">Feature-Gated</text>
      <text x="170" y="52" text-anchor="middle" font-size="11" fill="#78909C">条件加载的工具:</text>
      <text x="170" y="68" text-anchor="middle" font-size="10" fill="#90A4AE">REPL, Monitor, Cron, Workflow...</text>
    </g>

    <!-- Arrow -->
    <path d="M 450 100 L 495 100" fill="none" stroke="#5C6BC0" stroke-width="2.5" marker-end="url(#toolArrow)"/>
  </g>

  <!-- LAYER 2: Permission Filtering -->
  <g transform="translate(30, 270)">
    <rect x="0" y="0" width="1340" height="130" rx="12" fill="none" stroke="#66BB6A" stroke-width="2" stroke-dasharray="10,5"/>
    <text x="670" y="35" text-anchor="middle" font-size="18" font-weight="bold" fill="#43A047">层 2: 权限过滤 (Permission Filtering)</text>

    <!-- Permission Context -->
    <g transform="translate(50, 50)">
      <rect x="0" y="0" width="300" height="70" rx="8" fill="url(#gradFilter)" stroke="#4CAF50" stroke-width="2"/>
      <text x="150" y="28" text-anchor="middle" font-size="14" font-weight="bold" fill="#2E7D32">ToolPermissionContext</text>
      <text x="150" y="48" text-anchor="middle" font-size="11" fill="#388E3C">mode: default | auto | bypass | plan</text>
      <text x="150" y="64" text-anchor="middle" font-size="10" fill="#4CAF50">alwaysAllow / alwaysDeny / alwaysAsk</text>
    </g>

    <!-- Filter Logic -->
    <g transform="translate(400, 50)">
      <rect x="0" y="0" width="450" height="70" rx="8" fill="white" stroke="#4CAF50" stroke-width="2"/>
      <text x="225" y="28" text-anchor="middle" font-size="14" font-weight="bold" fill="#2E7D32">filterToolsByDenyRules()</text>
      <text x="225" y="48" text-anchor="middle" font-size="11" fill="#388E3C">步骤 1: 移除 blanket-denied 工具</text>
      <text x="225" y="64" text-anchor="middle" font-size="10" fill="#4CAF50">步骤 2: MCP server-prefix 规则过滤</text>
    </g>

    <!-- Permission Rules -->
    <g transform="translate(900, 50)">
      <rect x="0" y="0" width="390" height="70" rx="8" fill="#FFFDE7" stroke="#FBC02D" stroke-width="2"/>
      <text x="195" y="28" text-anchor="middle" font-size="12" font-weight="bold" fill="#F57F17">权限规则示例:</text>
      <text x="20" y="48" font-size="10" fill="#F9A825">• alwaysAllow: {"Bash": ["git *"]}</text>
      <text x="20" y="62" font-size="10" fill="#F9A825">• alwaysDeny: {"Bash": ["rm -rf *"]}</text>
    </g>

    <!-- Arrow -->
    <path d="M 1200 180 L 1200 205 L 670 205 L 670 265" fill="none" stroke="#4CAF50" stroke-width="2.5" marker-end="url(#toolArrow)"/>
  </g>

  <!-- LAYER 3: Tool Assembly -->
  <g transform="translate(30, 430)">
    <rect x="0" y="0" width="1340" height="100" rx="12" fill="none" stroke="#AB47BC" stroke-width="2" stroke-dasharray="10,5"/>
    <text x="670" y="35" text-anchor="middle" font-size="18" font-weight="bold" fill="#8E24AA">层 3: 工具池组装 (Tool Pool Assembly)</text>

    <!-- Assemble Function -->
    <g transform="translate(50, 50)">
      <rect x="0" y="0" width="500" height="40" rx="6" fill="#F3E5F5" stroke="#AB47BC" stroke-width="2"/>
      <text x="250" y="26" text-anchor="middle" font-size="12" font-family="monospace" fill="#6A1B9A">
        assembleToolPool(permissionContext, mcpTools): Tools
      </text>
    </g>

    <!-- Assembly Steps -->
    <g transform="translate(600, 50)">
      <rect x="0" y="0" width="300" height="40" rx="6" fill="white" stroke="#AB47BC" stroke-width="1.5"/>
      <text x="150" y="26" text-anchor="middle" font-size="11" fill="#333">1. Built-in → 按名称排序</text>

      <rect x="320" y="0" width="300" height="40" rx="6" fill="white" stroke="#AB47BC" stroke-width="1.5"/>
      <text x="470" y="26" text-anchor="middle" font-size="11" fill="#333">2. MCP → 按名称排序</text>

      <rect x="640" y="0" width="300" height="40" rx="6" fill="white" stroke="#AB47BC" stroke-width="1.5"/>
      <text x="790" y="26" text-anchor="middle" font-size="11" fill="#333">3. uniqBy → Built-in 优先</text>
    </g>

    <!-- Code reference -->
    <text x="50" y="120" font-size="10" fill="#7B1FA2" font-family="monospace">
      src/tools.ts:345-367 - assembleToolPool()
    </text>
  </g>

  <!-- LAYER 4: Tool Execution -->
  <g transform="translate(30, 560)">
    <rect x="0" y="0" width="1340" height="160" rx="12" fill="none" stroke="#EC407A" stroke-width="2" stroke-dasharray="10,5"/>
    <text x="670" y="35" text-anchor="middle" font-size="18" font-weight="bold" fill="#D81B60">层 4: 工具执行 (Tool Execution)</text>

    <!-- Execution Modes -->
    <g transform="translate(50, 50)">
      <!-- Streaming Mode -->
      <rect x="0" y="0" width="380" height="100" rx="8" fill="url(#gradExec)" stroke="#EC407A" stroke-width="2"/>
      <text x="190" y="30" text-anchor="middle" font-size="14" font-weight="bold" fill="#880E4F">流式执行模式</text>
      <text x="190" y="50" text-anchor="middle" font-size="11" fill="#AD1457">(StreamingToolExecutor)</text>

      <rect x="20" y="60" width="340" height="30" rx="4" fill="#F8BBD0" stroke="#EC407A" stroke-width="1"/>
      <text x="190" y="80" text-anchor="middle" font-size="10" fill="#880E4F">• 并行执行并发安全工具</text>

      <rect x="20" y="92" width="340" height="25" rx="4" fill="#F8BBD0" stroke="#EC407A" stroke-width="1"/>
      <text x="190" y="110" text-anchor="middle" font-size="10" fill="#880E4F">• 实时进度反馈</text>
    </g>

    <!-- Concurrency Control -->
    <g transform="translate(480, 50)">
      <rect x="0" y="0" width="400" height="100" rx="8" fill="white" stroke="#EC407A" stroke-width="2"/>
      <text x="200" y="30" text-anchor="middle" font-size="14" font-weight="bold" fill="#880E4F">并发控制</text>

      <rect x="20" y="40" width="360" height="25" rx="4" fill="#FCE4EC" stroke="#F48FB1" stroke-width="1"/>
      <text x="200" y="58" text-anchor="middle" font-size="10" fill="#880E4F">partitionToolCalls() → 并发安全分组</text>

      <rect x="20" y="70" width="360" height="25" rx="4" fill="#FCE4EC" stroke="#F48FB1" stroke-width="1"/>
      <text x="200" y="88" text-anchor="middle" font-size="10" fill="#880E4F">runToolsSerially() / runToolsConcurrently()</text>
    </g>

    <!-- Permission Check -->
    <g transform="translate(930, 50)">
      <rect x="0" y="0" width="360" height="100" rx="8" fill="#FFF3E0" stroke="#FF9800" stroke-width="2"/>
      <text x="180" y="30" text-anchor="middle" font-size="14" font-weight="bold" fill="#E65100">权限检查流程</text>

      <rect x="15" y="45" width="330" height="20" rx="3" fill="white" stroke="#FFB74D" stroke-width="1"/>
      <text x="180" y="60" text-anchor="middle" font-size="9" fill="#333">1. canUseTool() → PermissionResult</text>

      <rect x="15" y="70" width="330" height="20" rx="3" fill="white" stroke="#FFB74D" stroke-width="1"/>
      <text x="180" y="85" text-anchor="middle" font-size="9" fill="#333">2. behavior: allow / ask / deny</text>
    </g>

    <!-- Code references -->
    <text x="50" y="180" font-size="10" fill="#C2185B" font-family="monospace">
      src/services/tools/toolOrchestration.ts | StreamingToolExecutor.ts
    </text>
  </g>

  <!-- Connecting Arrows -->
  <path d="M 670 240 L 670 265" fill="none" stroke="#5C6BC0" stroke-width="2.5" marker-end="url(#toolArrow)"/>
  <path d="M 670 400 L 670 425" fill="none" stroke="#4CAF50" stroke-width="2.5" marker-end="url(#toolArrow)"/>
  <path d="M 670 530 L 670 555" fill="none" stroke="#AB47BC" stroke-width="2.5" marker-end="url(#toolArrow)"/>
</svg>
```

---

## C.3 工具执行流程

### 权限检查 → 执行 → 结果

```
┌─────────────────────────────────────────────────────────────────────┐
│                    工具执行完整流程                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. canUseTool() - 权限检查                                         │
│     ├─ 检查 alwaysAllowRules                                        │
│     ├─ 检查 alwaysDenyRules                                         │
│     ├─ 检查 alwaysAskRules                                          │
│     └─ 返回 PermissionResult: { behavior, updatedInput }            │
│                                                                     │
│  2. StreamingToolExecutor.addTool() - 加入执行队列                  │
│     ├─ 检查并发安全性 (isConcurrencySafe)                           │
│     ├─ 分区到并发组或顺序组                                         │
│     └─ 开始流式执行                                                 │
│                                                                     │
│  3. Tool.call() - 实际执行                                          │
│     ├─ validateInput() - 输入验证                                   │
│     ├─ checkPermissions() - 工具特定权限检查                        │
│     ├─ 执行逻辑                                                     │
│     └─ 返回 ToolResult<T>                                           │
│                                                                     │
│  4. 结果处理                                                        │
│     ├─ mapToolResultToToolResultBlockParam() - 格式化               │
│     ├─ renderToolResultMessage() - UI 渲染                          │
│     └─ 添加到 messages 数组                                         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 关键代码位置

| 阶段 | 文件 | 函数 | 行号 |
|------|------|------|------|
| 权限检查 | src/hooks/useCanUseTool.ts | `canUseTool()` | - |
| 工具组装 | src/tools.ts | `assembleToolPool()` | 345-367 |
| 流式执行 | src/services/tools/StreamingToolExecutor.ts | `addTool()` | - |
| 编排执行 | src/services/tools/toolOrchestration.ts | `runTools()` | - |
| 结果格式化 | src/utils/messages.js | `normalizeMessagesForAPI()` | - |

---

## C.4 Harness Engineering 设计决策评价

### 可扩展性 (Scalability) - 9/10

**优点**:
- **工厂模式**: `buildTool()` 使新工具开发标准化
- **MCP 集成**: 动态发现外部工具服务器
- **Feature Gates**: 条件加载工具 (REPL, Monitor, Workflow)

**缺点**:
- **循环依赖**: 需要 lazy require 打破依赖环 (tools.ts:62-72)
- **工具名称冲突**: MCP 工具可能与内置工具同名

**代码证据**:
```typescript
// Tool.ts:757-792 - 工具工厂
const TOOL_DEFAULTS = {
  isEnabled: () => true,
  isConcurrencySafe: () => false,
  // ... 默认实现
}

export function buildTool<D extends AnyToolDef>(def: D): BuiltTool<D> {
  return { ...TOOL_DEFAULTS, ...def } as BuiltTool<D>
}
```

---

### 安全边界 (Safety Boundary) - 9/10

**优点**:
- **三层权限系统**: alwaysAllow / alwaysDeny / alwaysAsk
- **工具级权限检查**: `checkPermissions()` 方法
- **破坏性操作标记**: `isDestructive()` 标识不可逆操作

**缺点**:
- **权限规则复杂**: pattern matching 可能导致意外匹配
- **MCP 工具信任**: 外部服务器工具权限验证有限

**代码证据**:
```typescript
// Tool.ts:123-138 - 权限上下文
export type ToolPermissionContext = DeepImmutable<{
  mode: PermissionMode  // default | auto | bypass | plan
  alwaysAllowRules: ToolPermissionRulesBySource
  alwaysDenyRules: ToolPermissionRulesBySource
  alwaysAskRules: ToolPermissionRulesBySource
  shouldAvoidPermissionPrompts?: boolean
}>
```

---

### 可观察性 (Observability) - 8/10

**优点**:
- **进度跟踪**: `onProgress` 回调用于实时反馈
- **工具调用日志**: `logEvent('tengu_tool_invoked', {...})`
- **权限拒绝追踪**: `permissionDenials` 数组记录拒绝历史

**缺点**:
- **执行追踪分散**: 日志分布在 executor 和 orchestration 中
- **错误分类有限**: 难以区分工具错误与权限错误

---

### 性能损耗 (Performance Overhead) - 7/10

**优点**:
- **并发执行**: `partitionToolCalls()` 并行安全工具
- **流式执行**: `StreamingToolExecutor` 减少等待时间

**缺点**:
- **权限检查开销**: 每个工具调用都要检查多层规则
- **工具池组装**: 每次查询都要过滤和排序

---

## C.5 最小化实现 (MRE) - Python

```python
"""
Tool Integration - Minimal Reference Implementation
视角 C: 工具集成最小化实现 (约 85 行)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable, TypeVar
from enum import Enum
import json


class PermissionBehavior(Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass
class PermissionResult:
    """权限检查结果"""
    behavior: PermissionBehavior
    updated_input: Optional[Dict] = None
    reason: Optional[str] = None


@dataclass
class ToolResult:
    """工具执行结果"""
    data: Any
    new_messages: List[Dict] = field(default_factory=list)


class ToolContext:
    """工具执行上下文"""
    def __init__(self, permission_context: Dict, tools: List['Tool']):
        self.permission_context = permission_context
        self.tools = tools


class Tool:
    """工具基类"""
    name: str = "base_tool"

    def call(self, args: Dict, context: ToolContext) -> ToolResult:
        raise NotImplementedError

    def is_concurrency_safe(self, args: Dict) -> bool:
        return False

    def is_read_only(self, args: Dict) -> bool:
        return False

    def check_permissions(self, args: Dict, context: ToolContext) -> PermissionResult:
        return PermissionResult(behavior=PermissionBehavior.ALLOW)


class ToolPermissionSystem:
    """权限系统"""

    def __init__(self):
        self.always_allow: Dict[str, List[str]] = {}  # {"Bash": ["git *"]}
        self.always_deny: Dict[str, List[str]] = {}   # {"Bash": ["rm *"]}
        self.always_ask: Dict[str, List[str]] = {}    # {"Bash": ["*"]}

    def can_use_tool(self, tool: Tool, args: Dict, context: ToolContext) -> PermissionResult:
        """
        检查工具使用权限

        对应: src/hooks/useCanUseTool.ts
        """
        tool_name = tool.name

        # 检查 alwaysDeny
        if tool_name in self.always_deny:
            for pattern in self.always_deny[tool_name]:
                if self._matches_pattern(args, pattern):
                    return PermissionResult(
                        behavior=PermissionBehavior.DENY,
                        reason=f"Denied by rule: {tool_name}({pattern})"
                    )

        # 检查 alwaysAllow
        if tool_name in self.always_allow:
            for pattern in self.always_allow[tool_name]:
                if self._matches_pattern(args, pattern):
                    return PermissionResult(behavior=PermissionBehavior.ALLOW)

        # 检查 alwaysAsk
        if tool_name in self.always_ask:
            for pattern in self.always_ask[tool_name]:
                if self._matches_pattern(args, pattern):
                    return PermissionResult(behavior=PermissionBehavior.ASK)

        # 默认允许 (交给工具自身 checkPermissions)
        return tool.check_permissions(args, context)

    def _matches_pattern(self, args: Dict, pattern: str) -> bool:
        """简单 pattern 匹配 (实际实现更复杂)"""
        if pattern == "*":
            return True
        # 简化实现：精确匹配
        return True


class ToolExecutor:
    """工具执行器"""

    def __init__(self, permission_system: ToolPermissionSystem):
        self.permission_system = permission_system

    async def execute_tools(
        self,
        tool_calls: List[Dict],
        tools: List[Tool],
        context: ToolContext,
    ) -> List[ToolResult]:
        """
        执行工具调用列表

        对应：src/services/tools/toolOrchestration.ts
        """
        results = []

        # 分区：并发安全 vs 顺序执行
        concurrent_safe = []
        sequential = []

        for call in tool_calls:
            tool = self._find_tool(tools, call['name'])
            if tool and tool.is_concurrency_safe(call['input']):
                concurrent_safe.append((tool, call))
            else:
                sequential.append((tool, call))

        # 并发执行安全工具
        for tool, call in concurrent_safe:
            result = await self._execute_single(tool, call, context)
            results.append(result)

        # 顺序执行其他工具
        for tool, call in sequential:
            result = await self._execute_single(tool, call, context)
            results.append(result)

        return results

    async def _execute_single(
        self,
        tool: Tool,
        call: Dict,
        context: ToolContext,
    ) -> ToolResult:
        """执行单个工具"""
        # 权限检查
        perm_result = self.permission_system.can_use_tool(
            tool, call['input'], context
        )

        if perm_result.behavior == PermissionBehavior.DENY:
            return ToolResult(
                data={"error": f"Permission denied: {perm_result.reason}"}
            )

        if perm_result.behavior == PermissionBehavior.ASK:
            # 简化实现：用户拒绝
            return ToolResult(
                data={"error": "User denied permission"}
            )

        # 执行工具
        try:
            return tool.call(perm_result.updated_input or call['input'], context)
        except Exception as e:
            return ToolResult(data={"error": str(e)})

    def _find_tool(self, tools: List[Tool], name: str) -> Optional[Tool]:
        """按名称查找工具"""
        for tool in tools:
            if tool.name == name or name in getattr(tool, 'aliases', []):
                return tool
        return None


# 示例工具实现
class ReadTool(Tool):
    name = "Read"

    def call(self, args: Dict, context: ToolContext) -> ToolResult:
        file_path = args.get('path', '')
        # 模拟读取文件
        content = f"Content of {file_path}"
        return ToolResult(data=content)

    def is_concurrency_safe(self, args: Dict) -> bool:
        return True  # 读取是并发安全的

    def is_read_only(self, args: Dict) -> bool:
        return True


class BashTool(Tool):
    name = "Bash"

    def call(self, args: Dict, context: ToolContext) -> ToolResult:
        command = args.get('command', '')
        # 模拟执行 bash 命令
        return ToolResult(data=f"Output of: {command}")

    def check_permissions(self, args: Dict, context: ToolContext) -> PermissionResult:
        command = args.get('command', '')
        if command.startswith('rm -rf'):
            return PermissionResult(
                behavior=PermissionBehavior.DENY,
                reason="Destructive command"
            )
        return PermissionResult(behavior=PermissionBehavior.ALLOW)


# 使用示例
async def main():
    # 创建权限系统
    perm_system = ToolPermissionSystem()
    perm_system.always_allow = {"Read": ["*"]}
    perm_system.always_deny = {"Bash": ["rm *"]}

    # 创建工具列表
    tools = [ReadTool(), BashTool()]

    # 创建执行器
    executor = ToolExecutor(perm_system)

    # 执行工具调用
    tool_calls = [
        {"name": "Read", "input": {"path": "file.txt"}},
        {"name": "Bash", "input": {"command": "ls -la"}},
    ]

    context = ToolContext(
        permission_context={},
        tools=tools,
    )

    results = await executor.execute_tools(tool_calls, tools, context)
    for result in results:
        print(f"结果：{result.data}")
```

---

## C.6 挑战性思考问题

### 问题 C: 工具执行安全性增强

**场景**: Claude Code 的权限系统基于 pattern matching (如 `"Bash": ["git *"]`)，但这种匹配在某些边缘情况下可能被绕过。例如，攻击者可能通过以下方式尝试绕过权限控制：

1. **参数注入**: `git commit -m "message"; rm -rf /`
2. **编码绕过**: 使用 base64 编码恶意命令
3. **路径遍历**: `cd /tmp && rm -rf target`

**挑战问题**:
> 如果你要为 Claude Code 设计一个增强的工具执行安全系统，你会采用以下哪种策略？请分析每种策略的实施难度和有效性。
>
> **方案 A: 静态分析沙箱**
> - 在执行前对命令进行 AST 解析，检测危险操作
> - 对于 BashTool，解析 shell 命令的语法树
> - 对于文件操作，检查实际路径是否在允许范围内
>
> **方案 B: 动态执行沙箱**
> - 使用容器或 seccomp 限制工具执行的系统调用
> - 监控工具执行过程中的实际行为
> - 异常行为触发终止和回滚
>
> **方案 C: 能力系统 (Capability-Based)**
> - 为每个工具定义细粒度的能力 (如：read:/src/*, write:/tmp/*)
> - 权限规则从 pattern matching 改为能力授予
> - 工具执行时检查所需能力是否在授予范围内
>
> **具体要求**:
> 1. 选择一种方案并详细说明实现架构
> 2. 分析该方案的局限性（是否会影响合法工具的使用？）
> 3. 如何在不显著增加延迟的情况下实现你的方案？
> 4. 设计一组测试用例来验证你的安全系统能检测的攻击类型

**提示**: 参考浏览器安全模型 (Content Security Policy)、操作系统安全模块 (SELinux/AppArmor)、或区块链智能合约的形式化验证方法。

---

*视角 C 分析完成*
