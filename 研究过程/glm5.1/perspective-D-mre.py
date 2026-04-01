#!/usr/bin/env python3
"""
Claude Code 记忆系统 - 最小化复现实现

这个Python脚本复现了Claude Code记忆系统的核心原理：
- 分层记忆存储 (短期/长期/团队)
- Context修剪策略
- 记忆提取和持久化
- 上下文窗口管理

核心概念简化：
1. 消息按轮次组织，每轮包含用户消息和助手响应
2. Token计数近似为字符数除以4
3. 压缩保留最近N条消息
4. 记忆按类型分类并持久化
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


class MemoryType(Enum):
    """记忆类型分类"""
    USER = "user"
    FEEDBACK = "feedback"
    PROJECT = "project"
    REFERENCE = "reference"


@dataclass
class Message:
    """消息结构"""
    uuid: str
    role: str  # "user" or "assistant"
    content: str
    timestamp: float
    tool_calls: List[str] = field(default_factory=list)
    message_id: Optional[str] = None  # 用于normalizeMessagesForAPI合并


@dataclass
class Memory:
    """记忆结构"""
    name: str
    description: str
    memory_type: MemoryType
    content: str
    file_path: str  # 相对路径，如 "user_role.md"


@dataclass
class CompactionResult:
    """压缩结果"""
    boundary_marker: str
    summary: str
    kept_messages: List[Message]
    pre_token_count: int
    post_token_count: int


class TokenCounter:
    """Token计数器 (近似实现)"""

    @staticmethod
    def count_tokens(text: str) -> int:
        """粗略估计token数：字符数/4"""
        return len(text) // 4

    @staticmethod
    def count_messages(messages: List[Message]) -> int:
        """计算消息列表的总token数"""
        total = 0
        for msg in messages:
            total += TokenCounter.count_tokens(msg.content)
            # 估算工具调用的开销
            total += len(msg.tool_calls) * 50
        return total


class ShortTermMemory:
    """短期记忆 (Session Memory)"""

    def __init__(self, memory_dir: Path):
        self.memory_dir = memory_dir / "session-memory"
        self.memory_file = self.memory_dir / "session.md"
        self.last_summarized_uuid: Optional[str] = None
        self.tokens_at_last_extraction = 0

        # 配置
        self.min_tokens_to_init = 10000
        self.min_tokens_between_update = 5000
        self.tool_calls_between_updates = 3

    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self.last_summarized_uuid is not None

    def should_extract(self, messages: List[Message], tool_calls_since: int) -> bool:
        """判断是否应该提取记忆"""
        current_tokens = TokenCounter.count_messages(messages)

        # 检查初始化阈值
        if not self.is_initialized():
            if current_tokens < self.min_tokens_to_init:
                return False
            self.last_summarized_uuid = messages[-1].uuid if messages else None
            return True

        # 检查更新间隔
        tokens_growth = current_tokens - self.tokens_at_last_extraction
        has_token_threshold = tokens_growth >= self.min_tokens_between_update
        has_tool_threshold = tool_calls_since >= self.tool_calls_between_updates

        # 最后一条消息是否没有工具调用（自然休息点）
        last_has_tools = len(messages[-1].tool_calls) > 0 if messages else False

        return (has_token_threshold and has_tool_threshold) or (
            has_token_threshold and not last_has_tools
        )

    def get_template(self) -> str:
        """获取Session Memory模板"""
        return """# Session Title
_A short and distinctive 5-10 word descriptive title_

# Current State
_What is actively being worked on right now?_

# Task specification
_What did the user ask to build?_

# Files and Functions
_What are the important files?_

# Errors & Corrections
_Errors encountered and how they were fixed_

# Learnings
_What has worked well? What has not?_
"""

    def save(self, content: str) -> None:
        """保存记忆到文件"""
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.memory_file.write_text(content, encoding="utf-8")
        self.tokens_at_last_extraction = TokenCounter.count_tokens(content)


class LongTermMemory:
    """长期记忆 (Auto Memory)"""

    def __init__(self, memory_dir: Path):
        self.memory_dir = memory_dir / "memory"
        self.index_file = self.memory_dir / "MEMORY.md"
        self.max_index_lines = 200
        self.max_index_bytes = 25000

    def get_memory_path(self, memory: Memory) -> Path:
        """获取记忆文件的完整路径"""
        return self.memory_dir / memory.file_path

    def save(self, memory: Memory) -> None:
        """保存记忆"""
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        # 生成frontmatter格式
        frontmatter = f"""---
