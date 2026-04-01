"""
视角C: 工具集成系统 — 最小化可运行实现 (MRE)

复现 Claude Code 工具系统的核心原理：
  1. Tool 接口 + buildTool 工厂（安全默认值）
  2. 工具注册 + 条件发现 + deny 规则过滤
  3. 多层权限检查（5 层纵深防御简化版）
  4. Bash 安全验证器链
  5. MCP 动态工具注册
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable
import re
import asyncio


# ─── 1. 核心类型定义 ───────────────────────────────────────────

@dataclass
class PermissionResult:
    """权限决策结果 — 与 Claude Code 的 PermissionResult 对应"""
    behavior: str  # 'allow' | 'deny' | 'ask' | 'passthrough'
    message: str = ""
    updated_input: dict | None = None
    suggestions: list = field(default_factory=list)

    @staticmethod
    def allow(updated_input=None):
        return PermissionResult("allow", updated_input=updated_input)

    @staticmethod
    def deny(msg="Denied"):
        return PermissionResult("deny", msg)

    @staticmethod
    def ask(msg="Requires approval"):
        return PermissionResult("ask", msg)

    @staticmethod
    def passthrough(msg="No decision"):
        return PermissionResult("passthrough", msg)


@runtime_checkable
class Tool(Protocol):
    """工具接口 — 对应 Tool.ts 中的 type Tool"""
    name: str
    def call(self, args: dict, context: dict) -> Any: ...
    def check_permissions(self, args: dict, context: dict) -> PermissionResult: ...
    def is_read_only(self, args: dict) -> bool: ...
    def is_enabled(self) -> bool: ...


# ─── 2. buildTool 工厂 — 安全默认值 ────────────────────────────

def build_tool(definition: dict) -> Tool:
    """
    对应 Tool.ts:783 buildTool()
    填充安全默认值：默认非只读、默认非并行、默认允许权限
    """
    class ConcreteTool:
        name = definition.get("name", "unknown")
        _call = definition.get("call", lambda args, ctx: {"data": None})
        _check_perms = definition.get("check_permissions",
            lambda args, ctx: PermissionResult.allow(args))
        _is_readonly = definition.get("is_read_only", lambda args: False)
        _is_enabled = definition.get("is_enabled", lambda: True)

        def call(self, args, ctx):        return self._call(args, ctx)
        def check_permissions(self, a, c): return self._check_perms(a, c)
        def is_read_only(self, args):     return self._is_readonly(args)
        def is_enabled(self):             return self._is_enabled

    return ConcreteTool()


# ─── 3. Bash 安全验证器链 ──────────────────────────────────────

# 对应 bashSecurity.ts 中 23 个验证器的简化版
BASH_SECURITY_VALIDATORS: list[Callable[[str], PermissionResult]] = [
    # V1: 空命令 → 允许
    lambda cmd: PermissionResult.allow()
        if not cmd.strip() else PermissionResult.passthrough(),
    # V2: 命令替换 $() → 询问
    lambda cmd: PermissionResult.ask("Command contains $() substitution")
        if re.search(r'\$\(', cmd) else PermissionResult.passthrough(),
    # V3: 反引号 → 询问
    lambda cmd: PermissionResult.ask("Command contains backtick substitution")
        if '`' in cmd and not cmd.count('`') % 2 == 0
        else PermissionResult.passthrough(),
    # V4: 管道/分号 → 询问（需逐段检查）
    lambda cmd: PermissionResult.ask("Command contains shell operators")
        if re.search(r'[;&|]', re.sub(r"'.*?'", '', re.sub(r'".*?"', '', cmd)))
        else PermissionResult.passthrough(),
    # V5: 重定向 → 询问
    lambda cmd: PermissionResult.ask("Command contains redirections")
        if re.search(r'[<>]', cmd) else PermissionResult.passthrough(),
]


def validate_bash_security(command: str) -> PermissionResult:
    """验证器链 — 对应 bashCommandIsSafe_DEPRECATED"""
    for validator in BASH_SECURITY_VALIDATORS:
        result = validator(command)
        if result.behavior != "passthrough":
            return result
    return PermissionResult.passthrough("Passed all security checks")


# ─── 4. 权限规则引擎 ───────────────────────────────────────────

@dataclass
class PermissionContext:
    """对应 ToolPermissionContext"""
    mode: str = "default"
    allow_rules: dict[str, list[str]] = field(default_factory=dict)
    deny_rules: dict[str, list[str]] = field(default_factory=dict)
    ask_rules: dict[str, list[str]] = field(default_factory=dict)


def match_rule(pattern: str, command: str) -> bool:
    """简化版规则匹配 — 支持 exact/prefix/wildcard"""
    if pattern == command:
        return True
    if pattern.endswith(":*"):
        return command.startswith(pattern[:-2])
    if pattern.endswith("*"):
        prefix = pattern[:-1]
        return re.search(re.escape(prefix), command) is not None
    return False


def check_permission_rules(
    tool_name: str, command: str, ctx: PermissionContext
) -> PermissionResult:
    """5 层纵深防御权限检查 — 对应 bashToolHasPermission 简化"""
    # Layer 1: Deny rules (最高优先级)
    for rule in ctx.deny_rules.get(tool_name, []):
        if match_rule(rule, command):
            return PermissionResult.deny(f"Denied by rule: {rule}")
    # Layer 2: Ask rules
    for rule in ctx.ask_rules.get(tool_name, []):
        if match_rule(rule, command):
            return PermissionResult.ask(f"Requires approval (rule: {rule})")
    # Layer 3: Security validators
    if tool_name == "Bash":
        sec_result = validate_bash_security(command)
        if sec_result.behavior == "ask":
            return sec_result
    # Layer 4: Allow rules
    for rule in ctx.allow_rules.get(tool_name, []):
        if match_rule(rule, command):
            return PermissionResult.allow({"command": command})
    # Layer 5: Default → ask
    return PermissionResult.ask("No matching rule — requires approval")


# ─── 5. 工具注册表 + MCP 动态工具 ──────────────────────────────

class ToolRegistry:
    """对应 tools.ts 的 getAllBaseTools + assembleToolPool"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._mcp_tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    def register_mcp(self, server: str, tool_name: str, handler: Callable):
        """对应 MCPTool 运行时覆盖机制"""
        full_name = f"mcp__{server}__{tool_name}"
        self._mcp_tools[full_name] = build_tool({
            "name": full_name,
            "call": handler,
            "is_mcp": True,
        })

    def get_tool_pool(self, ctx: PermissionContext) -> list[Tool]:
        """对应 assembleToolPool — 合并内置 + MCP，按 deny 规则过滤"""
        all_tools = list(self._tools.values()) + list(self._mcp_tools.values())
        return [t for t in all_tools if t.is_enabled()
                and not any(match_rule(r, t.name) for r in ctx.deny_rules.get("*", []))]


