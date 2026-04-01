"""
视角D - MRE: Claude Code 记忆系统简化实现

一个最小可复现示例，展示Claude Code记忆系统的核心机制：
1. 分层记忆管理 (Session/Project/Global)
2. LRU缓存实现
3. Token预算检查
4. 上下文压缩策略
5. 记忆持久化

使用方法: python 视角D-MRE.py
"""

from __future__ import annotations
import json
import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Set, Any, Callable
from datetime import datetime
from pathlib import Path


# ============================================================================
# 1. 基础数据类型
# ============================================================================

@dataclass
class Message:
    """消息基类 - 模拟Claude Code的Message类型"""
    uuid: str
    role: str  # 'user', 'assistant', 'system', 'tool_result'
    content: str
    timestamp: float = field(default_factory=time.time)
    parent_uuid: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def estimate_tokens(self) -> int:
        """粗略估计token数（4字符/token）"""
        return len(self.content) // 4


@dataclass
class ToolResult:
    """工具结果 - 模拟FileRead/Grep等工具输出"""
    tool_use_id: str
    tool_name: str
    content: str

    def estimate_tokens(self) -> int:
        return len(self.content) // 4


# ============================================================================
# 2. LRU缓存实现 (模拟 fileStateCache.ts)
# ============================================================================

class FileState:
    """文件状态 - 缓存已读取的文件内容"""
    def __init__(self, content: str, timestamp: float, offset: int = 0, limit: Optional[int] = None):
        self.content = content
        self.timestamp = timestamp
        self.offset = offset
        self.limit = limit

    def size_bytes(self) -> int:
        return len(self.content.encode('utf-8'))


class LRUFileCache:
    """
    LRU文件状态缓存 - 参考 src/utils/fileStateCache.ts

    特点:
    - O(1)读写
    - 大小限制 (默认25MB)
    - 条目数限制 (默认100)
    - 路径规范化
    """
    def __init__(self, max_entries: int = 100, max_size_bytes: int = 25 * 1024 * 1024):
        self._cache: OrderedDict[str, FileState] = OrderedDict()
        self._max_entries = max_entries
        self._max_size = max_size_bytes
        self._current_size = 0

    def _normalize_path(self, path: str) -> str:
        """路径规范化 - 统一处理分隔符"""
        return path.replace('\\', '/').lower()

    def get(self, key: str) -> Optional[FileState]:
        """获取缓存 - 移动到最近使用"""
        normalized = self._normalize_path(key)
        if normalized in self._cache:
            # 移动到末尾 (最近使用)
            self._cache.move_to_end(normalized)
            return self._cache[normalized]
        return None

    def set(self, key: str, value: FileState) -> bool:
        """设置缓存 - 处理大小限制"""
        normalized = self._normalize_path(key)
        size = value.size_bytes()

        # 如果单个条目超过限制，拒绝缓存
        if size > self._max_size:
            print(f"[Cache] 条目过大，跳过缓存: {size} bytes")
            return False

        # 如果已存在，更新大小计算
        if normalized in self._cache:
            old_size = self._cache[normalized].size_bytes()
            self._current_size -= old_size

        # 淘汰旧条目直到有足够空间
        while (self._current_size + size > self._max_size or
               len(self._cache) >= self._max_entries) and self._cache:
            self._evict_oldest()

        self._cache[normalized] = value
        self._current_size += size
        return True

    def _evict_oldest(self):
        """淘汰最久未使用的条目"""
        if self._cache:
            oldest_key, oldest_value = self._cache.popitem(last=False)
            self._current_size -= oldest_value.size_bytes()
            print(f"[Cache] 淘汰: {oldest_key}")

    def clear(self):
        """清空缓存"""
        self._cache.clear()
        self._current_size = 0

    def stats(self) -> Dict[str, Any]:
        return {
            'entries': len(self._cache),
            'current_size_mb': self._current_size / (1024 * 1024),
            'max_size_mb': self._max_size / (1024 * 1024),
            'max_entries': self._max_entries
        }


