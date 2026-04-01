#!/usr/bin/env python3
"""
Claude Code 任务规划核心原理最小化实现
复现 query loop, LLM 调用模拟, 任务拆解逻辑, Plan mode 状态机

根据 Claude Code 源码分析结果:
- QueryEngine.ts: 查询引擎核心
- query.ts: 查询循环实现
- claude.ts: LLM API 调用
- plan/plan.tsx: Plan mode 实现
- ultraplan.tsx: Ultra planning 机制
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, Generator, List, Optional, Any
from collections import defaultdict
import time


# ==================== 数据结构 ====================

class MessageType(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL_RESULT = "tool_result"


@dataclass
class Message:
    """消息结构，对应 Claude Code 的 Message 类型"""
    type: MessageType
    content: str
    tool_use_id: Optional[str] = None
    tool_name: Optional[str] = None
    tool_input: Optional[Dict] = None
    stop_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class Tool:
    """工具定义，对应 Tool 类型"""
    name: str
    description: str
    handler: Callable[[Dict], str]
    input_schema: Dict[str, Any]


@dataclass
class QueryContext:
    """查询上下文，对应 ToolUseContext"""
    messages: List[Message] = field(default_factory=list)
    tools: List[Tool] = field(default_factory=list)
    mode: str = "default"  # default, plan
    max_turns: int = 10
    current_turn: int = 0


@dataclass
class State:
    """循环状态，对应 query.ts 中的 State 类型"""
    messages: List[Message] = field(default_factory=list)
    tool_use_context: QueryContext = field(default_factory=QueryContext)
    turn_count: int = 0
    max_output_tokens_recovery_count: int = 0
    transition_reason: Optional[str] = None
    stop_hook_active: bool = False


# ==================== LLM 模拟 ====================

class MockLLM:
    """模拟 Claude API 的 LLM"""

    def __init__(self, model: str = "claude-opus-4-6"):
        self.model = model
        self.call_count = 0

    def chat(self, messages: List[Message], tools: List[Tool]) -> Message:
        """
        模拟 LLM 调用
        复现 claude.ts 中的 queryModel 流程
        """
        self.call_count += 1

        last_message = messages[-1]

        # 简单的工具调用模拟
        if "read" in last_message.content.lower() and self._has_tool(tools, "read_file"):
            return Message(
                type=MessageType.ASSISTANT,
                content="",
                tool_name="read_file",
                tool_input={"path": "example.txt"},
                stop_reason="tool_use"
            )

        if "summarize" in last_message.content.lower():
            return Message(
                type=MessageType.ASSISTANT,
                content="Here is a summary of the work done.",
                stop_reason="end_turn"
            )

        # 默认响应
        return Message(
            type=MessageType.ASSISTANT,
            content="I understand. Let me help you with that.",
            stop_reason="end_turn"
        )

    def _has_tool(self, tools: List[Tool], name: str) -> bool:
        return any(t.name == name for t in tools)


# ==================== Plan Mode 状态机 ====================

class PlanMode(Enum):
    """Plan mode 状态，复现 plan.tsx 的状态转换"""
    DEFAULT = "default"
    PLAN = "plan"
    PLAN_OPEN = "plan_open"


class PlanModeStateMachine:
    """Plan mode 状态机，复现 prepareContextForPlanMode 逻辑"""

    def __init__(self):
        self.current_mode = PlanMode.DEFAULT
        self.plan_content = ""

    def enable_plan_mode(self) -> bool:
        """切换到 Plan 模式"""
        if self.current_mode != PlanMode.PLAN:
            self.current_mode = PlanMode.PLAN
            print(f"[PlanMode] Transition: {PlanMode.DEFAULT.value} → {PlanMode.PLAN.value}")
            return True
        return False

    def set_plan_content(self, content: str):
        """设置计划内容"""
        self.plan_content = content
        print(f"[PlanMode] Plan updated: {content[:50]}...")

    def is_plan_mode(self) -> bool:
        """检查是否为 Plan 模式"""
        return self.current_mode == PlanMode.PLAN


# ==================== Ultra Planning 状态机 ====================

class UltraPlanPhase(Enum):
    """Ultra Planning 阶段，复现 ccrSession.ts 的状态"""
    RUNNING = "running"
    NEEDS_INPUT = "needs_input"
    PLAN_READY = "plan_ready"


class ExitPlanModeScanner:
    """
    ExitPlanMode 扫描器
    复现 ccrSession.ts 中的扫描逻辑
    """

    def __init__(self):
        self.exit_plan_calls: List[str] = []
        self.tool_results: Dict[str, Any] = {}
        self.rejected_ids: set = set()
        self.terminated = False
        self.ever_seen_pending = False

    @property
    def has_pending_plan(self) -> bool:
        """检查是否有待处理的计划"""
        for call_id in reversed(self.exit_plan_calls):
            if call_id not in self.rejected_ids and call_id not in self.tool_results:
                return True
        return False

    def ingest(self, events: List[Dict]) -> str:
        """
        处理事件流并返回当前状态
        复现 ccrSession.ts:ingest() 方法
        """
        for event in events:
            event_type = event.get("type", "")

            if event_type == "assistant" and "tool_use" in event:
                # 检查 ExitPlanMode 调用
                if event.get("name", "") == "ExitPlanMode":
                    self.exit_plan_calls.append(event.get("id", ""))

            elif event_type == "user":
                # 记录 tool_result
                for block in event.get("content", []):
                    if block.get("type") == "tool_result":
                        tool_id = block.get("tool_use_id")
                        self.tool_results[tool_id] = block
                        if block.get("is_error"):
                            self.rejected_ids.add(tool_id)

            elif event_type == "result" and event.get("subtype") != "success":
                self.terminated = True

        # 状态判定逻辑
        for call_id in reversed(self.exit_plan_calls):
            if call_id in self.rejected_ids:
                continue

            if call_id not in self.tool_results:
                self.ever_seen_pending = True
                return UltraPlanPhase.PLAN_READY.value

            result = self.tool_results[call_id]
            if isinstance(result, dict) and result.get("is_error"):
                # 检查是否为 teleport (包含特殊标记)
                content = str(result.get("content", ""))
                if "__ULTRAPLAN_TELEPORT_LOCAL__" in content:
                    return "teleport"
                return "rejected"
            else:
                return "approved"

        if self.terminated:
            return "terminated"

        return "unchanged"


# ==================== 查询循环核心 ====================

class QueryLoop:
    """
    查询循环核心
    复现 query.ts 中的 queryLoop() 函数
    """

    def __init__(self, llm: MockLLM):
        self.llm = llm
        self.state = State()
        self.plan_mode = PlanModeStateMachine()
        self.ultra_scanner = ExitPlanModeScanner()

    def _build_api_params(
        self,
        messages: List[Message],
        tools: List[Tool],
        context: QueryContext
    ) -> Dict:
        """构建 API 参数，复现 paramsFromContext() 逻辑"""
        return {
            "model": self.llm.model,
            "messages": [{"role": m.type.value, "content": m.content} for m in messages],
            "tools": [{"name": t.name, "description": t.description} for t in tools],
            "max_tokens": 8192,
            "system_prompt": self._build_system_prompt(context),
        }

    def _build_system_prompt(self, context: QueryContext) -> str:
        """构建系统提示词"""
        base_prompt = "You are Claude Code, an AI programming assistant."

        if context.mode == "plan":
            return base_prompt + "\n\nPlan mode is active. Use the TaskCreate tool for planning."

        return base_prompt

    def _check_recovery_conditions(self, message: Message) -> Optional[str]:
        """
        检查恢复条件
        复现 query.ts:1188-1252 的 max_output_tokens 恢复逻辑
        """
        if message.stop_reason == "max_output_tokens":
            if self.state.max_output_tokens_recovery_count < 3:
                self.state.max_output_tokens_recovery_count += 1
                self.state.transition_reason = "max_output_tokens_recovery"
                return "continue"

        return "completed"

    def _execute_tools(self, tool_message: Message) -> List[Message]:
        """
        执行工具调用
        复现 runTools() 逻辑
        """
        results = []

        if tool_message.tool_name and tool_message.tool_input:
            for tool in self.state.tool_use_context.tools:
                if tool.name == tool_message.tool_name:
                    try:
                        output = tool.handler(tool_message.tool_input)
                        results.append(Message(
                            type=MessageType.TOOL_RESULT,
                            content=output,
                            tool_use_id=tool_message.tool_use_id
                        ))
                    except Exception as e:
                        results.append(Message(
                            type=MessageType.TOOL_RESULT,
                            content=f"Error: {str(e)}",
                            tool_use_id=tool_message.tool_use_id
                        ))

        return results

    def _should_continue(self, message: Message) -> bool:
        """判断是否继续循环"""
        if message.stop_reason == "tool_use":
            return True
        if message.stop_reason == "end_turn":
            return False

        # 检查是否达到最大轮数
        if self.state.turn_count >= self.state.max_turns:
            print(f"[QueryLoop] Max turns ({self.state.max_turns}) reached")
            return False

        return False

    def run(
        self,
        initial_prompt: str,
        tools: List[Tool],
        mode: str = "default"
    ) -> Generator[Message, None, None]:
        """
        运行查询循环
        复现 query.ts:241-1729 的 queryLoop() 函数
        """
        # 初始化
        self.state.messages = [
            Message(type=MessageType.USER, content=initial_prompt)
        ]
        self.state.tool_use_context = QueryContext(
            messages=self.state.messages.copy(),
            tools=tools,
            mode=mode
        )

        # 激活 Plan Mode
        if mode == "plan":
            self.plan_mode.enable_plan_mode()

        print(f"[QueryLoop] Starting query loop in {mode} mode")

        while True:
            self.state.turn_count += 1
            print(f"[QueryLoop] Turn {self.state.turn_count}")

            # 构建参数
            params = self._build_api_params(
                self.state.messages,
                self.state.tool_use_context.tools,
                self.state.tool_use_context
            )

            # LLM 调用
            llm_message = self.llm.chat(self.state.messages, self.state.tool_use_context.tools)
            self.state.messages.append(llm_message)
            yield llm_message

            # 检查是否需要继续
            if not self._should_continue(llm_message):
                print(f"[QueryLoop] Query completed: {llm_message.stop_reason}")
                break

            # 执行工具
            tool_results = self._execute_tools(llm_message)
            for result in tool_results:
                self.state.messages.append(result)
                yield result

            # 检查恢复条件
            recovery_decision = self._check_recovery_conditions(llm_message)
            if recovery_decision == "continue":
                print(f"[QueryLoop] Recovery triggered: {self.state.transition_reason}")
                # 添加恢复消息
                recovery_message = Message(
                    type=MessageType.USER,
                    content="[System] Resume from where you left off.",
                    metadata={"is_meta": True}
                )
                self.state.messages.append(recovery_message)
                continue

            # 检查停止钩子
            if self.state.stop_hook_active:
                print("[QueryLoop] Stop hook active, stopping")
                break


# ==================== Ultra Planning ====================

class UltraPlanning:
    """
    Ultra Planning 流程
    复现 ultraplan.tsx 和 ccrSession.ts 的核心逻辑
    """

    def __init__(self, llm: MockLLM):
        self.llm = llm
        self.scanner = ExitPlanModeScanner()
        self.timeout = 30 * 60  # 30 分钟

    def detect_keyword(self, text: str) -> bool:
        """
        关键词检测
        复现 keyword.ts:findUltraplanTriggerPositions() 逻辑
        """
        keyword = "ultraplan"
        # 简化的检测逻辑
        return keyword.lower() in text.lower() and not text.strip().startswith("/")

    def replace_keyword(self, text: str) -> str:
        """替换关键词，保持语法正确"""
        return text.lower().replace("ultraplan", "plan")

    def launch(
        self,
        prompt: str,
        seed_plan: Optional[str] = None
    ) -> Generator[str, None, None]:
        """
        启动 Ultra Planning 流程
        复现 ultraplan.tsx:launchUltraplan() 逻辑
        """
        print(f"[UltraPlan] Launching with prompt: {prompt[:50]}...")

        # 1. 构建提示词
        if seed_plan:
            full_prompt = f"Here is a draft plan to refine:\n\n{seed_plan}\n\n{prompt}"
        else:
            full_prompt = prompt

        # 2. 模拟远程会话创建
        session_id = f"session_{int(time.time())}"
        print(f"[UltraPlan] Remote session created: {session_id}")

        # 3. 轮询用户批准
        yield f"[UltraPlan] Waiting for approval... (Session: {session_id})"

        # 4. 模拟状态转换
        phases = [
            UltraPlanPhase.RUNNING,
            UltraPlanPhase.NEEDS_INPUT,
            UltraPlanPhase.PLAN_READY
        ]

        for phase in phases:
            print(f"[UltraPlan] Phase: {phase}")
            yield f"[UltraPlan] Status: {phase}"
            time.sleep(0.5)  # 模拟延迟

        # 5. 模拟用户批准
        approved_plan = """1. Analyze the requirements
