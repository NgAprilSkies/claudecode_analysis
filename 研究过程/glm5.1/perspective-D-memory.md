# 视角D: Claude Code 记忆系统分析

## 1. 记忆系统的层次架构

Claude Code 实现了一个多层次记忆系统，用于管理会话上下文和持久化知识：

```
┌─────────────────────────────────────────────────────────────┐
│                     记忆系统层次结构                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 1. 短期记忆 (Session Memory)                          │   │
│  │    - 会话期间自动维护                                 │   │
│  │    - 位置: .claude/session-memory/session.md          │   │
│  │    - 触发: 每5000 tokens增长 + 3个工具调用             │   │
│  │    - 初始化阈值: 10000 tokens                         │   │
│  └─────────────────────────────────────────────────────┘   │
│                          ↓                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 2. 上下文压缩 (Compaction)                             │   │
│  │    - 自动触发: 达到 context窗口 - 13000 tokens         │   │
│  │    - 手动触发: /compact 命令                           │   │
│  │    - 微压缩: 清理旧工具结果 (cache_edits API)          │   │
│  │    - 会话记忆压缩: 使用SessionMemory替代API摘要         │   │
│  └─────────────────────────────────────────────────────┘   │
│                          ↓                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 3. 长期记忆 (Auto Memory)                              │   │
│  │    - 位置: ~/.claude/projects/<repo>/memory/           │   │
│  │    - 类型: user, feedback, project, reference         │   │
│  │    - 自动提取: 每轮对话结束时后台forked agent          │   │
│  │    - 索引: MEMORY.md (200行/25KB上限)                 │   │
│  └─────────────────────────────────────────────────────┘   │
│                          ↓                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 4. 团队记忆 (Team Memory)                              │   │
│  │    - 位置: ~/.claude/projects/<repo>/memory/team/      │   │
│  │    - 同步: 基于OAuth的API双向同步                      │   │
│  │    - 范围控制: 私有 vs 团队共享                         │   │
│  │    - 冲突解决: 乐观锁 (ETag) + delta上传               │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 2. Session Memory (会话记忆) 深度解析

### 2.1 架构设计

**核心文件**: `src/services/SessionMemory/sessionMemory.ts`

Session Memory 是一个自动维护的 Markdown 文件，包含当前会话的动态笔记。它在后台通过 forked subagent 运行，不阻塞主对话流程。

**关键阈值配置** (sessionMemoryUtils.ts:32-36):
```typescript
const DEFAULT_SESSION_MEMORY_CONFIG: SessionMemoryConfig = {
  minimumMessageTokensToInit: 10000,    // 初始化阈值
  minimumTokensBetweenUpdate: 5000,    // 更新间隔
  toolCallsBetweenUpdates: 3,          // 工具调用间隔
}
```

### 2.2 提取触发逻辑

**源码**: sessionMemory.ts:134-181

提取触发的两个条件（必须同时满足 token 阈值）：

1. **Token 阈值满足**: 上下文增长 ≥ 5000 tokens
2. **工具调用满足** 或 **自然对话休息点**:
   - 上次更新后 ≥ 3 个工具调用，或
   - 最后一条助手消息没有工具调用

```typescript
// sessionMemory.ts:168-180
const shouldExtract =
  (hasMetTokenThreshold && hasMetToolCallThreshold) ||
  (hasMetTokenThreshold && !hasToolCallsInLastTurn)
```

### 2.3 模板结构

**源码**: prompts.ts:11-41

Session Memory 使用固定模板结构：

```markdown
# Session Title
_5-10词的描述性标题_

# Current State
_正在进行的任务、待办事项、下一步行动_

# Task specification
_用户要求构建的内容、设计决策_

# Files and Functions
_重要文件及其作用_

# Workflow
_常用的bash命令及执行顺序_

# Errors & Corrections
_遇到的错误及修复方法_

# Codebase and System Documentation
_重要系统组件及其工作原理_

# Learnings
_有效的做法、应避免的做法_

# Key results
_用户要求的特定输出（表格、答案等）_