# ============================================================================
# 3. Token预算管理 (模拟 toolResultStorage.ts)
# ============================================================================

class ContentReplacementState:
    """
    内容替换状态 - 参考 src/utils/toolResultStorage.ts

    用于跟踪已处理的工具结果，确保:
    - 已替换的内容保持一致性 (prompt cache稳定)
    - 已见但未替换的内容永不替换
    """
    def __init__(self):
        self.seen_ids: Set[str] = set()  # 已看到的工具结果ID
        self.replacements: Dict[str, str] = {}  # ID -> 替换内容

    def mark_seen(self, tool_use_id: str):
        """标记为已见"""
        self.seen_ids.add(tool_use_id)

    def set_replacement(self, tool_use_id: str, replacement: str):
        """设置替换内容"""
        self.replacements[tool_use_id] = replacement
        self.seen_ids.add(tool_use_id)

    def get_replacement(self, tool_use_id: str) -> Optional[str]:
        """获取已缓存的替换内容"""
        return self.replacements.get(tool_use_id)

    def is_frozen(self, tool_use_id: str) -> bool:
        """检查是否已见但未替换 (frozen = 不可再替换)"""
        return tool_use_id in self.seen_ids and tool_use_id not in self.replacements


class ToolResultBudgetManager:
    """
    工具结果预算管理器

    策略:
    - 每个工具结果最大50KB
    - 每消息所有工具结果总和最大150KB
    - 大结果持久化到"磁盘"并替换为预览
    """
    MAX_TOOL_RESULT_BYTES = 50 * 1024
    MAX_PER_MESSAGE_BYTES = 150 * 1024
    PREVIEW_SIZE = 2000

    def __init__(self, storage_dir: str = "./tool_results"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)
        self.state = ContentReplacementState()

    def persist_tool_result(self, content: str, tool_use_id: str) -> Dict[str, Any]:
        """持久化大工具结果到磁盘"""
        file_path = self.storage_dir / f"{tool_use_id}.txt"
        with open(file_path, 'w') as f:
            f.write(content)

        # 生成预览
        preview = content[:self.PREVIEW_SIZE]
        has_more = len(content) > self.PREVIEW_SIZE

        return {
            'filepath': str(file_path),
            'original_size': len(content),
            'preview': preview,
            'has_more': has_more
        }

    def build_replacement_message(self, result: Dict[str, Any]) -> str:
        """构建替换消息"""
        msg = f"[Output too large ({result['original_size']} bytes). Saved to: {result['filepath']}\n\n"
        msg += f"Preview ({len(result['preview'])} bytes):\n{result['preview']}"
        if result['has_more']:
            msg += "\n..."
        msg += "]"
        return msg

    def enforce_budget(self, tool_results: List[ToolResult]) -> List[ToolResult]:
        """
        强制执行预算

        返回处理后的工具结果列表
        """
        processed = []
        total_size = 0

        for tr in tool_results:
            size = len(tr.content.encode('utf-8'))

            # 检查是否已处理过
            replacement = self.state.get_replacement(tr.tool_use_id)
            if replacement:
                # 已替换过，保持相同替换
                tr.content = replacement
                processed.append(tr)
                continue

            if self.state.is_frozen(tr.tool_use_id):
                # 已见但未替换，保持原样
                processed.append(tr)
                total_size += size
                continue

            # 新内容，检查预算
            if size > self.MAX_TOOL_RESULT_BYTES or total_size + size > self.MAX_PER_MESSAGE_BYTES:
                # 需要持久化并替换
                persisted = self.persist_tool_result(tr.content, tr.tool_use_id)
                replacement_msg = self.build_replacement_message(persisted)

                tr.content = replacement_msg
                self.state.set_replacement(tr.tool_use_id, replacement_msg)
                print(f"[Budget] 工具结果 {tr.tool_name} 已持久化: {size} -> {len(replacement_msg)} bytes")
            else:
                # 在预算内，标记为已见但未替换 (frozen)
                self.state.mark_seen(tr.tool_use_id)
                total_size += size

            processed.append(tr)

        return processed


