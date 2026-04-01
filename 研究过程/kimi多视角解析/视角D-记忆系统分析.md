# 视角D：Claude Code 记忆系统深度分析

## 概述

Claude Code的记忆系统是一个多层次、多策略的复杂架构，旨在解决大型语言模型对话中的**上下文窗口限制**和**长期记忆保持**问题。该系统通过短期记忆（Session级别）和长期记忆（跨Session）的协同工作，实现了高效的记忆管理。

### 核心设计目标
1. **避免OOM（Out of Memory）**：通过多层次的上下文修剪和压缩机制
2. **保持对话连贯性**：通过边界标记和摘要保留关键信息
3. **跨Session记忆持久化**：通过文件系统存储用户和项目记忆
4. **高效检索**：通过LRU缓存和索引机制加速记忆访问

---

## 短期记忆机制分析（Session级别）

### 1. 消息存储架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Session Memory Stack                      │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: Pending Buffer (内存中，未持久化)                   │
│     └─ pendingEntries: LogEntry[]                          │
│                                                              │
│  Layer 2: Session History (JSONL文件)                        │
│     └─ ~/.claude/history.jsonl                             │
│                                                              │
│  Layer 3: Session Transcript (项目级JSONL)                   │
│     └─ ~/.claude/projects/<project>/sessions/<id>/...      │
└─────────────────────────────────────────────────────────────┘
```

**关键文件**：`src/history.ts`
- 使用**双缓冲机制**：pending buffer + 磁盘持久化
- 支持**增量写入**：通过 `immediateFlushHistory()` 实现
- 最大历史条目限制：`MAX_HISTORY_ITEMS = 100`

### 2. 文件状态缓存（FileStateCache）

**关键文件**：`src/utils/fileStateCache.ts`

```typescript
export class FileStateCache {
  private cache: LRUCache<string, FileState>
  // max: 100 entries
  // maxSize: 25MB (DEFAULT_MAX_CACHE_SIZE_BYTES)
}
```

**设计特点**：
- 使用 **LRU (Least Recently Used)** 策略
- **路径规范化**：处理相对/绝对路径、Windows/Linux路径分隔符
- **大小限制**：25MB默认上限，防止大文件导致OOM
- **支持部分视图标记**：`isPartialView` 用于跟踪注入内容

### 3. 上下文预算与工具结果存储

**关键文件**：`src/utils/toolResultStorage.ts`

```typescript
// 工具结果大小限制
const MAX_TOOL_RESULT_BYTES = 50 * 1024        // 50KB
const MAX_TOOL_RESULTS_PER_MESSAGE_CHARS = 150_000  // 150KB