# Worklog
_逐步完成的工作总结_
```

### 2.4 限制与截断

**源码**: prompts.ts:7-9, 256-324

- **每节上限**: 2000 tokens
- **总上限**: 12000 tokens
- **超限处理**: 自动截断并添加警告

```typescript
// prompts.ts:256-263
export function truncateSessionMemoryForCompact(content: string): {
  truncatedContent: string
  wasTruncated: boolean
} {
  const maxCharsPerSection = MAX_SECTION_LENGTH * 4  // 2000 * 4 = 8000 chars
  // ... 截断逻辑
}
```

## 3. Context 构建与修剪策略

### 3.1 上下文窗口管理

**核心文件**: `src/services/compact/autoCompact.ts`

**自动压缩阈值计算** (autoCompact.ts:72-91):
```typescript
export function getAutoCompactThreshold(model: string): number {
  const effectiveContextWindow = getEffectiveContextWindowSize(model)
  return effectiveContextWindow - AUTOCOMPACT_BUFFER_TOKENS  // -13000
}

export function getEffectiveContextWindowSize(model: string): number {
  const reservedTokensForSummary = Math.min(
    getMaxOutputTokensForModel(model),
    MAX_OUTPUT_TOKENS_FOR_SUMMARY  // 20000
  )
  let contextWindow = getContextWindowForModel(model, getSdkBetas())
  return contextWindow - reservedTokensForSummary
}
```

**不同模型的窗口示例**:
- Claude Opus 4.6: 200000 tokens
- 有效窗口: 200000 - 20000 = 180000 tokens
- 自动压缩触发: 180000 - 13000 = 167000 tokens

### 3.2 微压缩 (Microcompact)

**核心文件**: `src/services/compact/microCompact.ts`

微压缩清理旧的工具结果以节省 tokens：

**可压缩的工具** (microCompact.ts:41-50):
```typescript
const COMPACTABLE_TOOLS = new Set<string>([
  FILE_READ_TOOL_NAME,
  ...SHELL_TOOL_NAMES,
  GREP_TOOL_NAME,
  GLOB_TOOL_NAME,
  WEB_SEARCH_TOOL_NAME,
  WEB_FETCH_TOOL_NAME,
  FILE_EDIT_TOOL_NAME,
  FILE_WRITE_TOOL_NAME,
])
```

**两种微压缩模式**:

1. **时间触发微压缩** (microCompact.ts:411-530):
   - 触发: 与最后一条助手消息间隔 ≥ 阈值（默认10分钟）
   - 行为: 直接修改消息内容，替换为 `[Old tool result content cleared]`
   - 原因: 缓存已过期，无需使用 cache_edits API

2. **缓存编辑微压缩** (microCompact.ts:305-399):
   - 使用 `cache_edits` API 块删除工具结果
   - 不修改本地消息内容
   - 保持缓存前缀有效
   - 基于 GrowthBook 配置的触发阈值

### 3.3 全量压缩流程

**核心文件**: `src/services/compact/compact.ts`

**压缩步骤** (compact.ts:387-763):

1. **执行 PreCompact Hooks** (line 413-424)
2. **构建压缩提示词** (compactPrompt from prompt.ts:19-143)
3. **流式生成摘要** (使用 forked agent 共享缓存)
4. **创建边界标记** (createCompactBoundaryMessage)
5. **重建附件** (文件、技能、代理状态等)
6. **执行 SessionStart Hooks** 恢复上下文
7. **返回压缩结果**

**压缩提示词结构** (prompt.ts:61-143):
```
<analysis>
[思考过程]
</analysis>