# ============================================================================
# 4. 上下文压缩 (模拟 compact.ts)
# ============================================================================

class CompactBoundary:
    """压缩边界标记"""
    def __init__(self, trigger: str, pre_tokens: int, messages_summarized: int):
        self.trigger = trigger  # 'manual' 或 'auto'
        self.pre_tokens = pre_tokens
        self.messages_summarized = messages_summarized
        self.timestamp = time.time()

    def to_message(self) -> Message:
        return Message(
            uuid=self._generate_uuid(),
            role='system',
            content=f"[Conversation compacted: {self.messages_summarized} messages, ~{self.pre_tokens} tokens]",
            metadata={'type': 'compact_boundary', 'trigger': self.trigger}
        )

    def _generate_uuid(self) -> str:
        return hashlib.md5(str(self.timestamp).encode()).hexdigest()[:16]


class ContextCompactor:
    """
    上下文压缩器 - 参考 src/services/compact/compact.ts

    策略:
    - 当token数超过阈值时触发压缩
    - 生成摘要消息替换旧消息
    - 保留最近的N条消息
    """
    def __init__(self, threshold_tokens: int = 100000, keep_recent: int = 10):
        self.threshold = threshold_tokens
        self.keep_recent = keep_recent
        self.compact_count = 0

    def should_compact(self, messages: List[Message]) -> bool:
        """检查是否应该压缩"""
        total_tokens = sum(m.estimate_tokens() for m in messages)
        return total_tokens > self.threshold

    def compact(self, messages: List[Message], trigger: str = 'auto') -> List[Message]:
        """
        执行压缩

        流程:
        1. 计算当前token总数
        2. 保留最近keep_recent条消息
        3. 生成摘要替换旧消息
        4. 添加边界标记
        """
        if len(messages) <= self.keep_recent:
            return messages

        pre_tokens = sum(m.estimate_tokens() for m in messages)

        # 保留的消息
        kept_messages = messages[-self.keep_recent:]

        # 需要摘要的消息
        to_summarize = messages[:-self.keep_recent]

        # 生成摘要 (简化: 只统计信息)
        summary = self._generate_summary(to_summarize)

        # 创建边界标记
        boundary = CompactBoundary(
            trigger=trigger,
            pre_tokens=pre_tokens,
            messages_summarized=len(to_summarize)
        )

        # 构建压缩后的消息列表
        result = [
            boundary.to_message(),
            Message(
                uuid=self._generate_uuid(),
                role='user',
                content=f"[Earlier conversation summary]:\n{summary}",
                metadata={'is_compact_summary': True}
            )
        ]
        result.extend(kept_messages)

        self.compact_count += 1
        print(f"[Compact] 压缩完成: {len(to_summarize)} -> {len(result)} messages, "
              f"tokens: {pre_tokens} -> {sum(m.estimate_tokens() for m in result)}")

        return result

    def _generate_summary(self, messages: List[Message]) -> str:
        """生成摘要 (简化版)"""
        by_role: Dict[str, int] = {}
        for m in messages:
            by_role[m.role] = by_role.get(m.role, 0) + 1

        summary_parts = [
            f"Total messages: {len(messages)}",
            f"Message breakdown: {by_role}",
            f"Topics: {self._extract_topics(messages)}"
        ]
        return "\n".join(summary_parts)

    def _extract_topics(self, messages: List[Message]) -> List[str]:
        """提取话题 (简化: 基于关键词)"""
        keywords = ['file', 'code', 'test', 'build', 'error', 'fix']
        topics = set()
        for m in messages:
            for kw in keywords:
                if kw in m.content.lower():
                    topics.add(kw)
        return list(topics)[:5]

    def _generate_uuid(self) -> str:
        return hashlib.md5(str(time.time()).encode()).hexdigest()[:16]


# ============================================================================
# 5. 记忆持久化 (模拟 memdir/ 和 SessionMemory)
# ============================================================================

