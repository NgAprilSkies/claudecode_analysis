# 视角 C：工具集成分析 (Tool Integration)

## C.1 工具类型系统

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

### buildTool 构建器模式

```typescript
const TOOL_DEFAULTS = {
  isEnabled: () => true,
  isConcurrencySafe: (_input?: unknown) => false,
  isReadOnly: (_input?: unknown) => false,
  isDestructive: (_input?: unknown) => false,
  checkPermissions: (input, _ctx?: ToolUseContext) =>
    Promise.resolve({ behavior: 'allow', updatedInput: input }),
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

**设计优点**:
- 默认值集中管理，避免重复代码
- 类型安全，BuiltTool<D>保留输入类型的精确 arity
- .fail-closed 原则：默认不是并发安全/只读的

---

## C.2 工具编排系统

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

### 并发控制

```typescript
function getMaxToolUseConcurrency(): number {
  return (
    parseInt(process.env.CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY || '', 10) || 10
  )
}

async function* runToolsConcurrently(...) {
  yield* all(
    toolUseMessages.map(async function* (toolUse) {
      // 并发执行
      yield* runToolUse(...)
    }),
    getMaxToolUseConcurrency(),  // 限制并发数
  )
}
```

---

## C.3 权限验证流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    工具调用权限验证流程                          │
│                                                                  │
│  1. validateInput - 输入格式验证                                 │
│     - Zod schema 验证                                            │
│     - 自定义验证逻辑                                             │
│                          │                                       │
│                          ▼                                       │
│  2. checkPermissions (工具级)                                    │
│     - 工具特定权限逻辑                                           │
│     - 返回 PermissionResult                                      │
│                          │                                       │
│                          ▼                                       │
│  3. canUseTool - 通用权限检查入口                                │
│     ┌─────────────────┐                                         │
│     │ a. Deny Rules   │ - 匹配拒绝规则                           │
│     │ b. Allow Rules  │ - 匹配允许规则                           │
│     │ c. Ask Rules    │ - 匹配询问规则                           │
│     └────────┬────────┘                                         │
│              │                                                   │
│              ▼                                                   │
│  4. 权限请求对话框                                               │
│     - Always allow/deny                                          │
│     - This time only                                             │
│                          │                                       │
│                          ▼                                       │
│  5. Hook 执行                                                    │
│     - PreToolUse hooks                                           │
│     - PostToolUse hooks                                          │
│                          │                                       │
│                          ▼                                       │
│  6. 实际执行                                                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 权限规则类型

```typescript
//  Always Allow Rules
"Bash"              // 工具名匹配
"Bash(git *)"       // 子命令匹配
"mcp__server__*"    // MCP 服务器匹配

// Always Deny Rules
"Bash(rm -rf /)"    // 危险命令黑名单
"Bash(/etc/*)"      // 敏感路径访问限制

// Always Ask Rules
"Bash(sudo *)"      // 需要用户确认的操作
```

---

## C.4 工具注册机制

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

---

## C.5 Harness Engineering 评价

| 维度 | 评分 | 说明 |
|------|------|------|
| 可扩展性 | ⭐⭐⭐⭐⭐ | 新工具注册机制简单 | buildTool 默认值集中 |
| 安全边界 | ⭐⭐⭐⭐⭐ | 权限验证多层 | 输入过滤 | 沙箱机制 |
| 可观察性 | ⭐⭐⭐⭐ | 工具执行日志 | 追踪完整 | UI 渲染可定制 |
| 性能损耗 | ⭐⭐⭐⭐ | 并发工具有优化 | 权限规则匹配高效 |

---

## C.6 Python MRE - 工具集成

```python
#!/usr/bin/env python3
"""
最小化实现：工具集成系统
展示：工具注册、权限验证、编排执行
"""

from dataclasses import dataclass
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
        required = self.definition.input_schema.get('required', [])
        for field in required:
            if field not in args:
                return False, f"Missing required field: {field}"
        return True, None
    
    async def check_permissions(
        self, args: dict, context: Any
    ) -> PermissionResult:
        """权限检查"""
        return PermissionResult(PermissionBehavior.ALLOW)


