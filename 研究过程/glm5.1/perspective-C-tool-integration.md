# 视角C: 工具集成分析 (Tool Integration)

## 1. 架构概述

Claude Code 的工具系统是一个**多层防御的安全执行框架**，核心设计理念是"**安全优先，可观察性贯穿**"。工具集成分为三层：定义层、注册层、执行层。

### 1.1 核心类型体系

**Tool 接口** (`Tool.ts:362-695`) 是所有工具的契约定义，包含约 40 个方法/属性：

```typescript
export type Tool<Input, Output, P> = {
  name: string                    // 工具唯一标识
  aliases?: string[]              // 向后兼容的别名
  call(args, context, canUseTool, parentMessage, onProgress): Promise<ToolResult<Output>>
  description(input, options): Promise<string>
  prompt(options): Promise<string>
  readonly inputSchema: Input     // Zod schema
  isConcurrencySafe(input): boolean  // 是否可并行
  isEnabled(): boolean            // 功能开关
  isReadOnly(input): boolean      // 是否只读
  isDestructive?(input): boolean  // 是否破坏性操作
  checkPermissions(input, context): Promise<PermissionResult>  // 权限检查
  validateInput?(input, context): Promise<ValidationResult>    // 输入验证
  maxResultSizeChars: number      // 结果大小限制
  // ... UI 渲染方法、搜索/折叠方法等
}
```

**buildTool 工厂函数** (`Tool.ts:783-792`) 提供安全默认值：

```typescript
const TOOL_DEFAULTS = {
  isEnabled: () => true,
  isConcurrencySafe: (_input?) => false,  // 默认不安全
  isReadOnly: (_input?) => false,         // 默认非只读
  isDestructive: (_input?) => false,
  checkPermissions: (input) => Promise.resolve({ behavior: 'allow', updatedInput: input }),
  toAutoClassifierInput: (_input?) => '',  // 默认跳过分类器
  userFacingName: (_input?) => '',
}
```

**Harness Engineering 评价**：这种 fail-closed 设计（默认不可并行、默认非只读）是正确的安全姿态。新工具默认需要显式声明安全性属性。

---

## 2. 工具注册与发现

### 2.1 工具池组装 (`tools.ts:193-251`)

`getAllBaseTools()` 是所有工具的**唯一真相来源**，返回约 30+ 内置工具：

```
AgentTool, BashTool, FileEditTool, FileWriteTool, FileReadTool,
GlobTool, GrepTool, NotebookEditTool, WebFetchTool, WebSearchTool,
TodoWriteTool, AskUserQuestionTool, SkillTool, EnterPlanModeTool,
TaskCreateTool, TaskGetTool, TaskUpdateTool, TaskListTool,
SendMessageTool, TeamCreateTool, TeamDeleteTool, MCPTool, ...
```

工具按**条件注册**：
- `feature('PROACTIVE')` → SleepTool
- `feature('AGENT_TRIGGERS')` → CronCreate/CronDelete/CronList
- `isAgentSwarmsEnabled()` → TeamCreate/TeamDelete
- `isWorktreeModeEnabled()` → EnterWorktree/ExitWorktree

### 2.2 权限过滤 (`tools.ts:262-269`)

```typescript
export function filterToolsByDenyRules(tools, permissionContext): T[] {
  return tools.filter(tool => !getDenyRuleForTool(permissionContext, tool))
}
```

**关键设计**：工具在到达 LLM 之前就被 deny 规则过滤掉了。模型永远看不到被禁止的工具，不是"看到了但不能调用"。

### 2.3 MCP 工具集成 (`tools.ts:345-367`)

```typescript
export function assembleToolPool(permissionContext, mcpTools): Tools {
  const builtInTools = getTools(permissionContext)
  const allowedMcpTools = filterToolsByDenyRules(mcpTools, permissionContext)
  const byName = (a, b) => a.name.localeCompare(b.name)
  return uniqBy(
    [...builtInTools].sort(byName).concat(allowedMcpTools.sort(byName)),
    'name',  // 内置工具优先于同名 MCP 工具
  )
}
```

**排序策略**：工具按名称排序以支持 **prompt cache**。内置工具作为连续前缀，MCP 工具追加在后，确保缓存键稳定性。

---

## 3. 权限控制系统（多层防御）

Claude Code 的权限系统是业界最精细的 Agent 安全框架之一，特别是 BashTool 的安全检查链。