class MemoryManager:
    """
    记忆管理器 - 管理长期记忆

    层次:
    - User: ~/.claude/memory/
    - Project: ~/.claude/projects/<project>/memory/
    - Session: session_memory.md
    """
    def __init__(self, base_dir: str = "./claude_memory"):
        self.base_dir = Path(base_dir)
        self.user_dir = self.base_dir / "memory"
        self.projects_dir = self.base_dir / "projects"

        self.user_dir.mkdir(parents=True, exist_ok=True)
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    def get_project_memory_dir(self, project_name: str) -> Path:
        """获取项目记忆目录"""
        project_dir = self.projects_dir / project_name / "memory"
        project_dir.mkdir(parents=True, exist_ok=True)
        return project_dir

    def save_memory(self, memory_type: str, content: str, project: Optional[str] = None):
        """保存记忆"""
        if project:
            memory_file = self.get_project_memory_dir(project) / f"{memory_type}.md"
        else:
            memory_file = self.user_dir / f"{memory_type}.md"

        # 截断处理 (最大200行, 25KB)
        truncated = self._truncate_content(content)

        with open(memory_file, 'a') as f:
            f.write(f"\n\n## {datetime.now().isoformat()}\n")
            f.write(truncated)

        print(f"[Memory] 已保存到 {memory_file}")

    def _truncate_content(self, content: str, max_lines: int = 200, max_bytes: int = 25000) -> str:
        """截断内容 - 参考 memdir.ts 实现"""
        lines = content.split('\n')

        # 按行截断
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            content = '\n'.join(lines) + f"\n\n[WARNING: Truncated at {max_lines} lines]"

        # 按字节截断
        content_bytes = content.encode('utf-8')
        if len(content_bytes) > max_bytes:
            content = content_bytes[:max_bytes].decode('utf-8', errors='ignore')
            content += f"\n\n[WARNING: Truncated at {max_bytes} bytes]"

        return content

    def load_memory(self, memory_type: str, project: Optional[str] = None) -> str:
        """加载记忆"""
        if project:
            memory_file = self.get_project_memory_dir(project) / f"{memory_type}.md"
        else:
            memory_file = self.user_dir / f"{memory_type}.md"

        if not memory_file.exists():
            return ""

        with open(memory_file) as f:
            return f.read()


# ============================================================================
# 6. 主会话管理器 - 整合所有组件
# ============================================================================

class SessionManager:
    """
    会话管理器 - 整合所有记忆系统组件
    """
    def __init__(self, project_name: str = "default"):
        self.project = project_name
        self.messages: List[Message] = []
        self.file_cache = LRUFileCache()
        self.budget_manager = ToolResultBudgetManager()
        self.compactor = ContextCompactor()
        self.memory_manager = MemoryManager()

        # SessionMemory阈值
        self.init_threshold = 10000  # tokens
        self.update_threshold = 5000  # tokens
        self.tool_call_threshold = 10
        self.last_memory_update = 0
        self.tool_call_count = 0

    def add_message(self, role: str, content: str, **kwargs) -> Message:
        """添加消息"""
        msg = Message(
            uuid=self._generate_uuid(),
            role=role,
            content=content,
            parent_uuid=self.messages[-1].uuid if self.messages else None,
            **kwargs
        )
        self.messages.append(msg)

        # 检查是否需要自动压缩
        self._check_compact()

        # 检查是否需要更新SessionMemory
        self._check_session_memory()

        return msg

    def add_tool_result(self, tool_name: str, content: str) -> ToolResult:
        """添加工具结果 (带预算控制)"""
        self.tool_call_count += 1

        tool_id = self._generate_uuid()
        tr = ToolResult(tool_use_id=tool_id, tool_name=tool_name, content=content)

        # 应用预算
        processed = self.budget_manager.enforce_budget([tr])

        # 转换为消息
        msg = Message(
            uuid=tool_id,
            role='tool_result',
            content=processed[0].content,
            metadata={'tool_name': tool_name, 'tool_use_id': tool_id}
        )
        self.messages.append(msg)

        return tr

    def _check_compact(self):
        """检查是否需要压缩"""
        if self.compactor.should_compact(self.messages):
            self.messages = self.compactor.compact(self.messages, trigger='auto')

    def _check_session_memory(self):
        """检查是否需要更新SessionMemory"""
        current_tokens = sum(m.estimate_tokens() for m in self.messages)

        # 初始化检查
        if current_tokens < self.init_threshold:
            return

        # 更新检查
        if current_tokens - self.last_memory_update >= self.update_threshold:
            # 提取关键信息并保存
            self._extract_and_save_memory()
            self.last_memory_update = current_tokens

    def _extract_and_save_memory(self):
        """提取并保存记忆"""
        # 简化: 统计最近消息的关键信息
        recent = self.messages[-10:]
        content = f"Session activity summary:\n"
        content += f"- Total messages: {len(self.messages)}\n"
        content += f"- Recent roles: {[m.role for m in recent]}\n"
        content += f"- Tool calls: {self.tool_call_count}\n"

        self.memory_manager.save_memory("session", content, self.project)

    def read_file(self, filepath: str) -> str:
        """读取文件 (带缓存)"""
        # 检查缓存
        cached = self.file_cache.get(filepath)
        if cached:
            print(f"[Cache] Hit: {filepath}")
            return cached.content

        # 读取文件
        try:
            with open(filepath, 'r') as f:
                content = f.read()
        except FileNotFoundError:
            return ""

        # 更新缓存
        state = FileState(content, time.time())
        self.file_cache.set(filepath, state)

        return content

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total_tokens = sum(m.estimate_tokens() for m in self.messages)
        return {
            'messages': len(self.messages),
            'total_tokens': total_tokens,
            'file_cache': self.file_cache.stats(),
            'compact_count': self.compactor.compact_count,
            'tool_call_count': self.tool_call_count
        }

    def _generate_uuid(self) -> str:
        return hashlib.md5(str(time.time()).encode()).hexdigest()[:16]