class BashTool(BaseTool):
    """Bash 工具示例"""
    
    def __init__(self):
        super().__init__(ToolDefinition(
            name="Bash",
            description="Execute bash commands",
            input_schema={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"]
            },
            is_destructive=True
        ))
    
    async def execute(self, args: dict, context: Any) -> str:
        cmd = args.get('command')
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
        self, tool_name: str, args: dict, context: Any
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
        self, tool_name: str, args: dict, context: Any,
        can_use_tool_fn: Callable
    ) -> Any:
        """执行工具（带权限检查）"""
        # 1. 权限检查
        permission = await can_use_tool_fn(tool_name, args, context)
        
        if permission.behavior == PermissionBehavior.DENY:
            raise PermissionError(
                f"Tool {tool_name} denied: {permission.reason}"
            )
        
        # 2. 输入验证
        tool = self.tools.get(tool_name)
        valid, error = await tool.validate_input(args)
        if not valid:
            raise ValueError(f"Invalid input: {error}")
        
        # 3. 应用输入更新
        if permission.updated_input:
            args = permission.updated_input
        
        # 4. 执行
        return await tool.execute(args, context)
    
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
    tools = [BashTool()]
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
    context = None
    result = await orchestrator.execute_tool(
        "Bash",
        {"command": "echo hello"},
        context,
        orchestrator.can_use_tool
    )
    print(f"Result: {result}")


if __name__ == "__main__":
    asyncio.run(demo())
```

---

## C.7 挑战性工程问题

### 问题：工具系统的安全隐患

**背景**: 当前的工具系统设计存在以下安全隐患：

1. **输入验证分散**: 每个工具自己实现 `validateInput`，标准不一致
2. **权限规则冲突**: 多条规则可能产生冲突的决策
3. **工具注入风险**: 动态加载的工具可能绕过来路检查
4. **沙箱逃逸**: Bash 工具的沙箱可能不是绝对安全

### 思考题

设计一个更安全的工具执行框架，需要考虑：

1. **统一输入验证层**: 基于 Schema 的集中验证
2. **规则冲突解决**: 定义明确的优先级和解决策略
3. **工具签名验证**: 确保工具来源可信
4. **执行沙箱**: 多层隔离机制

### 推荐方案设计

```python
# 统一输入验证层
class SchemaValidator:
    def __init__(self):
        self.schemas = {}
    
    def register_schema(self, tool_name: str, schema: dict):
        """注册工具 Schema"""
        self.schemas[tool_name] = schema
    
    def validate(self, tool_name: str, args: dict) -> Tuple[bool, str]:
        """集中验证"""
        schema = self.schemas.get(tool_name)
        if not schema:
            return False, f"No schema for tool: {tool_name}"
        # JSON Schema 验证逻辑
        ...

# 规则冲突解决
class PermissionResolver:
    """权限规则解析器"""
    
    # 优先级：deny > ask > allow
    PRIORITY_ORDER = {'deny': 0, 'ask': 1, 'allow': 2}
    
    def resolve(self, rules: List[PermissionRule]) -> PermissionResult:
        """解决规则冲突"""
        if not rules:
            return PermissionResult(PermissionBehavior.ALLOW)
        
        # 按优先级排序
        rules.sort(key=lambda r: self.PRIORITY_ORDER.get(r.behavior, 2))
        
        # 返回最高优先级的规则
        highest = rules[0]
        return PermissionResult(
            highest.behavior,
            reason=f"Rule: {highest.pattern}"
        )

# 工具签名验证
class ToolSignatureVerifier:
    """工具签名验证器"""
    
    def __init__(self, trusted_signers: List[str]):
        self.trusted_signers = trusted_signers
        self.verified_tools = {}
    
    def verify_tool(self, tool_name: str, signature: str) -> bool:
        """验证工具签名"""
        # 验证逻辑：检查签名是否来自可信签名者
        ...
        return True
    
    def register_tool(self, tool_name: str, signature: str):
        """注册已验证工具"""
        if not self.verify_tool(tool_name, signature):
            raise SecurityError(f"Unverified tool: {tool_name}")
        self.verified_tools[tool_name] = True
```

---

*本分析报告由 Qwen3.5 多视角分析团队生成 - 视角 C*