<summary>
1. Primary Request and Intent
2. Key Technical Concepts
3. Files and Code Sections
4. Errors and fixes
5. Problem Solving
6. All user messages
7. Pending Tasks
8. Current Work
9. Optional Next Step
</summary>
```

## 4. 会话记忆压缩 (Session Memory Compaction)

**核心文件**: `src/services/compact/sessionMemoryCompact.ts`

这是传统压缩的高效替代方案，直接使用 Session Memory 而非调用 API 生成摘要。

**配置** (sessionMemoryCompact.ts:57-61):
```typescript
export const DEFAULT_SM_COMPACT_CONFIG: SessionMemoryCompactConfig = {
  minTokens: 10_000,              // 最小保留 tokens
  minTextBlockMessages: 5,        // 最少保留消息数
  maxTokens: 40_000,              // 最大保留 tokens 硬上限
}
```

**计算保留范围** (sessionMemoryCompact.ts:324-397):
1. 从 `lastSummarizedMessageId` 之后开始
2. 向后扩展以满足:
   - 至少 `minTokens` tokens
   - 至少 `minTextBlockMessages` 条文本消息
3. 停止条件:
   - 达到 `maxTokens` 上限
   - 或两个最小值都满足
4. 调整索引以保护 tool_use/tool_result 配对

**API 不变性保护** (sessionMemoryCompact.ts:232-314):
- 确保 tool_use/tool_result 成对保留
- 保护共享 message.id 的 thinking 块
- 流式消息合并兼容性

## 5. 记忆提取机制

**核心文件**: `src/services/extractMemories/extractMemories.ts`

### 5.1 Forked Agent 模式

记忆提取使用 forked agent 模式（extractMemories.ts:15-16）:
- 与主对话完全相同的系统提示词
- 共享主对话的 prompt 缓存
- 在主对话写入记忆时自动跳过

### 5.2 提取触发逻辑

**源码**: extractMemories.ts:376-426

1. **特征门控**: `tengu_passport_quail`
2. **记忆已启用检查**: `isAutoMemoryEnabled()`
3. **非远程模式**: `!getIsRemoteMode()`
4. **节流控制**: 每 N 轮提取一次 (`tengu_bramble_lintel`，默认1)
5. **互斥检查**: 如果主 agent 已写入记忆，跳过

### 5.3 提取提示词

**源码**: prompts.ts:50-154

```markdown
You are now acting as the memory extraction subagent.
Analyze the most recent ~{newMessageCount} messages above...

Available tools: Read, Grep, Glob, read-only Bash, Edit/Write (memory only)

You have a limited turn budget. Efficient strategy:
Turn 1 — issue all Read calls in parallel
Turn 2 — issue all Edit/Write calls in parallel
```

### 5.4 记忆类型分类

**源码**: memoryTypes.ts:14-19, 37-178

四种记忆类型（闭环分类法）:

| 类型 | 范围 | 描述 | 示例 |
|------|------|------|------|
| user | 总是私有 | 用户角色、偏好、知识 | 数据科学家，Go专家但React新手 |
| feedback | 默认私有 | 工作方式指导 | "不要mock数据库"、"停止总结diff" |
| project | 倾向团队 | 项目状态、目标、事故 | 合并冻结、合规驱动的重写 |
| reference | 通常团队 | 外部系统指针 | Linear项目、Grafana仪表板 |

**明确排除的内容** (memoryTypes.ts:183-195):
```markdown
- Code patterns, conventions, architecture, file paths, or project structure
- Git history, recent changes, or who-changed-what
- Debugging solutions or fix recipes
- Anything already documented in CLAUDE.md files
- Ephemeral task details: in-progress work, temporary state
```

## 6. 团队记忆同步

**核心文件**: `src/services/teamMemorySync/index.ts`

### 6.1 API 契约

```
GET  /api/claude_code/team_memory?repo={owner/repo}            → TeamMemoryData
GET  /api/claude_code/team_memory?repo={owner/repo}&view=hashes → metadata + entryChecksums
PUT  /api/claude_code/team_memory?repo={owner/repo}            → upload entries (upsert)
```

### 6.2 同步语义

**拉取** (index.ts:770-867):
- 服务器胜: 拉取覆盖本地文件
- ETag 缓存: 304 跳过未修改内容
- entryChecksums: 每键内容哈希，用于 delta 计算

**推送** (index.ts:889-1146):
- Delta 上传: 只发送内容哈希不同的键
- 乐观锁: If-Match ETag 防止冲突覆盖
- 冲突解决:
  - 412 响应时刷新 serverChecksums
  - 重新计算 delta（排除匹配内容）
  - 最多重试 2 次

**关键限制** (index.ts:72-89):
```typescript
const MAX_FILE_SIZE_BYTES = 250_000      // 每文件上限
const MAX_PUT_BODY_BYTES = 200_000       // 单次 PUT 上限
const MAX_RETRIES = 3
const MAX_CONFLICT_RETRIES = 2
```

### 6.3 安全扫描

**源码**: index.ts:567-673, secretScanner.ts

上传前使用 gitleaks 规则扫描敏感信息：
- 检测到密钥的文件被跳过
- 记录到 skippedSecrets 数组
- 记录事件: `tengu_team_mem_secret_skipped`

## 7. 上下文窗口溢出处理策略

### 7.1 分层处理

```
Context窗口溢出处理链:

1. Microcompact (每轮)
   └─ 清理旧工具结果，节省 ~1-5K tokens

2. Session Memory Compaction (自动)
   └─ 使用会话记忆替代API摘要，节省 ~20-40K tokens

3. Legacy Compact (自动/手动)
   └─ Forked agent 生成摘要，保留最近N条消息

4. Reactive Compact (API 413)
   └─ 捕获 prompt_too_long 错误，紧急压缩

5. Prompt-Too-Long Retry (compact.ts:243-291)
   └─ truncateHeadForPTLRetry: 删除最旧的 API-round 组
```

### 7.2 断路器机制

**源码**: autoCompact.ts:67-70, 260-265

```typescript
const MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3

// Circuit breaker: stop retrying after N consecutive failures
if (tracking?.consecutiveFailures >= MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES) {
  return { wasCompacted: false }
}
```

防止不可恢复的上下文压力导致的无限重试浪费。

### 7.3 上下文窗口追踪

**Token 计数函数**:
- `tokenCountWithEstimation`: 精确计数（来自 API）+ 估算
- `roughTokenCountEstimation`: 本地粗略估算
- `estimateMessageTokens`: 微压缩专用估计

**警告状态计算** (autoCompact.ts:93-145):
```typescript
return {
  percentLeft,                    // 剩余百分比
  isAboveWarningThreshold,        // ≥ -20K buffer
  isAboveErrorThreshold,          // ≥ -20K buffer
  isAboveAutoCompactThreshold,    // ≥ -13K buffer
  isAtBlockingLimit,              // ≥ -3K buffer (手动/紧急)
}
```

## 8. 记忆持久化机制

### 8.1 文件结构

```
~/.claude/projects/<sanitized-git-root>/memory/
├── MEMORY.md              # 索引文件 (200行/25KB上限)
├── user_role.md           # 用户记忆
├── feedback_testing.md    # 反馈记忆
├── project_release.md     # 项目记忆
├── reference_dashboard.md # 参考记忆
└── team/                  # 团队记忆目录
    └── ...
```

### 8.2 Frontmatter 格式

**源码**: memoryTypes.ts:261-271

```markdown
---
name: {{memory name}}
description: {{one-line description}}
type: {{user | feedback | project | reference}}
---

{{memory content}}
```

**反馈/项目记忆结构建议**:
```
规则/事实
**Why:** 原因（过去的事故或强烈偏好）
**How to apply:** 何时/何处应用
```

### 8.3 索引截断

**源码**: memdir.ts:57-103

```typescript
const MAX_ENTRYPOINT_LINES = 200
const MAX_ENTRYPOINT_BYTES = 25_000

function truncateEntrypointContent(raw: string): EntrypointTruncation {
  const wasLineTruncated = lineCount > MAX_ENTRYPOINT_LINES
  const wasByteTruncated = byteCount > MAX_ENTRYPOINT_BYTES
  // ... 截断并添加警告
}
```

## 9. 自动压缩与上下文窗口管理

### 9.1 缓存共享优化

**源码**: compact.ts:435-438, 1179-1231

Forked agent 路径重用主对话的 prompt 缓存：
```typescript
const promptCacheSharingEnabled = getFeatureValue_CACHED_MAY_BE_STALE(
  'tengu_compact_cache_prefix', true
)