// 内容替换状态跟踪
export type ContentReplacementState = {
  seenIds: Set<string>           // 已处理的结果ID
  replacements: Map<string, string>  // 替换内容映射
}
```

**大工具结果处理策略**：
1. **持久化到磁盘**：大结果写入 `~/.claude/projects/<project>/sessions/<id>/tool-results/`
2. **生成预览**：保留前2000字节预览
3. **预算强制执行**：`enforceToolResultBudget()` 确保每消息不超过150KB

---

## 长期记忆机制分析（跨Session）

### 1. 记忆类型系统

**关键文件**：`src/utils/memory/types.ts`

```typescript
export const MEMORY_TYPE_VALUES = [
  'User',     // 用户级记忆（跨所有项目）
  'Project',  // 项目级记忆
  'Local',    // 本地特定记忆
  'Managed',  // 托管记忆
  'AutoMem',  // 自动记忆
  'TeamMem',  // 团队记忆（feature gate控制）
] as const
```

### 2. 记忆目录结构（memdir）

**关键文件**：`src/memdir/memdir.ts`, `src/memdir/paths.ts`

```
~/.claude/
├── projects/
│   └── <sanitized-project-root>/
│       └── memory/                    # AutoMem目录
│           ├── MEMORY.md              # 记忆入口点（最多200行/25KB）
│           ├── user.md                # 用户记忆
│           ├── project.md             # 项目记忆
│           └── logs/                  # 每日日志
│               └── YYYY/MM/YYYY-MM-DD.md
├── memory/                            # 全局用户记忆
│   └── ...
└── ...
```

**MEMORY.md 截断策略**：
- 最大200行
- 最大25KB
- 优先截断尾部（保留头部重要信息）

### 3. 自动记忆提取（AutoMem）

**关键文件**：`src/services/extractMemories/extractMemories.ts`

**触发条件**：
1. 初始化阈值：`minimumMessageTokensToInit`（默认约100K tokens）
2. 更新阈值：`minimumTokensBetweenUpdate`（默认约50K tokens）
3. 工具调用阈值：`toolCallsBetweenUpdates`（默认约10次）

**工作流程**：
```
User Query → Check Thresholds → Fork Subagent → Extract Memories → Write to MEMORY.md
```

### 4. Session记忆（SessionMemory）

**关键文件**：`src/services/SessionMemory/sessionMemory.ts`

**特点**：
- 在后台fork子代理运行
- 使用 `runForkedAgent` 保持隔离性
- 更新 `~/.claude/projects/<project>/sessions/<id>/memory.md`

---

## 上下文构建与修剪分析

### 1. 上下文构建流程

**关键文件**：`src/context.ts`

```typescript
// System Context（系统级，缓存）
export const getSystemContext = memoize(async () => {
  const gitStatus = await getGitStatus()  // Git状态快照
  return { gitStatus }
})

// User Context（用户级，缓存）
export const getUserContext = memoize(async () => {
  const claudeMd = await getClaudeMds()   // CLAUDE.md文件
  return { claudeMd, currentDate }
})
```

**构建策略**：
- **Memoization缓存**：避免重复计算
- **Git状态快照**：会话开始时捕获，不随对话更新
- **CLAUDE.md加载**：支持目录遍历和过滤

### 2. 消息归一化（normalizeMessagesForAPI）

**关键文件**：`src/utils/messages.ts`

**处理步骤**：
1. **附件重新排序**：将附件上移到工具结果之前
2. **虚拟消息过滤**：移除仅用于UI显示的消息
3. **错误块剥离**：移除PDF/图像错误块
4. **工具引用过滤**：只保留可用工具的引用

### 3. 上下文压缩（Compact）

**关键文件**：`src/services/compact/compact.ts`, `src/services/compact/autoCompact.ts`

**压缩触发条件**：
```typescript
// 自动压缩阈值
const AUTOCOMPACT_BUFFER_TOKENS = 13_000
const getAutoCompactThreshold = (model: string) => {
  const effectiveWindow = getEffectiveContextWindowSize(model)
  return effectiveWindow - AUTOCOMPACT_BUFFER_TOKENS
}
```

**压缩流程**：
```
Pre-Compact Messages (N tokens)
        ↓
[Strip Images & Attachments]
        ↓
Fork Compaction Agent
        ↓
Generate Summary + Boundary Marker
        ↓
