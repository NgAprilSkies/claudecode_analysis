"""
Claude Code Core Build - Minimal Reproduction

This is a simplified Python implementation that captures the core architectural
principles of Claude Code's Agent system:
1. Task-based execution model
2. State machine lifecycle management
3. In-process teammate coordination
4. Mailbox communication system

Key design patterns demonstrated:
- Strategy Pattern: Different task types with shared interface
- Observer Pattern: State subscription and notification
- State Pattern: Task lifecycle state machine
- Actor Model: Teammate isolation via context
"""

import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Set
from collections import defaultdict
import json
import os


# =============================================================================
# 1. CORE TYPE DEFINITIONS (mirrors Task.ts)
# =============================================================================

class TaskType(Enum):
    """Task type identifiers"""
    LOCAL_SHELL = "local_bash"
    LOCAL_AGENT = "local_agent"
    REMOTE_AGENT = "remote_agent"
    IN_PROCESS_TEAMMATE = "in_process_teammate"
    LOCAL_WORKFLOW = "local_workflow"


class TaskStatus(Enum):
    """Task lifecycle states"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


def is_terminal_status(status: TaskStatus) -> bool:
    """Check if status is terminal (mirrors isTerminalTaskStatus)"""
    return status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.KILLED)


@dataclass
class TaskStateBase:
    """Base task state (mirrors Task.ts TaskStateBase)"""
    id: str
    type: TaskType
    status: TaskStatus
    description: str
    tool_use_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    output_file: str = ""
    notified: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type.value,
            "status": self.status.value,
            "description": self.description,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "notified": self.notified
        }


# =============================================================================
# 2. TASK INTERFACE (mirrors Task.ts Task interface)
# =============================================================================

class Task(ABC):
    """Base task interface"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Task name"""
        pass

    @property
    @abstractmethod
    def type(self) -> TaskType:
        """Task type"""
        pass

    @abstractmethod
    async def kill(self, task_id: str) -> None:
        """Kill the task"""
        pass


# =============================================================================
# 3. STATE MANAGEMENT (mirrors bootstrap/state.ts + store.ts)
# =============================================================================

