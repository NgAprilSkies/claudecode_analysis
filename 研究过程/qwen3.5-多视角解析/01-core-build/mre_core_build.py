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


# 使用示例
async def demo():
    class SimpleTool:
        def __init__(self, name):
            self.name = name
        async def execute(self, args, context):
            return f"Executed {self.name}"

    agent = Agent(
        system_prompt="You are a helpful assistant",
        tools=[SimpleTool("bash"), SimpleTool("read")]
    )

    result = await agent.run([{"role": "user", "content": "Hello"}])
    print(f"Result: {result}")
    print(f"Status: {agent.status}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(demo())