Post-Compact Messages (~50K tokens)
```

**边界标记（Compact Boundary）**：
```typescript
{
  type: 'system',
  subtype: 'compact_boundary',
  compactMetadata: {
    trigger: 'manual' | 'auto',
    preTokens: number,           // 压缩前token数
    messagesSummarized: number   // 被摘要的消息数
  }
}
```

### 4. 微压缩（Microcompact）

**关键文件**：`src/services/compact/microCompact.ts`

**两种策略**：

#### A. 时间触发微压缩（Time-based MC）
```typescript
// 默认配置
const DEFAULT_GAP_THRESHOLD_MINUTES = 60  // 1小时无活动
const DEFAULT_KEEP_RECENT = 10            // 保留最近10个工具结果
```

**触发条件**：距上次助手消息超过60分钟
**行为**：清除所有可压缩工具结果，仅保留最近N个

#### B. 缓存微压缩（Cached MC）
使用Anthropic API的缓存编辑功能：
```typescript
export type CacheEditsBlock = {
  type: 'cache_edits'
  edits: Array<{
    type: 'delete'
    target: { type: 'tool_result'; tool_use_id: string }
  }>
}
```

**优势**：
- 不修改本地消息内容
- 通过API层删除缓存中的工具结果
- 保持提示缓存命中率

---

## 记忆持久化分析

### 1. 会话存储（SessionStorage）

**关键文件**：`src/utils/sessionStorage.ts`

**存储结构**：
```
~/.claude/projects/<project>/sessions/<sessionId>/
├── transcript.jsonl          # 完整对话记录
├── memory.md                 # Session记忆
├── tool-results/             # 大工具结果
│   └── <tool-use-id>.json
└── attachments/              # 附件文件
```

**transcript.jsonl 格式**：
```jsonl
{"type": "user", "uuid": "...", "message": {...}, "timestamp": "..."}
{"type": "assistant", "uuid": "...", "message": {...}, "timestamp": "..."}
{"type": "system", "subtype": "compact_boundary", ...}
```

### 2. 会话恢复机制

**关键文件**：`src/utils/sessionStorage.ts`

**恢复流程**：
1. 读取 `transcript.jsonl` 尾部（最多16KB用于元数据）
2. 解析消息链（通过 `parentUuid` 重建链表）
3. 重建文件状态缓存
4. 恢复内容替换状态

**优化策略**：
- **惰性加载**：只加载消息索引，内容按需读取
- **增量读取**：使用 `readLinesReverse` 从尾部读取

### 3. 提示历史（Prompt History）

**关键文件**：`src/history.ts`

**特点**：
- 全局存储在 `~/.claude/history.jsonl`
- 按项目过滤
- 支持粘贴内容的哈希存储（大内容分离存储）

---

## Harness Engineering评价

### 1. 可扩展性设计

**评分：8.5/10**

**优点**：
- ✅ **分层架构**：短期/长期/持久化三层分离
- ✅ **策略模式**：不同的compact策略可插拔（Time-based/Cached/API Microcompact）
- ✅ **Feature Gate控制**：新功能通过 `feature()` 函数控制，便于灰度发布

**改进空间**：
- ⚠️ 部分模块存在循环依赖（如 `toolResultStorage.ts` 和 `messages.ts`）
- ⚠️ 缓存配置硬编码，建议外部化

### 2. 安全边界设计

**评分：9/10**

**安全措施**：
- ✅ **路径验证**：`validateMemoryPath` 防止路径遍历攻击
- ✅ **权限隔离**：Session文件使用 `0o600` 权限
- ✅ **记忆隔离**：`isAutoMemPath` 确保记忆写入限定目录
- ✅ **敏感信息扫描**：`teamMemSecretGuard.ts` 检测secrets

**安全设计**：
```typescript
// 路径验证
function validateMemoryPath(raw: string): string | undefined {
  if (!isAbsolute(normalized) || normalized.length < 3) return undefined
  if (normalized.includes('\0')) return undefined  // Null字节检查
  if (normalized.startsWith('\\\\')) return undefined  // UNC路径
}
```

### 3. 可观察性设计

**评分：9/10**

**监控维度**：
- ✅ **事件日志**：`logEvent('tengu_compact', {...})` 详细的压缩指标
- ✅ **调试日志**：`logForDebugging` 用于开发调试
- ✅ **Token统计**：每个API调用记录token使用情况
- ✅ **缓存命中率**：`promptCacheBreakDetection` 监控缓存性能

**关键指标**：
```typescript
logEvent('tengu_compact', {
  preCompactTokenCount,
  postCompactTokenCount,
  compactionCacheReadTokens,
  compactionCacheCreationTokens,
  willRetriggerNextTurn,  // 预测是否会再次触发压缩
})
```

### 4. 性能损耗分析

**评分：8/10**

**性能优化策略**：

| 策略 | 实现 | 效果 |
|------|------|------|
| **LRU缓存** | `fileStateCache.ts` | O(1)读写，自动淘汰 |
| **Memoization** | `getSystemContext`, `getUserContext` | 避免重复计算 |
| **增量写入** | `history.ts` pending buffer | 减少磁盘I/O |
| **懒加载** | `sessionStorage.ts` | 按需读取消息 |
| **批量处理** | `compact.ts` fork agent | 异步摘要生成 |

**潜在性能瓶颈**：
- ⚠️ **大文件读取**：`FileReadTool` 读取大文件时可能阻塞
- ⚠️ **Compaction延迟**：摘要生成需要额外的API调用（约1-3秒）

**内存使用优化**：
```typescript
// 工具结果预算限制
const MAX_TOOL_RESULTS_PER_MESSAGE_CHARS = 150_000