### 3.1 权限决策流程

```
用户输入 → LLM 选择工具 → validateInput() → checkPermissions() → canUseTool() → 执行
                                ↓                    ↓                  ↓
                          输入合法性验证       工具级权限检查      通用权限框架
```

**PermissionResult 类型**：

```typescript
type PermissionResult = 
  | { behavior: 'allow', updatedInput }    // 允许（可能修改输入）
  | { behavior: 'deny', message }          // 拒绝
  | { behavior: 'ask', message, suggestions } // 需要用户确认
  | { behavior: 'passthrough', message }   // 传递给下一层
```

### 3.2 BashTool 安全检查链（深度分析）

BashTool 的权限检查是整个系统最复杂的部分，包含 **23+ 个安全验证器**：

#### 第一层：AST 解析 (`bashPermissions.ts:1663-1806`)

```typescript
// tree-sitter Bash 解析 — 替代旧的 regex/shell-quote 路径
const astRoot = await parseCommandRaw(input.command)
const astResult = parseForSecurityFromAst(input.command, astRoot)
```

三种结果：
- `simple` — 干净解析，可以静态分析
- `too-complex` — 包含命令替换/控制流，无法静态验证 → 降级到 ask
- `parse-unavailable` — tree-sitter 不可用 → 回退到 regex

#### 第二层：23 个安全验证器 (`bashSecurity.ts`)

每个验证器返回 `PermissionResult`，按顺序执行：