// Forked agent 使用相同的系统提示词、工具、模型
// 确保缓存键匹配，实现高缓存命中率
```

**优势**:
- 减少缓存创建 token（实验: false 路径成本 0.76% fleet cache_creation）
- 提高压缩速度
- 降低 API 成本

### 9.2 压缩后附件重建

**源码**: compact.ts:532-586

压缩后重建关键上下文附件：
1. **文件附件**: 最多5个最近访问的文件，总共 ≤50K tokens
2. **技能附件**: 已调用的技能，每个 ≤5K tokens
3. **代理附件**: 后台运行的代理状态
4. **计划附件**: 当前计划文件
5. **Delta 附件**: 工具、代理、MCP 指令变化

```typescript
const POST_COMPACT_TOKEN_BUDGET = 50_000
const POST_COMPACT_MAX_TOKENS_PER_FILE = 5_000
const POST_COMPACT_MAX_TOKENS_PER_SKILL = 5_000
```

### 9.3 Prompt Too Long 重试

**源码**: compact.ts:450-491

当压缩请求本身触发 prompt_too_long 时：
```typescript
for (;;) {
  summaryResponse = await streamCompactSummary(...)
  if (!summary?.startsWith(PROMPT_TOO_LONG_ERROR_MESSAGE)) break
  
  // 截断最旧的 API-round 组
  const truncated = truncateHeadForPTLRetry(messagesToSummarize, summaryResponse)
  if (!truncated) {
    throw new Error(ERROR_MESSAGE_PROMPT_TOO_LONG)
  }
  messagesToSummarize = truncated
  retryCacheSafeParams = {
    ...retryCacheSafeParams,
    forkContextMessages: truncated,
  }
}
```

## 10. Harness Engineering 评价

### 10.1 优秀设计

1. **分层记忆架构**:
   - 短期/长期记忆明确分工
   - 会话记忆作为压缩的高效替代
   - 团队记忆支持协作场景

2. **增量更新策略**:
   - Token 计数而非消息数触发
   - 工具调用间隔减少不必要的提取
   - 自然对话休息点检测

3. **缓存优化**:
   - Forked agent 共享主缓存
   - ETag 条件请求避免重复传输
   - Delta 上传减少带宽

4. **安全考虑**:
   - 密钥扫描防止泄露
   - 路径验证防止目录遍历
   - 私有/团队范围分离

### 10.2 潜在改进

1. **记忆陈旧化**:
   - 虽然有验证提醒，但缺少自动过期机制
   - 项目记忆变化快，需要主动刷新策略

2. **压缩质量**:
   - 完全依赖模型质量
   - 缺少结构化数据提取
   - Code snippets 可能丢失细节

3. **同步冲突**:
   - 本地优先策略可能导致协作冲突
   - 缺少合并策略，只是简单覆盖

4. **性能**:
   - 大项目记忆扫描可能较慢
   - 缺少增量索引更新

### 10.3 可靠性

1. **断路器**: 防止无限重试浪费
2. **重试机制**: 网络错误自动重试
3. **降级策略**: 多级压缩兜底
4. **错误处理**: 优雅失败，记录诊断信息

## 11. 关键代码位置索引

| 功能 | 文件 | 关键行 |
|------|------|--------|
| Session Memory 触发 | sessionMemory.ts | 134-181 |
| Session Memory 模板 | prompts.ts | 11-41 |
| 自动压缩阈值 | autoCompact.ts | 72-91, 160-239 |
| 微压缩工具列表 | microCompact.ts | 41-50 |
| 时间触发微压缩 | microCompact.ts | 422-530 |
| 全量压缩流程 | compact.ts | 387-763 |
| 会话记忆压缩 | sessionMemoryCompact.ts | 324-630 |
| 记忆提取 | extractMemories.ts | 296-587 |
| 记忆类型 | memoryTypes.ts | 14-271 |
| 团队同步推送 | teamMemorySync/index.ts | 889-1146 |
| 团队同步拉取 | teamMemorySync/index.ts | 770-867 |
| 索引截断 | memdir.ts | 57-103 |
| PTL 重试 | compact.ts | 243-291 |

## 12. 记忆对 Agent 推理质量的影响

### 12.1 正面影响

1. **上下文连续性**: 压缩后的摘要保持任务上下文
2. **用户偏好记忆**: 反馈记忆避免重复错误
3. **项目知识**: 项目记忆提供决策背景
4. **外部系统**: 参考记忆链接关键资源

### 12.2 潜在问题

1. **信息损失**: 压缩摘要丢失细节
2. **幻觉风险**: 模型可能捏造压缩时未看到的信息
3. **陈旧记忆**: 未验证的记忆可能误导
4. **记忆污染**: 错误记忆传播到后续会话

### 12.3 缓解措施

1. **转录本引用**: 提供完整上下文访问路径
2. **验证提醒**: 要求验证记忆准确性
3. **结构化记忆**: Frontmatter 提供元数据
4. **显式用户指令**: 用户可覆盖默认行为