// 文件缓存大小限制
const DEFAULT_MAX_CACHE_SIZE_BYTES = 25 * 1024 * 1024  // 25MB

// 消息级预算强制执行
export async function enforceToolResultBudget(
  messages: Message[],
  state: ContentReplacementState
): Promise<{ messages: Message[]; newlyReplaced: ToolResultReplacementRecord[] }>
```

---

## 关键实现细节

### 1. 防止OOM的多层防御

```
Layer 1: FileStateCache Size Limit (25MB)
    ↓
Layer 2: Tool Result Budget (150KB per message)
    ↓
Layer 3: Microcompact (自动清除旧工具结果)
    ↓
Layer 4: AutoCompact (上下文压缩)
    ↓
Layer 5: Circuit Breaker (3次失败后停止重试)
```

### 2. 提示缓存保护

```typescript
// 关键设计：保持已见内容的稳定性
export type ContentReplacementState = {
  seenIds: Set<string>        // 一旦看到，永不改变
  replacements: Map<string, string>  // 替换内容缓存
}

// 分区策略
partitionByPriorDecision(candidates, state): {
  mustReapply: Candidate[]  // 已替换 → 必须重新应用相同内容
  frozen: Candidate[]       // 已见未替换 → 永不替换
  fresh: Candidate[]        // 新内容 → 可以替换
}
```

### 3. 会话隔离设计

```typescript
// Forked Agent隔离
export async function runForkedAgent({
  promptMessages,
  cacheSafeParams,      // 隔离的参数
  canUseTool,           // 自定义工具权限
  forkLabel,            // 标识fork用途
}: ForkedAgentOptions)

// Subagent Context创建
export function createSubagentContext(
  parent: ToolUseContext
): ToolUseContext {
  return {
    ...parent,
    readFileState: new FileStateCache(...),  // 新的缓存实例
    abortController: new AbortController(),   // 独立的取消信号
  }
}
```

---

## 互动挑战

**问题：如果是你，你会如何优化这里的上下文内存管理以防止OOM？**

请在阅读以上分析后思考以下方面：
1. 当前的内存预算分层是否足够？
2. 是否应该引入预测性压缩（在达到阈值前主动压缩）？
3. 如何平衡提示缓存命中率和内存使用？
4. 对于超大文件（如1GB日志文件）的处理策略应该如何设计？

---

## 参考文件

- `src/history.ts` - 提示历史管理
- `src/context.ts` - 上下文构建
- `src/utils/fileStateCache.ts` - 文件状态缓存
- `src/assistant/sessionHistory.ts` - 会话历史API
- `src/utils/toolResultStorage.ts` - 工具结果存储
- `src/services/compact/compact.ts` - 上下文压缩
- `src/services/compact/microCompact.ts` - 微压缩
- `src/services/compact/autoCompact.ts` - 自动压缩
- `src/memdir/memdir.ts` - 记忆目录管理
- `src/services/SessionMemory/sessionMemory.ts` - Session记忆