# ─── 6. 运行演示 ───────────────────────────────────────────────

async def demo():
    registry = ToolRegistry()
    # 注册内置工具
    registry.register(build_tool({"name": "Read", "call": lambda a, c: {"data": "file content"},
                                   "is_read_only": lambda a: True}))
    registry.register(build_tool({"name": "Bash", "call": lambda a, c: {"data": "executed"},
                                   "check_permissions": lambda a, c:
                                       check_permission_rules("Bash", a.get("command",""), c)}))
    # 注册 MCP 工具
    registry.register_mcp("github", "create_issue",
                           lambda a, c: {"data": f"Created issue: {a.get('title')}"})

    ctx = PermissionContext(
        mode="default",
        allow_rules={"Bash": ["git:*", "ls"]},
        deny_rules={"Bash": ["rm:*"]},
    )

    # 测试 5 层防御
    tests = [
        ("git status", "allow"),      # Layer 4: prefix allow
        ("rm -rf /", "deny"),         # Layer 1: prefix deny
        ("echo $(whoami)", "ask"),     # Layer 3: security validator
        ("python script.py", "ask"),   # Layer 5: no rule → ask
        ("ls", "allow"),              # Layer 4: exact allow
    ]
    print("=== Claude Code Tool Integration MRE ===\n")
    for cmd, expected in tests:
        result = check_permission_rules("Bash", cmd, ctx)
        status = "PASS" if result.behavior == expected else "FAIL"
        print(f"  {status} Bash({cmd:25s}) → {result.behavior:6s} (expected: {expected})")
        if result.message:
            print(f"     └─ {result.message}")

    pool = registry.get_tool_pool(ctx)
    print(f"\n  Tool pool ({len(pool)} tools): {[t.name for t in pool]}")


if __name__ == "__main__":
    asyncio.run(demo())
