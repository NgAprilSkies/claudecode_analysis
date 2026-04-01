# 视角B-MRE.py - 任务规划系统最小复现实现
"""
Claude Code 任务规划系统简化版实现
展示了状态机、依赖注入、熔断器和Token预算等核心机制
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from typing import AsyncGenerator, Protocol, Optional, Literal, Any
from enum import Enum, auto
from collections import deque
import hashlib
import time


# ============================================================================
# 1. 类型定义与常量
# ============================================================================

class TransitionReason(Enum):
    """状态转移原因 - 用于调试和防止无限循环"""
    NEXT_TURN = auto()
    MAX_OUTPUT_TOKENS_RECOVERY = auto()
    STOP_HOOK_BLOCKING = auto()
    TOKEN_BUDGET_CONTINUATION = auto()
    TOOL_EXECUTION = auto()
    COMPLETED = auto()
    ERROR = auto()


class TerminalReason(Enum):
    """终止原因"""
    COMPLETED = "completed"
    MAX_TURNS = "max_turns"
    TOKEN_BUDGET_EXCEEDED = "token_budget_exceeded"
    CIRCUIT_BREAKER = "circuit_breaker"
    USER_INTERRUPT = "user_interrupt"
    ERROR = "error"


# ============================================================================
# 2. 数据模型
# ============================================================================

@dataclass
class Message:
    """消息基类"""
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content, **self.metadata}


@dataclass
class ToolCall:
    """工具调用"""
    tool_name: str
    input_params: dict
    call_id: str = field(default_factory=lambda: hashlib.md5(str(time.time()).encode()).hexdigest()[:8])


@dataclass
class ToolResult:
    """工具执行结果"""
    call_id: str
    output: str
    success: bool = True


@dataclass
class State:
    """
    查询循环状态 - 对应 query.ts 中的 State 类型
    每次迭代更新，用于决策下一步行动
    """
    messages: list[Message] = field(default_factory=list)
    turn_count: int = 0
    transition: Optional[TransitionReason] = None

    # 安全边界相关
    max_output_tokens_recovery_count: int = 0
    has_attempted_recovery: bool = False
    stop_hook_active: bool = False

    # Token预算
    total_tokens_used: int = 0

    def copy(self) -> State:
        """创建状态副本 - 不可变更新模式"""
        return State(
            messages=self.messages.copy(),
            turn_count=self.turn_count,
            transition=self.transition,
            max_output_tokens_recovery_count=self.max_output_tokens_recovery_count,
            has_attempted_recovery=self.has_attempted_recovery,
            stop_hook_active=self.stop_hook_active,
            total_tokens_used=self.total_tokens_used
        )


# ============================================================================
# 3. 依赖注入接口（对应 query/deps.ts）
# ============================================================================

class LLMClient(Protocol):
    """LLM客户端接口"""
    async def generate(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None
    ) -> AsyncGenerator[Message, None]:
        ...


class ToolExecutor(Protocol):
    """工具执行器接口"""
    async def execute(self, tool_call: ToolCall) -> ToolResult:
        ...

    def can_execute(self, tool_name: str) -> bool:
        ...


class TokenCounter(Protocol):
    """Token计数器接口"""
    def count(self, messages: list[Message]) -> int:
        ...


@dataclass
class QueryDeps:
    """
    查询依赖 - 对应 src/query/deps.ts
    支持测试时注入mock
    """
    llm_client: LLMClient
    tool_executor: ToolExecutor
    token_counter: TokenCounter
    uuid_gen: callable = field(default_factory=lambda: lambda: hashlib.md5(str(time.time()).encode()).hexdigest()[:12])


# ============================================================================
# 4. 安全边界组件
# ============================================================================

class TokenBudget:
    """
    Token预算管理 - 对应 src/query/tokenBudget.ts
    防止无限循环和过度消耗
    """

    COMPLETION_THRESHOLD = 0.9  # 90%预算阈值
    DIMINISHING_THRESHOLD = 500  # 收益递减阈值

    def __init__(self, total_budget: int):
        self.total_budget = total_budget
        self.continuation_count = 0
        self.last_delta = 0
        self.last_tokens = 0

    def check(self, current_tokens: int) -> dict:
        """
        检查预算状态
        返回: {'action': 'continue'|'stop', 'reason': str, ...}
        """
        pct = (current_tokens / self.total_budget) * 100
        delta = current_tokens - self.last_tokens

        # 检测收益递减（连续3次增量<阈值）
        is_diminishing = (
            self.continuation_count >= 3 and
            delta < self.DIMINISHING_THRESHOLD and
            self.last_delta < self.DIMINISHING_THRESHOLD
        )

        if is_diminishing:
            return {
                "action": "stop",
                "reason": "diminishing_returns",
                "pct": pct,
                "continuation_count": self.continuation_count
            }

        if current_tokens < self.total_budget * self.COMPLETION_THRESHOLD:
            self.continuation_count += 1
            self.last_delta = delta
            self.last_tokens = current_tokens
            return {
                "action": "continue",
                "reason": "within_budget",
                "pct": pct,
                "continuation_count": self.continuation_count,
                "nudge_message": f"Progress: {pct:.1f}% of token budget used"
            }

        return {
            "action": "stop",
            "reason": "budget_exceeded",
            "pct": pct
        }


class CircuitBreaker:
    """
    熔断器 - 对应 autoCompact.ts 中的实现
    防止连续失败后仍不断重试
    """

    def __init__(self, max_failures: int = 3):
        self.max_failures = max_failures
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None

    def record_success(self):
        """记录成功，重置计数器"""
        self.failure_count = 0

    def record_failure(self) -> bool:
        """
        记录失败
        返回: True if should trip (熔断), False otherwise
        """
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.max_failures:
            print(f"[CircuitBreaker] TRIPPED after {self.failure_count} failures")
            return True
        return False

    def can_execute(self) -> bool:
        """检查是否允许执行"""
        if self.failure_count >= self.max_failures:
            # 可选：添加冷却期后重置
            if self.last_failure_time and (time.time() - self.last_failure_time) > 60:
                self.failure_count = 0
                return True
            return False
        return True


class LoopDetector:
    """
    循环检测器 - 检测重复模式
    补充Claude Code的无限循环防护
    """

    def __init__(self, window_size: int = 5, similarity_threshold: float = 0.9):
        self.window_size = window_size
        self.similarity_threshold = similarity_threshold
        self.history: deque[str] = deque(maxlen=window_size * 2)

    def add(self, content: str):
        """添加内容到历史"""
        # 使用内容的hash作为指纹
        fingerprint = hashlib.md5(content.encode()).hexdigest()[:16]
        self.history.append(fingerprint)

    def is_looping(self) -> bool:
        """检测是否进入循环模式"""
        if len(self.history) < self.window_size * 2:
            return False

        # 检查最近N个是否与之前N个重复
        recent = list(self.history)[-self.window_size:]
        previous = list(self.history)[-self.window_size*2:-self.window_size]

        matches = sum(1 for r, p in zip(recent, previous) if r == p)
        similarity = matches / self.window_size

        return similarity >= self.similarity_threshold


# ============================================================================
# 5. 核心查询引擎
# ============================================================================

class QueryEngine:
    """
    查询引擎 - 简化版实现
    对应 src/query.ts 中的 query() 和 queryLoop()
    """

    def __init__(
        self,
        deps: QueryDeps,
        max_turns: int = 10,
        token_budget: Optional[int] = None,
        system_prompt: str = "You are a helpful assistant."
    ):
        self.deps = deps
        self.max_turns = max_turns
        self.token_budget = TokenBudget(token_budget) if token_budget else None
        self.system_prompt = system_prompt
        self.circuit_breaker = CircuitBreaker(max_failures=3)
        self.loop_detector = LoopDetector()

    async def query(
        self,
        initial_messages: list[Message]
    ) -> AsyncGenerator[dict, None]:
        """
        主查询循环 - 对应 query.ts 中的 queryLoop()

        Yields:
            各种事件：message, tool_call, tool_result, checkpoint, terminal
        """
        # 初始化状态
        state = State(messages=initial_messages.copy())

        # 查询配置快照（不可变）
        config = {
            "system_prompt": self.system_prompt,
            "max_turns": self.max_turns,
            "has_token_budget": self.token_budget is not None
        }

        yield {"type": "checkpoint", "message": "query_start", "config": config}

        while True:
            # ========== Phase 1: 安全检查 ==========

            # 检查max_turns
            if state.turn_count >= self.max_turns:
                yield {
                    "type": "terminal",
                    "reason": TerminalReason.MAX_TURNS.value,
                    "turn_count": state.turn_count
                }
                return

            # 检查熔断器
            if not self.circuit_breaker.can_execute():
                yield {
                    "type": "terminal",
                    "reason": TerminalReason.CIRCUIT_BREAKER.value,
                    "failure_count": self.circuit_breaker.failure_count
                }
                return

            # 检查Token预算
            if self.token_budget:
                token_count = self.deps.token_counter.count(state.messages)
                decision = self.token_budget.check(token_count)

                if decision["action"] == "stop":
                    yield {
                        "type": "terminal",
                        "reason": TerminalReason.TOKEN_BUDGET_EXCEEDED.value,
                        "details": decision
                    }
                    return
                elif decision["action"] == "continue":
                    yield {"type": "budget_status", **decision}

            # ========== Phase 2: 调用LLM ==========

            yield {"type": "checkpoint", "message": "llm_call_start", "turn": state.turn_count}

            assistant_message: Optional[Message] = None
            tool_calls: list[ToolCall] = []

            try:
                async for msg in self.deps.llm_client.generate(state.messages):
                    if msg.role == "assistant":
                        assistant_message = msg
                        yield {"type": "message", "message": msg}

                        # 检测循环模式
                        self.loop_detector.add(msg.content)
                        if self.loop_detector.is_looping():
                            yield {"type": "warning", "message": "Loop pattern detected!"}
                            self.circuit_breaker.record_failure()

                    # 解析工具调用（简化版）
                    if "tool_call" in msg.metadata:
                        tool_calls.append(ToolCall(**msg.metadata["tool_call"]))

            except Exception as e:
                yield {"type": "error", "message": f"LLM error: {e}"}
                if self.circuit_breaker.record_failure():
                    yield {
                        "type": "terminal",
                        "reason": TerminalReason.ERROR.value,
                        "error": str(e)
                    }
                    return
                continue

            yield {"type": "checkpoint", "message": "llm_call_end"}

            # ========== Phase 3: 处理工具调用 ==========

            if tool_calls:
                yield {"type": "checkpoint", "message": "tool_execution_start", "tool_count": len(tool_calls)}

                tool_results: list[ToolResult] = []
                for tc in tool_calls:
                    if self.deps.tool_executor.can_execute(tc.tool_name):
                        result = await self.deps.tool_executor.execute(tc)
                        tool_results.append(result)
                        yield {
                            "type": "tool_result",
                            "call_id": tc.call_id,
                            "tool_name": tc.tool_name,
                            "success": result.success,
                            "output": result.output[:200]  # 截断显示
                        }
                    else:
                        yield {"type": "error", "message": f"Unknown tool: {tc.tool_name}"}

                # 更新状态，准备下一轮
                if assistant_message:
                    state.messages.append(assistant_message)
                for tr in tool_results:
                    state.messages.append(Message(role="tool", content=tr.output, metadata={"call_id": tr.call_id}))

                state.turn_count += 1
                state.transition = TransitionReason.TOOL_EXECUTION

                self.circuit_breaker.record_success()
                yield {"type": "checkpoint", "message": "tool_execution_end"}
                continue  # 继续循环

            # ========== Phase 4: 检查是否完成 ==========

            if assistant_message:
                # 检查是否包含完成信号
                if "DONE" in assistant_message.content or "COMPLETED" in assistant_message.content:
                    yield {
                        "type": "terminal",
                        "reason": TerminalReason.COMPLETED.value,
                        "final_message": assistant_message.content,
                        "turn_count": state.turn_count
                    }
                    return

                # 没有工具调用，但也没有完成信号 - 可能需要继续
                state.messages.append(assistant_message)
                state.turn_count += 1
                state.transition = TransitionReason.NEXT_TURN

                # 注入恢复消息（类似 max_output_tokens_recovery）
                if state.max_output_tokens_recovery_count < 3:
                    recovery_msg = Message(
                        role="user",
                        content="Continue directly - no apology, pick up mid-thought if cut off."
                    )
                    state.messages.append(recovery_msg)
                    state.max_output_tokens_recovery_count += 1
                    state.transition = TransitionReason.MAX_OUTPUT_TOKENS_RECOVERY
                    yield {"type": "recovery", "message": "Injected continuation prompt"}
                else:
                    # 恢复次数用尽，强制结束
                    yield {
                        "type": "terminal",
                        "reason": TerminalReason.ERROR.value,
                        "message": "Max recovery attempts exceeded"
                    }
                    return


# ============================================================================
# 6. Mock实现（用于演示）
# ============================================================================

class MockLLMClient:
    """模拟LLM客户端"""

    def __init__(self, responses: list[str] = None):
        self.responses = responses or [
            "I'll help you with that. Let me search for relevant files.",
            "Found it! The file is located at src/main.py",
            "Here's the content: [file content]",
            "DONE"
        ]
        self.call_count = 0

    async def generate(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None
    ) -> AsyncGenerator[Message, None]:
        if self.call_count < len(self.responses):
            content = self.responses[self.call_count]
            self.call_count += 1

            # 模拟工具调用
            metadata = {}
            if "search" in content.lower():
                metadata["tool_call"] = {"tool_name": "file_search", "input_params": {"query": "main"}}

            yield Message(role="assistant", content=content, metadata=metadata)


class MockToolExecutor:
    """模拟工具执行器"""

    def __init__(self):
        self.tools = {"file_search", "read_file", "bash"}

    def can_execute(self, tool_name: str) -> bool:
        return tool_name in self.tools

    async def execute(self, tool_call: ToolCall) -> ToolResult:
        await asyncio.sleep(0.1)  # 模拟执行时间

        if tool_call.tool_name == "file_search":
            return ToolResult(
                call_id=tool_call.call_id,
                output='["src/main.py", "src/utils.py"]',
                success=True
            )
        return ToolResult(
            call_id=tool_call.call_id,
            output=f"Executed {tool_call.tool_name}",
            success=True
        )


class SimpleTokenCounter:
    """简单Token计数器（按字符估算）"""

    def count(self, messages: list[Message]) -> int:
        return sum(len(m.content) // 4 for m in messages)  # 粗略估算


# ============================================================================
# 7. 演示运行
# ============================================================================

async def main():
    """主函数 - 演示QueryEngine的使用"""

    print("=" * 60)
    print("Claude Code 任务规划系统 - 最小复现实现")
    print("=" * 60)

    # 创建依赖
    deps = QueryDeps(
        llm_client=MockLLMClient(),
        tool_executor=MockToolExecutor(),
        token_counter=SimpleTokenCounter()
    )

    # 创建引擎
    engine = QueryEngine(
        deps=deps,
        max_turns=5,
        token_budget=2000,
        system_prompt="You are a helpful coding assistant."
    )

    # 初始消息
    initial_messages = [
        Message(role="user", content="Find the main entry point of this project")
    ]

    # 运行查询
    print("\nStarting query loop...\n")

    async for event in engine.query(initial_messages):
        event_type = event.get("type")

        if event_type == "checkpoint":
            print(f"  [CHECKPOINT] {event['message']}")

        elif event_type == "message":
            msg = event["message"]
            print(f"  [ASSISTANT] {msg.content[:80]}...")

        elif event_type == "tool_result":
            print(f"  [TOOL] {event['tool_name']}: {event['success']} -> {event['output'][:50]}...")

        elif event_type == "budget_status":
            print(f"  [BUDGET] {event['pct']:.1f}% used ({event['continuation_count']} continuations)")

        elif event_type == "recovery":
            print(f"  [RECOVERY] {event['message']}")

        elif event_type == "terminal":
            print(f"\n[TERMINAL] Reason: {event['reason']}")
            if 'turn_count' in event:
                print(f"           Total turns: {event['turn_count']}")
            if 'final_message' in event:
                print(f"           Final: {event['final_message'][:100]}...")
            break

        elif event_type == "error":
            print(f"  [ERROR] {event['message']}")

    print("\n" + "=" * 60)
    print("Query completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