name: {memory.name}
description: {memory.description}
type: {memory.memory_type.value}
---

{memory.content}
"""

        # 写入记忆文件
        memory_path = self.get_memory_path(memory)
        memory_path.write_text(frontmatter, encoding="utf-8")

        # 更新索引
        self._update_index(memory)

    def _update_index(self, memory: Memory) -> None:
        """更新MEMORY.md索引"""
        # 读取现有索引
        existing_index = ""
        if self.index_file.exists():
            existing_index = self.index_file.read_text(encoding="utf-8")

        # 添加新条目
        new_entry = f"- [{memory.name}]({memory.file_path}) — {memory.description}\n"

        # 检查是否需要截断
        updated_index = existing_index + new_entry
        lines = updated_index.split("\n")

        if len(lines) > self.max_index_lines or len(updated_index) > self.max_index_bytes:
            # 截断并添加警告
            lines = lines[: self.max_index_lines]
            lines.append("\n> WARNING: MEMORY.md exceeds limit. Condense entries.")
            updated_index = "\n".join(lines)

        self.index_file.write_text(updated_index, encoding="utf-8")

    def load(self) -> str:
        """加载记忆内容"""
        if not self.index_file.exists():
            return "Your MEMORY.md is currently empty."

        content = self.index_file.read_text(encoding="utf-8")
        lines = content.split("\n")

        # 应用截断
        if len(lines) > self.max_index_lines:
            lines = lines[: self.max_index_lines]
            lines.append("\n> WARNING: MEMORY.md exceeds limit.")
            return "\n".join(lines)

        return content


class TeamMemory:
    """团队记忆 (Team Memory)"""

    def __init__(self, memory_dir: Path):
        self.memory_dir = memory_dir / "memory" / "team"
        self.sync_state = {
            "last_checksum": None,
            "server_checksums": {},
        }

    def get_memory_path(self, memory: Memory) -> Path:
        """获取团队记忆文件的完整路径"""
        return self.memory_dir / memory.file_path

    def save(self, memory: Memory) -> None:
        """保存团队记忆"""
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        frontmatter = f"""---
name: {memory.name}
description: {memory.description}
type: {memory.memory_type.value}
---

