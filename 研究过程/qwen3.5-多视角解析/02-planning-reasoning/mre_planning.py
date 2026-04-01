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