2. Design the architecture
3. Implement the solution
4. Test and validate"""

        yield f"[UltraPlan] Plan approved!"
        yield f"Plan:\n{approved_plan}"

        # 6. 清理
        print("[UltraPlan] Session completed")


# ==================== 示例工具 ====================

def read_file_handler(input_dict: Dict) -> str:
    """模拟文件读取"""
    path = input_dict.get("path", "")
    return f"Content of {path}"


def write_file_handler(input_dict: Dict) -> str:
    """模拟文件写入"""
    path = input_dict.get("path", "")
    content = input_dict.get("content", "")
    return f"Written to {path}: {len(content)} bytes"


def task_create_handler(input_dict: Dict) -> str:
    """任务创建工具，Plan Mode 核心工具"""
    tasks = input_dict.get("tasks", [])
    return f"Created {len(tasks)} tasks"


# ==================== 主函数 ====================

def main():
    """演示任务规划和推理流程"""
    print("=" * 60)
    print("Claude Code 任务规划与推理机制演示")
    print("=" * 60)

    # 创建 LLM 和工具
    llm = MockLLM()
    tools = [
        Tool("read_file", "Read a file", read_file_handler),
        Tool("write_file", "Write a file", write_file_handler),
        Tool("task_create", "Create tasks", task_create_handler),
    ]

    # 演示 1: 普通查询模式
    print("\n--- 演示 1: 普通查询 ---")
    query_loop = QueryLoop(llm)

    for message in query_loop.run("Read the file and summarize it", tools, "default"):
        if message.type == MessageType.ASSISTANT and message.tool_name:
            print(f"→ Tool call: {message.tool_name}")
        elif message.type == MessageType.TOOL_RESULT:
            print(f"→ Tool result: {message.content[:50]}...")
        elif message.type == MessageType.ASSISTANT:
            print(f"→ Response: {message.content[:50]}...")

    # 演示 2: Plan Mode
    print("\n--- 演示 2: Plan Mode ---")
    plan_mode = PlanModeStateMachine()
    plan_mode.enable_plan_mode()
    plan_mode.set_plan_content("1. Research\n2. Design\n3. Implement")
    print(f"Plan mode active: {plan_mode.is_plan_mode()}")

    # 演示 3: Ultra Planning
    print("\n--- 演示 3: Ultra Planning ---")
    ultra_planning = UltraPlanning(llm)

    for status in ultra_planning.launch("Create a web application"):
        print(status)

    # 演示 4: ExitPlanModeScanner
    print("\n--- 演示 4: ExitPlanModeScanner ---")
    scanner = ExitPlanModeScanner()

    # 模拟事件流
    events = [
        {"type": "assistant", "name": "ExitPlanMode", "id": "call_1"},
        {"type": "user", "content": [{"type": "tool_result", "tool_use_id": "call_1",
                      "content": "## Approved Plan:\n1. Task A\n2. Task B"}]},
    ]

    result = scanner.ingest(events)
    print(f"Scanner result: {result}")


if __name__ == "__main__":
    main()