{memory.content}
"""

        memory_path = self.get_memory_path(memory)
        memory_path.write_text(frontmatter, encoding="utf-8")

    def compute_hash(self, content: str) -> str:
        """计算内容哈希"""
        return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()

    def should_sync(self, local_content: str) -> bool:
        """检查是否需要同步（哈希不同）"""
        local_hash = self.compute_hash(local_content)
        return self.sync_state["server_checksums"].get(local_content) != local_hash


class ContextManager:
    """上下文管理器"""

    def __init__(self, context_window: int = 200000):
        self.context_window = context_window
        self.autocompact_buffer = 13000
        self.manual_compact_buffer = 3000

    def get_effective_window(self) -> int:
        """获取有效上下文窗口（预留摘要空间）"""
        return self.context_window - 20000  # 预留20K用于摘要

    def get_auto_compact_threshold(self) -> int:
        """获取自动压缩阈值"""
        return self.get_effective_window() - self.autocompact_buffer

    def calculate_warning_state(self, token_count: int) -> Dict[str, Any]:
        """计算警告状态"""
        threshold = self.get_auto_compact_threshold()
        effective_window = self.get_effective_window()
        warning_threshold = threshold - 20000
        error_threshold = threshold - 20000

        return {
            "percent_left": max(0, int(((threshold - token_count) / threshold) * 100)),
            "is_above_warning": token_count >= warning_threshold,
            "is_above_error": token_count >= error_threshold,
            "is_above_auto_compact": token_count >= threshold,
            "is_at_blocking_limit": token_count >= (effective_window - self.manual_compact_buffer),
        }


class CompactionService:
    """压缩服务"""

    def __init__(self, context_manager: ContextManager):
        self.context_manager = context_manager

    def microcompact(self, messages: List[Message]) -> List[Message]:
        """微压缩：清理旧的工具结果"""
        compactable_tools = {
            "read_file", "bash", "grep", "glob",
            "web_search", "web_fetch", "edit_file", "write_file"
        }

        # 统计每个工具ID的出现次数
        tool_counts: Dict[str, int] = {}
        for msg in messages:
            for tool_id in msg.tool_calls:
                tool_counts[tool_id] = tool_counts.get(tool_id, 0) + 1

        # 保留最近使用的工具结果
        recent_tools = set(list(tool_counts.keys())[-10:])  # 保留最近10个

        # 清理旧工具结果内容
        result = []
        for msg in messages:
            new_content = msg.content
            if msg.tool_calls:
                # 简化：如果有旧工具调用，添加标记
                old_calls = [tid for tid in msg.tool_calls if tid not in recent_tools]
                if old_calls:
                    new_content = f"[{len(old_calls)} old tool results cleared]\n" + msg.content

            result.append(Message(
                uuid=msg.uuid,
                role=msg.role,
                content=new_content,
                timestamp=msg.timestamp,
                tool_calls=msg.tool_calls,
                message_id=msg.message_id,
            ))

        return result

    def compact_conversation(
        self, messages: List[Message], keep_recent: int = 20
    ) -> CompactionResult:
        """压缩对话"""
        pre_count = TokenCounter.count_messages(messages)

        # 保留最近N条消息
        kept_messages = messages[-keep_recent:] if len(messages) > keep_recent else messages

        # 生成摘要（简化版）
        summary_lines = [
            f"# Summary of {len(messages) - len(kept_messages)} earlier messages",
            "",
            "## Primary Request",
            "User requested assistance with development tasks.",
            "",
            "## Current State",
            f"Conversation had {pre_count} tokens before compaction.",
            f"Keeping most recent {len(kept_messages)} messages.",
        ]

        summary = "\n".join(summary_lines)

        # 创建边界标记
        boundary_marker = f"[compact boundary: pre={pre_count} tokens]"

        return CompactionResult(
            boundary_marker=boundary_marker,
            summary=summary,
            kept_messages=kept_messages,
            pre_token_count=pre_count,
            post_token_count=TokenCounter.count_messages(kept_messages) + TokenCounter.count_tokens(summary),
        )


class MemoryExtractionService:
    """记忆提取服务"""

    def __init__(self, short_term: ShortTermMemory, long_term: LongTermMemory):
        self.short_term = short_term
        self.long_term = long_term

    def extract(self, messages: List[Message]) -> List[Memory]:
        """从消息中提取记忆"""
        memories = []

        # 简化版：基于关键词检测
        text = "\n".join(m.content for m in messages)

        # 检测用户偏好
        if "prefer" in text.lower() or "don't" in text.lower():
            memories.append(Memory(
                name="user_preferences",
                description="User work preferences",
                memory_type=MemoryType.FEEDBACK,
                content="User has specific preferences about work style.",
                file_path="feedback_preferences.md",
            ))

        # 检测项目信息
        if "project" in text.lower() or "deadline" in text.lower():
            memories.append(Memory(
                name="project_context",
                description="Project goals and deadlines",
                memory_type=MemoryType.PROJECT,
                content="Project has specific goals and deadlines.",
                file_path="project_goals.md",
            ))

        return memories


class ClaudeCodeMemorySystem:
    """Claude Code 记忆系统主类"""

    def __init__(self, workspace: Path, context_window: int = 200000):
        self.workspace = workspace
        self.context_manager = ContextManager(context_window)
        self.short_term = ShortTermMemory(workspace)
        self.long_term = LongTermMemory(workspace)
        self.team_memory = TeamMemory(workspace)
        self.compaction = CompactionService(self.context_manager)
        self.extraction = MemoryExtractionService(self.short_term, self.long_term)

        self.messages: List[Message] = []
        self.message_counter = 0

    def add_message(self, role: str, content: str, tool_calls: List[str] = None) -> str:
        """添加新消息"""
        self.message_counter += 1
        uuid = f"msg_{self.message_counter}"

        message = Message(
            uuid=uuid,
            role=role,
            content=content,
            timestamp=datetime.now().timestamp(),
            tool_calls=tool_calls or [],
        )

        self.messages.append(message)
        return uuid

    def check_context_pressure(self) -> Dict[str, Any]:
        """检查上下文压力"""
        token_count = TokenCounter.count_messages(self.messages)
        return self.context_manager.calculate_warning_state(token_count)

    def maybe_compact(self) -> Optional[CompactionResult]:
        """根据上下文压力决定是否压缩"""
        state = self.check_context_pressure()

        if state["is_at_blocking_limit"]:
            # 紧急压缩
            return self.compaction.compact_conversation(self.messages, keep_recent=5)
        elif state["is_above_auto_compact"]:
            # 自动压缩
            return self.compaction.compact_conversation(self.messages, keep_recent=20)

        return None

    def update_session_memory(self) -> bool:
        """更新会话记忆"""
        tool_calls = sum(len(m.tool_calls) for m in self.messages)
        if self.short_term.should_extract(self.messages, tool_calls):
            template = self.short_term.get_template()
            # 简化：直接使用模板
            self.short_term.save(template)
            self.short_term.last_summarized_uuid = self.messages[-1].uuid
            return True
        return False

    def extract_and_save_memories(self) -> List[Memory]:
        """提取并保存记忆"""
        memories = self.extraction.extract(self.messages)
        for memory in memories:
            if memory.memory_type in (MemoryType.USER, MemoryType.FEEDBACK):
                self.long_term.save(memory)
            else:
                self.team_memory.save(memory)
        return memories

    def get_context_summary(self) -> str:
        """获取上下文摘要"""
        lines = [
            f"=== Claude Code Memory System ===",
            f"",
            f"Messages: {len(self.messages)}",
            f"Tokens: {TokenCounter.count_messages(self.messages)}",
            f"Context Window: {self.context_manager.context_window}",
            f"",
            f"=== Memory State ===",
            f"Short Term: {'Initialized' if self.short_term.is_initialized() else 'Not Initialized'}",
            f"Long Term: {self.long_term.memory_dir}",
            f"Team Memory: {self.team_memory.memory_dir}",
        ]

        return "\n".join(lines)


# ==================== 演示 ====================

def main():
    """演示记忆系统的使用"""
    import tempfile

    # 创建临时工作区
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        system = ClaudeCodeMemorySystem(workspace, context_window=100000)

        print("=== Claude Code 记忆系统演示 ===\n")

        # 添加一些消息
        system.add_message("user", "I prefer using bun instead of npm")
        system.add_message("assistant", "I'll remember to use bun", tool_calls=["tool_1"])
        system.add_message("user", "Help me with the authentication module")
        system.add_message("assistant", "Let me read the auth files", tool_calls=["tool_2", "tool_3"])

        # 检查上下文状态
        state = system.check_context_pressure()
        print(f"上下文状态: {json.dumps(state, indent=2)}\n")

        # 更新会话记忆
        if system.update_session_memory():
            print("✓ 会话记忆已更新\n")

        # 提取长期记忆
        memories = system.extract_and_save_memories()
        print(f"✓ 提取了 {len(memories)} 条长期记忆\n")

        # 显示摘要
        print(system.get_context_summary())

        # 模拟上下文溢出
        print("\n=== 模拟上下文溢出 ===")
        for i in range(100):
            system.add_message("user", f"Message {i} with some content")
            system.add_message("assistant", f"Response {i}", tool_calls=[f"tool_{i}"])

        state = system.check_context_pressure()
        print(f"Tokens: {TokenCounter.count_messages(system.messages)}")
        print(f"需要压缩: {state['is_above_auto_compact']}")

        # 执行压缩
        result = system.maybe_compact()
        if result:
            print(f"✓ 压缩完成: {result.pre_token_count} → {result.post_token_count} tokens")
            print(f"  保留消息: {len(result.kept_messages)}")


if __name__ == "__main__":
    main()