class GlobalState:
    """
    Global singleton state (mirrors bootstrap/state.ts STATE)

    In production: 100+ fields including sessionId, cost tracking, etc.
    Here: Simplified to essential fields for demo.
    """
    _instance: Optional['GlobalState'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if GlobalState._instance is not None:
            return
        self.session_id: str = str(uuid.uuid4())
        self.tasks: Dict[str, TaskStateBase] = {}
        self.cwd: str = os.getcwd()
        self._listeners: Set[Callable] = set()

    @classmethod
    def get_instance(cls) -> 'GlobalState':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_state(self) -> Dict:
        """Get current state (mirrors getState)"""
        return {
            "session_id": self.session_id,
            "tasks": {tid: t.to_dict() for tid, t in self.tasks.items()}
        }

    def set_state(self, updater: Callable[[Dict], Dict]) -> None:
        """
        Update state (mirrors setState pattern)
        Uses functional update pattern for immutability
        """
        old_state = self.get_state()
        new_state = updater(old_state)

        # Apply updates to fields
        if "session_id" in new_state:
            self.session_id = new_state["session_id"]
        if "tasks" in new_state:
            self.tasks = new_state["tasks"]

        # Notify listeners (Observer pattern)
        for listener in self._listeners:
            listener(new_state, old_state)

    def subscribe(self, listener: Callable) -> Callable:
        """Subscribe to state changes (mirrors store.ts subscribe)"""
        self._listeners.add(listener)
        def unsubscribe():
            self._listeners.remove(listener)
        return unsubscribe


# =============================================================================
# 4. IN-PROCESS TEAMMATE (mirrors inProcessRunner.ts)
# =============================================================================

class TeammateContext:
    """
    AsyncLocalStorage isolation context (mirrors teammateContext.ts)

    In production: Uses AsyncLocalStorage for Node.js context isolation
    Here: Uses contextvars for Python equivalent
    """
    def __init__(self, agent_id: str, agent_name: str, team_name: str):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.team_name = team_name
        self._messages: List[dict] = []
        self._abort_controller = asyncio.Future()

    def add_message(self, message: dict) -> None:
        self._messages.append(message)

    def get_messages(self) -> List[dict]:
        return self._messages.copy()

    async def check_abort(self) -> bool:
        """Check if abort was signaled"""
        return self._abort_controller.done()

    def abort(self) -> None:
        if not self._abort_controller.done():
            self._abort_controller.set_result(None)


# Teammate context storage (thread-local equivalent of AsyncLocalStorage)
_teammate_context = None


def set_teammate_context(context: TeammateContext) -> None:
    global _teammate_context
    _teammate_context = context


def get_teammate_context() -> Optional[TeammateContext]:
    return _teammate_context


@dataclass
class InProcessTeammateTaskState(TaskStateBase):
    """In-process teammate task state"""
    identity: Dict[str, str]
    prompt: str
    messages: List[dict] = field(default_factory=list)
    is_idle: bool = False
    shutdown_requested: bool = False
    pending_messages: List[str] = field(default_factory=list)


class InProcessTeammateTask(Task):
    """
    In-process teammate implementation (mirrors InProcessTeammateTask)

    Key features:
    - Runs in same process with context isolation
    - AsyncLocalStorage for identity scoping
    - Mailbox-based communication
    - Idle notification loop
    """

    def __init__(self, state: GlobalState):
        self._state = state
        self._running_tasks: Dict[str, asyncio.Task] = {}

    @property
    def name(self) -> str:
        return "InProcessTeammateTask"

    @property
    def type(self) -> TaskType:
        return TaskType.IN_PROCESS_TEAMMATE

    async def kill(self, task_id: str) -> None:
        """Kill a teammate task"""
        await self._update_task(task_id, lambda t: {
            **t,
            "status": TaskStatus.KILLED,
            "end_time": time.time()
        })

    def _update_task(self, task_id: str, updater: Callable) -> None:
        """Update task state atomically"""
        def state_updater(current: Dict) -> Dict:
            tasks = current.get("tasks", {})
            if task_id not in tasks:
                return current
            task = tasks[task_id]
            updated = updater(task)
            tasks[task_id] = updated
            current["tasks"] = tasks
            return current

        self._state.set_state(state_updater, state_updater)

    async def spawn_teammate(
        self,
        name: str,
        team_name: str,
        prompt: str,
        color: str = "blue"
    ) -> str:
        """
        Spawn a new teammate (mirrors spawnInProcess.ts)
        Returns agent_id
        """
        agent_id = f"{name}@{team_name}"
        task_id = f"t_{uuid.uuid4().hex[:8]}"

        # Create identity
        identity = {
            "agent_id": agent_id,
            "agent_name": name,
            "team_name": team_name,
            "color": color
        }

        # Create task state
        task_state = InProcessTeammateTaskState(
            id=task_id,
            type=TaskType.IN_PROCESS_TEAMMATE,
            status=TaskStatus.RUNNING,
            description=f"{name}: {prompt[:50]}",
            identity=identity,
            prompt=prompt
        )

        # Register in state
        def state_updater(current: Dict) -> Dict:
            tasks = current.get("tasks", {})
            tasks[task_id] = task_state.to_dict()
            current["tasks"] = tasks
            return current

        self._state.set_state(state_updater, state_updater)

        # Start teammate loop in background
        task = asyncio.create_task(self._teammate_loop(
            task_id, agent_id, prompt, identity
        ))
        self._running_tasks[task_id] = task

        return agent_id

    async def _teammate_loop(
        self,
        task_id: str,
        agent_id: str,
        initial_prompt: str,
        identity: dict
    ) -> None:
        """
        Main teammate execution loop (mirrors inProcessRunner.ts runInProcessTeammate)

        This demonstrates:
        1. Context isolation via TeammateContext
        2. Message processing loop
        3. Idle state notification
        4. Graceful shutdown
        """
        # Create teammate context
        context = TeammateContext(
            agent_id=agent_id,
            agent_name=identity["agent_name"],
            team_name=identity["team_name"]
        )

        set_teammate_context(context)

        current_prompt = initial_prompt

        try:
            while not await context.check_abort():
                # Process current prompt
                await self._process_prompt(task_id, agent_id, current_prompt, context)

                # Mark as idle
                await self._update_task(task_id, lambda t: {
                    **t,
                    "is_idle": True
                })

                # Send idle notification
                await self._send_idle_notification(agent_id, identity)

                # Wait for next message or shutdown
                next_prompt = await self._wait_for_prompt(task_id, context)

                if next_prompt is None:  # Shutdown requested
                    break

                # Check for abort
                if await context.check_abort():
                    break

                current_prompt = next_prompt

        finally:
            # Cleanup
            await self._update_task(task_id, lambda t: {
                **t,
                "status": TaskStatus.COMPLETED,
                "end_time": time.time()
            })
            set_teammate_context(None)

    async def _process_prompt(
        self,
        task_id: str,
        agent_id: str,
        prompt: str,
        context: TeammateContext
    ) -> None:
        """Process a single prompt"""
        # Add message to context
        context.add_message({
            "role": "user",
            "content": prompt,
            "timestamp": time.time()
        })

        # Simulate agent work
        await asyncio.sleep(0.1)

        # Update progress
        def state_updater(current: Dict) -> Dict:
            tasks = current.get("tasks", {})
            if task_id in tasks:
                task = tasks[task_id]
                messages = task.get("messages", [])
                messages.append(context.get_messages()[-1])
                tasks[task_id]["messages"] = messages
                current["tasks"] = tasks
            return current

        self._state.set_state(state_updater, state_updater)

    async def _wait_for_prompt(
        self,
        task_id: str,
        context: TeammateContext
    ) -> Optional[str]:
        """Wait for next prompt or shutdown request"""
        for _ in range(50):  # Poll for up to 5 seconds
            await asyncio.sleep(0.1)

            # Check for shutdown
            def state_updater(current: Dict) -> Dict:
                tasks = current.get("tasks", {})
                if task_id in tasks:
                    task = tasks[task_id]
                    if task.get("shutdown_requested"):
                        current["tasks"][task_id]["shutdown_requested"] = False
                return current

            self._state.set_state(state_updater, state_updater)

            # Check for pending messages
            task = self._state.get_state()["tasks"].get(task_id, {})
            if task.get("pending_messages"):
                return task["pending_messages"].pop(0)

            if await context.check_abort():
                return None

        return None

    async def _send_idle_notification(self, agent_id: str, identity: dict) -> None:
        """Send idle notification (would go to mailbox in production)"""
        print(f"[IDLE] {agent_id} is idle (color: {identity.get('color', 'none')})")


# =============================================================================
# 5. MAILBOX COMMUNICATION (mirrors teammateMailbox.ts)
# =============================================================================

class Mailbox:
    """
    File-based mailbox system (mirrors teammateMailbox.ts)

    In production: Uses file system for inter-process communication
    Here: In-memory dict for demo purposes
    """
    _instance: Optional['Mailbox'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if Mailbox._instance is not None:
            return
        self._mailboxes: Dict[str, List[dict]] = defaultdict(list)

    @classmethod
    def get_instance(cls) -> 'Mailbox':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def write_mailbox(
        self,
        recipient: str,
        sender: str,
        message: str
    ) -> None:
        """Write message to recipient's mailbox"""
        mailbox = self._mailboxes[recipient]
        mailbox.append({
            "from": sender,
            "text": message,
            "timestamp": time.time(),
            "read": False
        })

    async def read_mailbox(self, recipient: str) -> List[dict]:
        """Read all messages from mailbox"""
        return self._mailboxes.get(recipient, [])

    async def mark_read(self, recipient: str, index: int) -> None:
        """Mark message as read"""
        mailbox = self._mailboxes.get(recipient, [])
        if 0 <= index < len(mailbox):
            mailbox[index]["read"] = True


# =============================================================================
# 6. EXAMPLE USAGE
# =============================================================================

async def main():
    """Demonstrate the core build system"""

    # Initialize state
    global_state = GlobalState.get_instance()
    mailbox = Mailbox.get_instance()
    teammate_task = InProcessTeammateTask(global_state)

    # Subscribe to state changes
    def state_listener(new_state: Dict, old_state: Dict):
        print(f"[STATE] Updated: {len(new_state.get('tasks', {}))} tasks")

    unsubscribe = global_state.subscribe(state_listener)

    print("=== Claude Code Core Build Demo ===\n")

    # Spawn a researcher teammate
    print("1. Spawning researcher teammate...")
    researcher_id = await teammate_task.spawn_teammate(
        name="researcher",
        team_name="default",
        prompt="Investigate the codebase structure",
        color="blue"
    )
    print(f"   Spawned: {researcher_id}")

    # Wait a bit
    await asyncio.sleep(0.5)

    # Send a message to the researcher
    print("\n2. Sending message to researcher...")
    await mailbox.write_mailbox(
        recipient=researcher_id,
        sender="team-lead",
        message="Please focus on the Task.ts file"
    )

    # Wait for processing
    await asyncio.sleep(1)

    # Spawn an implementer teammate
    print("\n3. Spawning implementer teammate...")
    implementer_id = await teammate_task.spawn_teammate(
        name="implementer",
        team_name="default",
        prompt="Implement the new feature",
        color="green"
    )
    print(f"   Spawned: {implementer_id}")

    # Show final state
    await asyncio.sleep(0.5)
    print("\n4. Final state:")
    state = global_state.get_state()
    for task_id, task in state["tasks"].items():
        print(f"   {task_id}: {task['status']} - {task['description']}")

    # Cleanup
    unsubscribe()
    print("\n=== Demo Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