# ============================================================================
# 7. 演示
# ============================================================================

def demo():
    """演示记忆系统的各个组件"""
    print("=" * 60)
    print("Claude Code 记忆系统简化实现 (MRE)")
    print("=" * 60)

    # 创建会话管理器
    session = SessionManager(project_name="demo_project")

    print("\n--- 1. 基础消息流 ---")
    session.add_message('user', 'Hello, can you help me analyze this codebase?')
    session.add_message('assistant', 'Sure! Let me start by exploring the project structure.')

    print(f"Messages: {len(session.messages)}")
    print(f"Stats: {session.get_stats()}")

    print("\n--- 2. 文件缓存机制 ---")
    # 创建一个测试文件
    test_file = "./test_source.py"
    with open(test_file, 'w') as f:
        f.write("# This is a test file\n" * 100)

    # 第一次读取 (缓存未命中)
    content1 = session.read_file(test_file)
    print(f"First read: {len(content1)} chars")

    # 第二次读取 (缓存命中)
    content2 = session.read_file(test_file)
    print(f"Cache stats: {session.file_cache.stats()}")

    print("\n--- 3. 工具结果预算控制 ---")
    # 大工具结果
    large_content = "Large tool result content\n" * 5000  # ~140KB
    session.add_tool_result('FileRead', large_content)

    print(f"Messages after large result: {len(session.messages)}")

    # 添加更多消息触发压缩
    print("\n--- 4. 自动压缩机制 ---")
    for i in range(50):
        session.add_message('user', f'Message {i}: ' + 'x' * 1000)
        session.add_message('assistant', f'Response {i}: ' + 'y' * 2000)

    print(f"Final stats: {session.get_stats()}")

    print("\n--- 5. 记忆持久化 ---")
    # 添加一些用户偏好
    session.memory_manager.save_memory(
        'user',
        "User prefers TypeScript over JavaScript",
        'demo_project'
    )

    # 加载记忆
    user_mem = session.memory_manager.load_memory('user', 'demo_project')
    print(f"User memory:\n{user_mem}")

    # 清理测试文件
    import os
    os.remove(test_file)

    print("\n" + "=" * 60)
    print("演示完成!")
    print("=" * 60)


if __name__ == '__main__':
    demo()