| # | 验证器 | 检测内容 | 安全等级 |
|---|--------|---------|---------|
| 1 | validateEmpty | 空命令 | 允许 |
| 2 | validateIncompleteCommands | 不完整片段（tab开头、flag开头） | 询问 |
| 3 | validateSafeCommandSubstitution | 安全 heredoc 替换 $(cat <<'EOF'...) | 允许 |
| 4 | validateGitCommit | git commit -m "简单消息" | 允许 |
| 5 | validateJqCommand | jq system() 函数 | 询问 |
| 6 | validateObfuscatedFlags | 引号混淆标记（ANSI-C quoting等） | 询问 |
| 7 | validateShellMetacharacters | 引号内的分号/管道 | 询问 |
| 8 | validateDangerousVariables | $VAR 在重定向/管道中 | 询问 |
| 9 | validateCommentQuoteDesync | # 注释内引号导致追踪器失同步 | 询问 |
| 10 | validateQuotedNewline | 引号内换行+下一行以#开头 | 询问 |
| 11 | validateCarriageReturn | \r 导致的解析差异 | 询问 |
| 12 | validateNewlines | 换行符分隔多命令 | 询问 |
| 13 | validateIFSInjection | $IFS 变量注入 | 询问 |
| 14 | validateProcEnvironAccess | /proc/*/environ 敏感文件访问 | 询问 |
| 15 | validateDangerousPatterns | 反引号/$()/${} 命令替换 | 询问 |
| 16 | validateRedirections | < > 重定向 | 询问 |
| 17 | validateBackslashEscapedWhitespace | \ 空格 逃逸 | 询问 |
| 18 | validateBackslashEscapedOperators | \; \| \& 操作符逃逸 | 询问 |
| 19 | validateUnicodeWhitespace | Unicode 空白字符注入 | 询问 |
| 20 | validateMidWordHash | 词中 # 的解析差异 | 询问 |
| 21 | validateBraceExpansion | {a,b} 大括号展开 | 询问 |
| 22 | validateZshDangerousCommands | zmodload, emulate, fc -e 等 | 询问 |
| 23 | validateMalformedTokenInjection | 畸形 token + 命令分隔符 | 询问 |

**Misparsing 分类**：验证器分为 misparsing 和 non-misparsing 两类。Misparsing 验证器的 `ask` 结果会被提前拦截（因为这意味着 shell-quote 和 bash 的解析结果不一致），non-misparsing 的 `ask` 结果延迟处理。

#### 第三层：规则匹配 (`bashPermissions.ts:1050-1178`)

```
1. Exact Match → deny/ask/allow
2. Prefix Match → Bash(git:*) 匹配 "git commit"
3. Wildcard Match → Bash(cd *) 匹配 "cd /any/path"
```

#### 第四层：路径约束 (`pathValidation.ts`)

检查文件路径是否在工作目录内，防止越权访问。

#### 第五层：模式检查 (`modeValidation.ts`)

根据 `PermissionMode`（default/acceptEdits/bypassPermissions/auto）进行最终判断。

### 3.3 异步分类器 (`bashPermissions.ts:1605-1658`)

```typescript
// 异步分类器在权限对话框显示时并行运行
// 如果高置信度允许，自动批准（用户无需等待）
if (classifierResult.matches && classifierResult.confidence === 'high') {
  callbacks.onAllow({ type: 'classifier', classifier: 'bash_allow', ... })
}
```

**设计精妙之处**：分类器（基于 LLM）在权限提示显示期间异步运行，如果高置信度匹配用户预定义的允许规则，可以自动批准，大幅减少用户交互摩擦。

---

## 4. 沙箱执行环境

### 4.1 沙箱管理器

```typescript
import { SandboxManager } from '../../utils/sandbox/sandbox-adapter.js'
```

沙箱为 BashTool 提供文件系统隔离：
- 当 `isSandboxingEnabled()` && `isAutoAllowBashIfSandboxedEnabled()` 时
- 沙箱中的命令自动允许（仍受 deny 规则约束）
- 路径重写确保文件操作限制在沙箱内

---

## 5. MCP 协议集成

### 5.1 MCPTool 设计 (`MCPTool.ts`)

MCPTool 是一个**占位工具**，在运行时被 MCP 服务器提供的实际工具覆盖：

```typescript
export const MCPTool = buildTool({
  isMcp: true,
  name: 'mcp',           // 运行时覆盖为实际名称
  maxResultSizeChars: 100_000,
  async call() { return { data: '' } },      // 运行时覆盖
  async checkPermissions() { 
    return { behavior: 'passthrough', message: 'MCPTool requires permission.' }
  },
})
```

### 5.2 MCP 工具生命周期

```
MCP 服务器连接 → 工具发现 → 动态创建 Tool 实例 → 注册到工具池 → 权限过滤 → 可用
```

---

## 6. Harness Engineering 评价

### 6.1 可扩展性

| 维度 | 评分 | 说明 |
|------|------|------|
| 新工具添加 | ★★★★★ | buildTool() 工厂 + Zod schema，只需实现接口 |
| MCP 扩展 | ★★★★★ | 标准协议，动态注册 |
| 条件加载 | ★★★★☆ | feature flags 控制，但分散在多处 require |

### 6.2 安全边界

| 维度 | 评分 | 说明 |
|------|------|------|
| 纵深防御 | ★★★★★ | 5 层权限检查，23+ 验证器 |
| Fail-closed | ★★★★★ | 默认不可并行/非只读，unknown = ask |
| AST vs Regex | ★★★★★ | tree-sitter 替代 regex 解析，消除解析差异 |
| 攻击面覆盖 | ★★★★★ | 覆盖 IFS 注入、Unicode 混淆、Zsh 危险命令等边缘场景 |

### 6.3 可观察性

| 维度 | 评分 | 说明 |
|------|------|------|
| 日志覆盖 | ★★★★★ | 每个验证器触发都有 analytics 事件 |
| 分类器遥测 | ★★★★☆ | shadow 模式对比 tree-sitter 和 regex 差异 |
| 权限决策追踪 | ★★★★☆ | decisionReason 类型链追踪每个决策 |

### 6.4 性能损耗

| 维度 | 评分 | 说明 |
|------|------|------|
| 工具注册 | ★★★★★ | 惰性加载 + 死代码消除 |
| 权限检查 | ★★★★☆ | AST 解析 + 23 个验证器，但有 speculative 预判 |
| 分类器延迟 | ★★★☆☆ | 异步 LLM 调用增加延迟，但与 UI 并行 |

---

## 7. 关键设计模式

### 7.1 策略模式 (Strategy Pattern)
- `checkPermissions()` 每个工具有自己的权限策略
- BashTool 有复杂的 5 层策略链

### 7.2 责任链模式 (Chain of Responsibility)
- 23 个验证器形成链式处理
- Early validators 可短路后续检查
- Deferred non-misparsing 结果延迟处理

### 7.3 观察者模式 (Observer Pattern)
- `onProgress` 回调实时报告工具执行进度
- `addNotification` 通知 UI 层

### 7.4 模板方法模式 (Template Method)
- `buildTool()` 提供骨架，子工具覆盖特定方法
- 安全默认值填充未实现的方法
