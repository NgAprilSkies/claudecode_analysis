# 视角 C：工具集成 - 挑战性工程问题

## 问题：工具系统的安全隐患

### 背景

当前的工具系统设计非常灵活，但存在以下安全隐患：

1. **输入验证分散**
   - 每个工具自己实现 `validateInput`，标准不一致
   - 有些工具可能没有实现验证逻辑
   - 难以保证所有工具都遵循相同的验证标准

2. **权限规则冲突**
   - 多条规则可能产生冲突的决策
   - 当前优先级规则简单（deny > ask > allow）
   - 难以处理复杂的权限场景

3. **工具注入风险**
   - 动态加载的工具可能绕过来路检查
   - MCP 服务器的工具注册缺乏签名验证
   - 第三方插件可能引入恶意工具

4. **沙箱逃逸**
   - Bash 工具的沙箱机制可能不是绝对安全
   - 某些命令可能突破限制访问系统资源
   - 缺乏细粒度的资源访问控制

---

## 思考题

设计一个更安全的工具执行框架，需要考虑：

### 1. 统一输入验证层

```python
class SchemaValidator:
    def __init__(self):
        self.schemas = {}

    def register_schema(self, tool_name: str, schema: dict):
        """注册工具 Schema"""
        self.schemas[tool_name] = schema

    def validate(self, tool_name: str, args: dict) -> Tuple[bool, str]:
        """集中验证"""
        schema = self.schemas.get(tool_name)
        if not schema:
            return False, f"No schema for tool: {tool_name}"
        # JSON Schema 验证逻辑
        ...
```

### 2. 规则冲突解决

```python
class PermissionResolver:
    """权限规则解析器"""

    # 优先级：deny > ask > allow
    PRIORITY_ORDER = {'deny': 0, 'ask': 1, 'allow': 2}

    def resolve(self, rules: List[PermissionRule]) -> PermissionResult:
        """解决规则冲突"""
        if not rules:
            return PermissionResult(PermissionBehavior.ALLOW)

        # 按优先级排序
        rules.sort(key=lambda r: self.PRIORITY_ORDER.get(r.behavior, 2))

        # 返回最高优先级的规则
        highest = rules[0]
        return PermissionResult(
            highest.behavior,
            reason=f"Rule: {highest.pattern}"
        )
```

### 3. 工具签名验证

```python
class ToolSignatureVerifier:
    """工具签名验证器"""

    def __init__(self, trusted_signers: List[str]):
        self.trusted_signers = trusted_signers
        self.verified_tools = {}

    def verify_tool(self, tool_name: str, signature: str) -> bool:
        """验证工具签名"""
        # 验证逻辑：检查签名是否来自可信签名者
        ...
        return True

    def register_tool(self, tool_name: str, signature: str):
        """注册已验证工具"""
        if not self.verify_tool(tool_name, signature):
            raise SecurityError(f"Unverified tool: {tool_name}")
        self.verified_tools[tool_name] = True
```

---

## 延伸思考

1. **执行沙箱**: 如何设计多层隔离机制？
   - 系统调用层沙箱
   - 文件系统访问限制
   - 网络访问控制

2. **审计日志**: 如何记录工具执行的完整追踪？
   - 输入/输出日志
   - 权限决策日志
   - 异常行为检测

3. **速率限制**: 如何防止工具滥用？
   - 单工具调用频率限制
   - 资源消耗配额管理
   - 并发执行数量控制

4. **回滚机制**: 如何处理工具执行失败后的状态恢复？
   - 事务性执行
   - 撤销操作支持
   - 状态快照
