#!/usr/bin/env python3
"""
最小化实现：工具集成系统
展示：工具注册、权限验证、编排执行
"""

from dataclasses import dataclass
from typing import Optional, Callable, Any, Dict, List, Tuple
from enum import Enum
import asyncio
from abc import ABC, abstractmethod


class PermissionBehavior(Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


@dataclass
class PermissionResult:
    """权限验证结果"""
    behavior: PermissionBehavior
    reason: Optional[str] = None
    updated_input: Optional[dict] = None


@dataclass
class ToolDefinition:
    """工具定义"""
    name: str
    description: str
    input_schema: dict
    is_read_only: bool = False
    is_destructive: bool = False


class BaseTool(ABC):
    """工具基类"""

    def __init__(self, definition: ToolDefinition):
        self.definition = definition

    @abstractmethod
    async def execute(self, args: dict, context: Any) -> Any:
        """执行工具"""
        pass

    async def validate_input(self, args: dict) -> Tuple[bool, Optional[str]]:
        """验证输入"""
        required = self.definition.input_schema.get('required', [])
        for field in required:
            if field not in args:
                return False, f"Missing required field: {field}"
        return True, None

    async def check_permissions(
        self,
        args: dict,
        context: Any
    ) -> PermissionResult:
        """权限检查"""
        return PermissionResult(PermissionBehavior.ALLOW)


class BashTool(BaseTool):
    """Bash 工具示例"""

    def __init__(self):
        super().__init__(ToolDefinition(
            name="Bash",
            description="Execute bash commands",
            input_schema={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"]
            },
            is_destructive=True
        ))

    async def execute(self, args: dict, context: Any) -> str:
        cmd = args.get('command')
        return f"[Bash output] {cmd}"

    async def check_permissions(self, args, context) -> PermissionResult:
        # 自定义权限逻辑：拒绝危险命令
        cmd = args.get('command', '')
        dangerous = ['rm -rf /', 'sudo rm', 'mkfs']
        if any(d in cmd for d in dangerous):
            return PermissionResult(
                PermissionBehavior.DENY,
                "Dangerous command detected"
            )
        return PermissionResult(PermissionBehavior.ALLOW)


class ToolOrchestrator:
    """工具编排器"""

    def __init__(self, tools: List[BaseTool]):
        self.tools = {t.definition.name: t for t in tools}
        self._permission_rules: List[Callable] = []

    def register_permission_rule(self, rule: Callable):
        """注册权限规则"""
        self._permission_rules.append(rule)

    async def can_use_tool(
        self,
        tool_name: str,
        args: dict,
        context: Any
    ) -> PermissionResult:
        """检查工具是否可用"""
        tool = self.tools.get(tool_name)
        if not tool:
            return PermissionResult(
                PermissionBehavior.DENY,
                f"Tool not found: {tool_name}"
            )

        # 1. 工具级权限检查
        tool_result = await tool.check_permissions(args, context)
        if tool_result.behavior != PermissionBehavior.ALLOW:
            return tool_result

        # 2. 全局规则检查
        for rule in self._permission_rules:
            rule_result = await rule(tool_name, args, context)
            if rule_result.behavior == PermissionBehavior.DENY:
                return rule_result

        return PermissionResult(PermissionBehavior.ALLOW)

    async def execute_tool(
        self,
        tool_name: str,
        args: dict,
        context: Any,
        can_use_tool_fn: Callable
    ) -> Any:
        """执行工具（带权限检查）"""
        # 1. 权限检查
        permission = await can_use_tool_fn(tool_name, args, context)

        if permission.behavior == PermissionBehavior.DENY:
            raise PermissionError(
                f"Tool {tool_name} denied: {permission.reason}"
            )

        if permission.behavior == PermissionBehavior.ASK:
            user_choice = await self._ask_user(tool_name, args)
            if not user_choice:
                raise PermissionError("User denied")

        # 2. 输入验证
        tool = self.tools.get(tool_name)
        valid, error = await tool.validate_input(args)
        if not valid:
            raise ValueError(f"Invalid input: {error}")

        # 3. 应用输入更新
        if permission.updated_input:
            args = permission.updated_input

        # 4. 执行
        return await tool.execute(args, context)

    async def _ask_user(self, tool_name: str, args: dict) -> bool:
        """询问用户（简化实现）"""
        print(f"Permission requested: {tool_name}")
        print(f"Arguments: {args}")
        return True

    async def execute_multiple(
        self,
        tool_calls: List[Tuple[str, dict]],
        context: Any,
        concurrency_safe: bool = True
    ) -> List[Any]:
        """执行多个工具调用"""
        if concurrency_safe:
            return await asyncio.gather(*[
                self.execute_tool(name, args, context, self.can_use_tool)
                for name, args in tool_calls
            ])
        else:
            results = []
            for name, args in tool_calls:
                result = await self.execute_tool(
                    name, args, context, self.can_use_tool
                )
                results.append(result)
            return results


# 使用示例
async def demo():
    tools = [BashTool()]
    orchestrator = ToolOrchestrator(tools)

    # 注册全局权限规则
    async def no_sudo_rule(tool_name, args, context):
        if 'sudo' in args.get('command', ''):
            return PermissionResult(
                PermissionBehavior.ASK,
                "sudo requires confirmation"
            )
        return PermissionResult(PermissionBehavior.ALLOW)

    orchestrator.register_permission_rule(no_sudo_rule)

    # 执行工具
    context = None
    result = await orchestrator.execute_tool(
        "Bash",
        {"command": "echo hello"},
        context,
        orchestrator.can_use_tool
    )
    print(f"Result: {result}")


if __name__ == "__main__":
    asyncio.run(demo())
