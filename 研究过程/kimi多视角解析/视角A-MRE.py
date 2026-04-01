"""
视角A-MRE.py
Claude Code Agent核心构建的最小化可复现实现 (Minimum Reproducible Example)

展示了：
1. Tool/Agent的基础抽象
2. Task状态机管理
3. 权限检查机制
4. 异步执行生命周期
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Coroutine, Dict, Generic, List, Optional, TypeVar, Union
import asyncio
import uuid
import time


# ============================================================================
# 1. 基础类型定义
# ============================================================================

TInput = TypeVar('TInput', bound=Dict[str, Any])
TOutput = TypeVar('TOutput')


class PermissionResult(Enum):
    """权限检查结果"""
    ALLOW = auto()
    DENY = auto()
    ASK = auto()


class TaskStatus(Enum):
    """Task状态机"""
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    KILLED = auto()

    @property
    def is_terminal(self) -> bool:
        return self in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.KILLED)


# ============================================================================
# 2. Tool抽象
# ============================================================================

@dataclass
class ToolContext:
    """Tool执行上下文"""
    agent_id: Optional[str] = None
    verbose: bool = False


class Tool(ABC, Generic[TInput, TOutput]):
    """
    Tool抽象基类 - 对应Claude Code的Tool类型
    """
    name: str
    aliases: List[str] = field(default_factory=list)

    def __init__(self):
        self._validate_schema()

    @abstractmethod
    async def call(self, args: TInput, context: ToolContext) -> TOutput:
        """执行工具"""
        pass

    @abstractmethod
    def get_description(self) -> str:
        """获取工具描述"""
        pass

    def validate_input(self, args: TInput) -> tuple[bool, Optional[str]]:
        """输入验证 - 默认通过"""
        return True, None

    def check_permissions(self, args: TInput, context: ToolContext) -> PermissionResult:
        """权限检查 - 默认允许 (对应TOOL_DEFAULTS)"""
        return PermissionResult.ALLOW

    def is_concurrency_safe(self, args: TInput) -> bool:
        """是否并发安全 - 默认False (fail-closed)"""
        return False

    def is_read_only(self, args: TInput) -> bool:
        """是否只读操作 - 默认False (fail-closed)"""
        return False

    def is_destructive(self, args: TInput) -> bool:
        """是否具有破坏性 - 默认False"""
        return False

    def _validate_schema(self):
        """验证工具定义"""
        assert hasattr(self, 'name') and self.name, "Tool必须定义name"


# ============================================================================
# 3. Task状态管理
# ============================================================================

@dataclass
class TaskState:
    """
    Task状态 - 对应TaskStateBase + LocalAgentTaskState
    """
    id: str
    type: str
    status: TaskStatus
    description: str
    start_time: float
    end_time: Optional[float] = None
    output_file: Optional[str] = None
    notified: bool = False

    # Agent特有字段
    agent_id: Optional[str] = None
    prompt: Optional[str] = None
    agent_type: Optional[str] = None
    is_backgrounded: bool = False
    progress: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    result: Optional[Any] = None

    # 运行时控制
    _abort_event: asyncio.Event = field(default_factory=asyncio.Event)
    _cleanup_handlers: List[Callable[[], None]] = field(default_factory=list)

    def abort(self):
        """中止任务"""
        self._abort_event.set()

    def is_aborted(self) -> bool:
        return self._abort_event.is_set()

    def add_cleanup(self, handler: Callable[[], None]):
        """注册清理处理器"""
        self._cleanup_handlers.append(handler)

    async def cleanup(self):
        """执行清理"""
        for handler in self._cleanup_handlers:
            try:
                handler()
            except Exception as e:
                print(f"Cleanup error: {e}")


class TaskRegistry:
    """
    Task注册表 - 简化版AppState.tasks
    """
    def __init__(self):
        self._tasks: Dict[str, TaskState] = {}

    def register(self, task: TaskState):
        """注册任务"""
        self._tasks[task.id] = task

    def update(self, task_id: str, updater: Callable[[TaskState], TaskState]):
        """更新任务状态 (函数式更新)"""
        if task_id in self._tasks:
            self._tasks[task_id] = updater(self._tasks[task_id])

    def get(self, task_id: str) -> Optional[TaskState]:
        return self._tasks.get(task_id)

    def remove(self, task_id: str):
        """移除任务"""
        if task_id in self._tasks:
            del self._tasks[task_id]

    def list_running(self) -> List[TaskState]:
        """获取所有运行中的任务"""
        return [t for t in self._tasks.values() if t.status == TaskStatus.RUNNING]


# ============================================================================
# 4. Agent核心实现
# ============================================================================

@dataclass
class AgentDefinition:
    """Agent定义 - 对应AgentDefinition"""
    agent_type: str
    description: str
    system_prompt: str = "You are a helpful assistant."
    model: Optional[str] = None
    background: bool = False


class SimpleAgentTool(Tool[Dict[str, Any], Dict[str, Any]]):
    """
    简化版Agent Tool - 对应AgentTool的核心逻辑
    """
    name = "Agent"

    def __init__(self, registry: TaskRegistry, agent_defs: Dict[str, AgentDefinition]):
        super().__init__()
        self.registry = registry
        self.agent_defs = agent_defs

    def get_description(self) -> str:
        return "Launch a subagent to perform tasks"

    async def call(self, args: Dict[str, Any], context: ToolContext) -> Dict[str, Any]:
        """
        Agent执行入口
        """
        description = args.get('description', 'Unnamed task')
        prompt = args.get('prompt', '')
        agent_type = args.get('subagent_type', 'general')
        run_in_background = args.get('run_in_background', False)

        # 1. 选择Agent定义
        agent_def = self.agent_defs.get(agent_type)
        if not agent_def:
            raise ValueError(f"Unknown agent type: {agent_type}")

        # 2. 创建Task ID
        task_id = self._generate_task_id()

        # 3. 决定执行模式
        should_run_async = run_in_background or agent_def.background

        if should_run_async:
            # 异步模式：启动后台任务，立即返回
            task = self._create_task(task_id, description, prompt, agent_def)
            asyncio.create_task(self._run_async_agent(task, agent_def, prompt))
            return {
                'status': 'async_launched',
                'task_id': task_id,
                'description': description,
                'prompt': prompt
            }
        else:
            # 同步模式：等待执行完成
            task = self._create_task(task_id, description, prompt, agent_def)
            result = await self._run_sync_agent(task, agent_def, prompt)
            return {
                'status': 'completed',
                'task_id': task_id,
                'result': result
            }

    def _generate_task_id(self) -> str:
        """生成任务ID - 使用'a'前缀表示agent任务"""
        return f"a{uuid.uuid4().hex[:8]}"

    def _create_task(
        self,
        task_id: str,
        description: str,
        prompt: str,
        agent_def: AgentDefinition
    ) -> TaskState:
        """创建TaskState"""
        task = TaskState(
            id=task_id,
            type='local_agent',
            status=TaskStatus.PENDING,
            description=description,
            start_time=time.time(),
            agent_id=task_id,
            prompt=prompt,
            agent_type=agent_def.agent_type
        )
        self.registry.register(task)
        return task

    async def _run_async_agent(
        self,
        task: TaskState,
        agent_def: AgentDefinition,
        prompt: str
    ):
        """后台执行Agent"""
        try:
            # 更新状态为运行中
            task.status = TaskStatus.RUNNING
            task.is_backgrounded = True

            # 模拟Agent执行
            result = await self._simulate_agent_execution(task, agent_def, prompt)

            # 标记完成
            if not task.is_aborted():
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.end_time = time.time()
                print(f"[Agent {task.id}] Completed: {result}")

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            print(f"[Agent {task.id}] Failed: {e}")
        finally:
            await task.cleanup()

    async def _run_sync_agent(
        self,
        task: TaskState,
        agent_def: AgentDefinition,
        prompt: str
    ) -> str:
        """同步执行Agent"""
        task.status = TaskStatus.RUNNING

        # 模拟：2秒后自动转为后台（如果未提前完成）
        try:
            result = await asyncio.wait_for(
                self._simulate_agent_execution(task, agent_def, prompt),
                timeout=2.0
            )
            task.status = TaskStatus.COMPLETED
            task.result = result
            task.end_time = time.time()
            return result

        except asyncio.TimeoutError:
            # 转为后台执行
            print(f"[Agent {task.id}] Converting to background...")
            task.is_backgrounded = True
            asyncio.create_task(self._run_async_agent(task, agent_def, prompt))
            return f"Task {task.id} moved to background"

    async def _simulate_agent_execution(
        self,
        task: TaskState,
        agent_def: AgentDefinition,
        prompt: str
    ) -> str:
        """模拟Agent执行过程"""
        steps = 3
        for i in range(steps):
            if task.is_aborted():
                raise asyncio.CancelledError("Task aborted")

            # 更新进度
            task.progress = {
                'step': i + 1,
                'total': steps,
                'activity': f'Processing step {i+1}'
            }

            print(f"[Agent {task.id}] {task.progress['activity']}")
            await asyncio.sleep(1)  # 模拟工作

        return f"Result of: {prompt[:30]}..."


# ============================================================================
# 5. 权限系统
# ============================================================================

class PermissionManager:
    """
    简化版权限管理 - 对应toolPermissionContext
    """
    def __init__(self):
        self.always_allow: List[str] = []
        self.always_deny: List[str] = []
        self.always_ask: List[str] = []

    def check_tool_permission(self, tool_name: str) -> PermissionResult:
        """检查工具权限"""
        if tool_name in self.always_deny:
            return PermissionResult.DENY
        if tool_name in self.always_allow:
            return PermissionResult.ALLOW
        if tool_name in self.always_ask:
            return PermissionResult.ASK
        return PermissionResult.ALLOW  # 默认允许


# ============================================================================
# 6. 使用示例
# ============================================================================

async def main():
    """演示Agent核心构建的使用"""

    print("=" * 60)
    print("Claude Code Agent核心构建 - MRE演示")
    print("=" * 60)

    # 初始化组件
    registry = TaskRegistry()

    agent_defs = {
        'general': AgentDefinition(
            agent_type='general',
            description='General purpose agent',
            system_prompt='You are a helpful assistant.'
        ),
        'coder': AgentDefinition(
            agent_type='coder',
            description='Code specialist agent',
            system_prompt='You are a coding expert.',
            background=True  # 默认后台运行
        )
    }

    agent_tool = SimpleAgentTool(registry, agent_defs)

    print("\n[示例1] 同步Agent执行")
    print("-" * 40)
    result1 = await agent_tool.call({
        'description': 'Quick task',
        'prompt': 'Say hello',
        'subagent_type': 'general',
        'run_in_background': False
    }, ToolContext())
    print(f"Result: {result1}")

    print("\n[示例2] 异步Agent执行（自动后台化）")
    print("-" * 40)
    result2 = await agent_tool.call({
        'description': 'Long running task',
        'prompt': 'Analyze codebase',
        'subagent_type': 'coder',
        'run_in_background': True
    }, ToolContext())
    print(f"Result: {result2}")

    # 等待后台任务完成
    print("\n[等待后台任务完成...]")
    await asyncio.sleep(4)

    print("\n[示例3] 查看所有任务状态")
    print("-" * 40)
    for task_id in ['a' + str(i) for i in range(100)]:  # 简单的遍历方式
        task = registry.get(task_id)
        if task:
            print(f"Task {task_id}: {task.status.name}, background={task.is_backgrounded}")

    print("\n[示例4] 权限检查")
    print("-" * 40)
    perm_mgr = PermissionManager()
    perm_mgr.always_deny.append('DangerousTool')

    print(f"ReadTool permission: {perm_mgr.check_tool_permission('ReadTool')}")
    print(f"DangerousTool permission: {perm_mgr.check_tool_permission('DangerousTool')}")

    print("\n" + "=" * 60)
    print("演示完成")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())
