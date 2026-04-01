#!/usr/bin/env python3
"""
最小化实现：记忆系统
展示：上下文管理、压缩策略、记忆检索
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Callable
from collections import deque
import hashlib
import time


@dataclass
class MemoryEntry:
    """记忆条目"""
    id: str
    content: str
    timestamp: float
    metadata: Dict = field(default_factory=dict)
    token_estimate: int = 0


@dataclass
class CompressedMemory:
    """压缩后的记忆"""
    summary: str
    original_ids: List[str]
    compression_ratio: float
    timestamp: float


class TokenBudget:
    """Token 预算管理"""

    def __init__(self, max_tokens: int = 100000):
        self.max_tokens = max_tokens
        self.warning_threshold = max_tokens - 20000
        self.error_threshold = max_tokens - 40000

    def check_status(self, used_tokens: int) -> Dict[str, bool]:
        """检查 token 使用状态"""
        remaining = self.max_tokens - used_tokens
        return {
            'is_above_warning': used_tokens >= self.warning_threshold,
            'is_above_error': used_tokens >= self.error_threshold,
            'remaining_tokens': remaining,
            'percent_used': (used_tokens / self.max_tokens) * 100
        }


class MemoryStore:
    """记忆存储"""

    def __init__(self):
        self.entries: Dict[str, MemoryEntry] = {}
        self.timeline: deque = deque(maxlen=1000)
        self.compressed: Dict[str, CompressedMemory] = {}

    def add(self, content: str, metadata: Dict = None) -> str:
        """添加记忆"""
        entry_id = hashlib.md5(
            f"{content}{time.time()}".encode()
        ).hexdigest()[:12]

        entry = MemoryEntry(
            id=entry_id,
            content=content,
            timestamp=time.time(),
            metadata=metadata or {},
            token_estimate=len(content) // 4  # 简化估算
        )

        self.entries[entry_id] = entry
        self.timeline.append(entry_id)
        return entry_id

    def get_recent(self, limit: int = 50) -> List[MemoryEntry]:
        """获取最近的记忆"""
        recent_ids = list(self.timeline)[-limit:]
        return [self.entries[eid] for eid in recent_ids if eid in self.entries]

    def compress(
        self,
        entries: List[str],
        compressor: Callable[[List[str]], str]
    ) -> CompressedMemory:
        """压缩记忆"""
        contents = [
            self.entries[eid].content
            for eid in entries
            if eid in self.entries
        ]

        summary = compressor(contents)
        original_tokens = sum(
            self.entries[eid].token_estimate for eid in entries
        )
        compressed_tokens = len(summary) // 4

        compressed = CompressedMemory(
            summary=summary,
            original_ids=entries,
            compression_ratio=compressed_tokens / max(original_tokens, 1),
            timestamp=time.time()
        )

        # 存储压缩结果
        for eid in entries:
            if eid in self.entries:
                del self.entries[eid]
                self.timeline.remove(eid)

        comp_id = hashlib.md5(
            f"compressed{time.time()}".encode()
        ).hexdigest()[:12]
        self.compressed[comp_id] = compressed

        # 将压缩摘要添加到时间线
        summary_entry = MemoryEntry(
            id=comp_id,
            content=summary,
            timestamp=time.time(),
            metadata={'type': 'compressed', 'original_count': len(entries)},
            token_estimate=compressed_tokens
        )
        self.entries[comp_id] = summary_entry
        self.timeline.append(comp_id)

        return compressed


class ContextManager:
    """上下文管理器"""

    def __init__(
        self,
        budget: TokenBudget,
        memory_store: MemoryStore,
        auto_compress_threshold: float = 0.8
    ):
        self.budget = budget
        self.memory_store = memory_store
        self.auto_compress_threshold = auto_compress_threshold
        self.current_messages: List[Dict] = []

    def add_message(self, role: str, content: str) -> str:
        """添加消息并管理上下文"""
        self.current_messages.append({
            'role': role,
            'content': content,
            'timestamp': time.time()
        })

        # 添加到长期记忆
        self.memory_store.add(content, {'role': role})

        # 检查是否需要压缩
        self._maybe_auto_compress()

        return str(len(self.current_messages))

    def get_context(self) -> List[Dict]:
        """获取当前上下文（在预算内）"""
        current_tokens = self._count_tokens()
        status = self.budget.check_status(current_tokens)

        if status['is_above_warning']:
            return self._trim_to_budget()

        return list(self.current_messages)

    def _count_tokens(self) -> int:
        """估算当前 token 数"""
        return sum(
            len(msg.get('content', '')) // 4
            for msg in self.current_messages
        )

    def _maybe_auto_compress(self):
        """自动压缩检查"""
        current_tokens = self._count_tokens()
        status = self.budget.check_status(current_tokens)

        if status['percent_used'] >= self.auto_compress_threshold * 100:
            self._compress_old_messages()

    def _compress_old_messages(
        self,
        compressor: Callable[[List[str]], str] = None
    ):
        """压缩旧消息"""
        if compressor is None:
            # 默认压缩器：简单连接
            compressor = lambda contents: "[Summary] " + "... ".join(
                c[:100] for c in contents
            )

        compress_count = max(1, len(self.current_messages) // 2)
        to_compress = self.current_messages[:compress_count]

        if not to_compress:
            return

        summary = compressor([m['content'] for m in to_compress])

        self.current_messages = [{
            'role': 'system',
            'content': summary,
            'id': 'compressed',
            'timestamp': time.time()
        }] + self.current_messages[compress_count:]

    def _trim_to_budget(self) -> List[Dict]:
        """裁剪到预算内"""
        max_tokens = self.budget.warning_threshold
        result = []
        current_tokens = 0

        # 从后往前添加（保留最新的）
        for msg in reversed(self.current_messages):
            msg_tokens = len(msg.get('content', '')) // 4
            if current_tokens + msg_tokens > max_tokens:
                break
            result.insert(0, msg)
            current_tokens += msg_tokens

        return result


# 使用示例
def demo():
    budget = TokenBudget(max_tokens=100000)
    memory = MemoryStore()
    context_mgr = ContextManager(budget, memory, auto_compress_threshold=0.7)

    # 模拟对话
    for i in range(20):
        context_mgr.add_message(
            'user', f"Message {i}: " + "Hello " * 100
        )
        context_mgr.add_message(
            'assistant', f"Response {i}: " + "World " * 100
        )

        tokens = context_mgr._count_tokens()
        status = budget.check_status(tokens)
        print(f"After {i+1} turns: {tokens} tokens, "
              f"warning={status['is_above_warning']}")

    # 获取最终上下文
    context = context_mgr.get_context()
    print(f"\nFinal context: {len(context)} messages")
    print(f"First message preview: {context[0]['content'][:50]}...")


if __name__ == "__main__":
    demo()
