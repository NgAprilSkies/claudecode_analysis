# 视角 B：任务规划分析 (Planning & Reasoning)

## B.1 决策架构

Claude Code 的决策系统采用多层架构：

```
┌─────────────────────────────────────────────────────────────────┐
│                    决策层次架构                                  │
│                                                                  │
│  Layer 0: 用户输入解析                                           │
│  - getCommands() - 命令识别                                      │
│  - 意图分类                                                      │
│                                                                  │
│  Layer 1: LLM 决策层                                             │
│  - 任务拆解 (通过 LLM)                                           │
│  - 工具选择 (通过 ToolSearch)                                    │
│  - 参数生成                                                      │
│                                                                  │
│  Layer 2: 验证层                                                 │
│  - validateInput() - 输入验证                                    │
│  - checkPermissions() - 权限检查                                 │
│  - classifierDecision - 分类器决策                               │
│                                                                  │
│  Layer 3: 执行层                                                 │
│  - 并发安全工具 → 并行执行                                       │
│  - 非安全工具 → 串行执行                                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## B.2 任务拆解流程

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
    
    // 6. 权限检查
    const permissionResult = await canUseTool(tool, input)
    
    // 7. 实际执行
    const result = await tool.call(input, context, canUseTool)
  }
  
  // 8. 结果处理和下一轮决策
}
```

## B.3 动态调整机制

通过 9 个 continue 站点实现决策路径的动态调整：

| 触发条件 | 决策类型 | 处理逻辑 |
|----------|----------|----------|
| 工具执行成功 | CONTINUE | 添加结果→继续下一轮 |
| 工具执行失败 | ERROR | 错误消息→返回/重试 |
| Token 超限 | COMPACT | 触发压缩→重试 |
| 用户中断 | TERMINATE | 清理→终止 |
| max_output_tokens | RECOVER | 增加输出 token→重试 |
| Hook 激活 | PAUSE | 等待 Hook 完成 |
| 缓存中断 | RESTART | 重新构建查询 |
| 反应式压缩 | COMPACT | API 触发压缩 |
| 正常完成 | RETURN | 返回结果 |

### Token 预算管理

```typescript
// autoCompact.ts 中的阈值定义
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
  return contextWindow - reservedTokensForSummary
}
```

## B.4 Harness Engineering 评价

| 维度 | 评分 | 说明 |
|------|------|------|
| 可扩展性 | ⭐⭐⭐⭐ | 新增决策路径需修改核心循环 |
| 安全边界 | ⭐⭐⭐⭐⭐ | 多层验证 | 分类器 | Hook 拦截 |
| 可观察性 | ⭐⭐⭐⭐ | 9 个决策路径可追踪 | 日志完善 |
| 性能损耗 | ⭐⭐⭐⭐ | LLM 调用优化 | 并发工具执行 |

---

## B.5 Python MRE - 任务规划

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
    tool_calls: list = field(default_factory=list)


class DecisionEngine:
    """决策引擎 - 核心规划逻辑"""
    
    def __init__(self, llm_client: Any, tools: dict, max_turns: int = 10):
        self.llm_client = llm_client
        self.tools = tools
        self.max_turns = max_turns
        self._turn_count = 0
        
    async def plan_and_execute(
        self,
        initial_messages: list,
        dynamic_adjustment: bool = True
    ) -> str:
        """规划并执行任务"""
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
                    tool_call, messages, dynamic_adjustment
                )
                
                # 4. 根据决策调整路径
                if decision.decision_type == DecisionType.TERMINATE:
                    return result
                elif decision.decision_type == DecisionType.COMPACT:
                    messages = await self._compact_context(messages)
                    continue
                elif decision.decision_type == DecisionType.RECOVER:
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
        self, tool_call: ToolCall, messages: list, dynamic_adjustment: bool
    ) -> tuple:
        """带决策的执行"""
        tool = self.tools.get(tool_call.name)
        
        if not tool:
            return None, Decision(
                DecisionType.ERROR,
                f"Tool not found: {tool_call.name}"
            )
        
        try:
            # 验证
            if hasattr(tool, 'validate'):
                valid, error = await tool.validate(tool_call.args)
                if not valid:
                    return None, Decision(
                        DecisionType.ERROR,
                        f"Validation failed: {error}"
                    )
            
            # 执行
            result = await tool.execute(tool_call.args)
            
            # 动态调整决策
            if dynamic_adjustment:
                decision = await self._make_decision(result, messages)
                return result, decision
                
            return result, Decision(DecisionType.CONTINUE, "OK")
            
        except Exception as e:
            return None, Decision(DecisionType.RECOVER, str(e))
    
    async def _make_decision(self, result: Any, messages: list) -> Decision:
        """根据执行结果做决策"""
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
        return LLMResponse(content="Processing...", tool_calls=[])
    
    async def _compact_context(self, messages: list) -> list:
        """压缩上下文"""
        print("Compacting context...")
        return messages[-5:]  # 简化：只保留最近 5 条


# 工具定义
class Tool:
    def __init__(self, name: str, execute_fn: Callable):
        self.name = name
        self._execute = execute_fn
        
    async def execute(self, args: dict) -> Any:
        return await self._execute(args)
    
    async def validate(self, args: dict) -> tuple:
        return True, None


# 使用示例
async def demo():
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
    
    engine = DecisionEngine(
        llm_client=None,
        tools=tools,
        max_turns=5
    )
    
    messages = [{'role': 'user', 'content': 'Check the project'}]
    result = await engine.plan_and_execute(messages)
    print(f"Final result: {result}")


if __name__ == "__main__":
    asyncio.run(demo())
```

---

## B.6 挑战性工程问题

### 问题：决策逻辑分散，难以全局理解

**背景**: 当前的决策系统有 9 个 continue 站点，每个站点代表一种决策路径。这种设计的缺点是：

1. 决策逻辑分散，难以全局理解
2. 新增决策路径需要修改核心循环
3. 决策之间的优先级关系不明确

### 思考题

如果要设计一个更加模块化、可扩展的决策系统，你会采用什么架构模式？

| 方案 | 优点 | 缺点 |
|------|------|------|
| **状态机模式** | 状态显式化 | 转换复杂 |
| **责任链模式** | 链式传递 | 性能开销 |
| **策略模式** | 可插拔 | 配置复杂 |
| **规则引擎** | 灵活配置 | 实现复杂 |

### 推荐方案设计

```python
# 基于责任链的决策处理器
class DecisionHandler:
    def __init__(self):
        self.handlers = []
        self.priorities = {}
    
    def register(self, handler, priority=0, conditions=None):
        """注册决策处理器"""
        self.handlers.append((priority, handler, conditions or []))
        self.handlers.sort(key=lambda x: x[0], reverse=True)
    
    async def process(self, context):
        """处理决策"""
        for priority, handler, conditions in self.handlers:
            if all(c.check(context) for c in conditions):
                decision = await handler.handle(context)
                if decision:
                    return decision
        return None

# 使用示例
engine = DecisionEngine()
engine.register(
    CompactHandler(),
    priority=10,
    conditions=[TokenThresholdCondition(threshold=0.8)]
)
engine.register(
    ErrorHandler(),
    priority=5,
    conditions=[ErrorCondition()]
)
```

---

*本分析报告由 Qwen3.5 多视角分析团队生成 - 视角 B*
