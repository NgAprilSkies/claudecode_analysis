# 视角 D: 记忆系统 (Memory Systems)

## D.1 记忆系统层次结构

Claude Code 实现了多层次记忆系统，从短期对话上下文到长期持久化存储：

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Claude Code 记忆系统层次结构                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  L1: 工作记忆 (Working Memory) - 秒级                               │
│      ├─ mutableMessages: Message[] (当前对话消息数组)               │
│      ├─ FileStateCache: LRU 缓存 (已读取文件内容)                   │
│      └─ 位置：src/QueryEngine.ts, src/utils/fileStateCache.ts       │
│                                                                     │
│  L2: 会话记忆 (Session Memory) - 小时级                             │
│      ├─ transcript.jsonl: 会话转录 (持久化对话历史)                 │
│      ├─ history.jsonl: 全局命令历史 (跨会话)                        │
│      └─ 位置：src/utils/sessionStorage.ts, src/history.ts           │
│                                                                     │
│  L3: 项目记忆 (Project Memory) - 月级                               │
│      ├─ CLAUDE.md: 项目级指令 (自动发现)                            │
│      ├─ .claude/ 目录：配置和技能                                   │
│      └─ 位置：src/utils/claudemd.ts                                 │
│                                                                     │
│  L4: 用户记忆 (User Memory) - 长期                                   │
│      ├─ MEMORY.md: 用户偏好和长期记忆                               │
│      ├─ settings.json: 全局配置                                     │
│      └─ 位置：~/.claude/ 目录                                       │
│                                                                     │
│  L5: 上下文管理系统 (Context Management)                            │
│      ├─ Snip Compact: 轻量级消息修剪                                │
│      ├─ Micro Compact: 删除重复工具对                               │
│      ├─ Auto Compact: 主动压缩 (90% 阈值)                            │
│      ├─ Context Collapse: 分级折叠压缩                              │
│      └─ Reactive Compact: API 413 错误后恢复                         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## D.2 记忆系统数据流图

```svg
<svg viewBox="0 0 1400 900" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <marker id="memArrow" markerWidth="12" markerHeight="8" refX="10" refY="4" orient="auto">
      <polygon points="0 0, 12 4, 0 8" fill="#00796B"/>
    </marker>
    <linearGradient id="gradWorking" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#E0F2F1;stop-opacity:1"/>
      <stop offset="100%" style="stop-color:#4DB6AC;stop-opacity:1"/>
    </linearGradient>
    <linearGradient id="gradSession" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#FFF8E1;stop-opacity:1"/>
      <stop offset="100%" style="stop-color:#FFCA28;stop-opacity:1"/>
    </linearGradient>
    <linearGradient id="gradProject" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#E8F5E9;stop-opacity:1"/>
      <stop offset="100%" style="stop-color:#81C784;stop-opacity:1"/>
    </linearGradient>
    <linearGradient id="gradUser" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#E3F2FD;stop-opacity:1"/>
      <stop offset="100%" style="stop-color:#64B5F6;stop-opacity:1"/>
    </linearGradient>
    <linearGradient id="gradCompact" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#FCE4EC;stop-opacity:1"/>
      <stop offset="100%" style="stop-color:#F06292;stop-opacity:1"/>
    </linearGradient>
  </defs>

  <!-- Title -->
  <text x="700" y="45" text-anchor="middle" font-size="24" font-weight="bold" fill="#333">
    记忆系统架构与上下文管理流程
  </text>
  <text x="700" y="75" text-anchor="middle" font-size="14" fill="#666">
    Memory Hierarchy &amp; Context Management Flow
  </text>

  <!-- LAYER 1: Working Memory -->
  <g transform="translate(30, 100)">
    <rect x="0" y="0" width="420" height="140" rx="10" fill="url(#gradWorking)" stroke="#00796B" stroke-width="2"/>
    <text x="210" y="35" text-anchor="middle" font-size="18" font-weight="bold" fill="#004D40">L1: 工作记忆 (Working Memory)</text>

    <!-- mutableMessages -->
    <rect x="20" y="50" width="180" height="75" rx="6" fill="white" stroke="#00796B" stroke-width="1.5"/>
    <text x="110" y="70" text-anchor="middle" font-size="13" font-weight="bold" fill="#004D40">mutableMessages</text>
    <text x="110" y="90" text-anchor="middle" font-size="10" fill="#00796B">Message[] 数组</text>
    <text x="110" y="107" text-anchor="middle" font-size="9" fill="#00897B">• 当前对话状态</text>
    <text x="110" y="120" text-anchor="middle" font-size="9" fill="#00897B">• 每转更新</text>

    <!-- FileStateCache -->
    <rect x="220" y="50" width="180" height="75" rx="6" fill="white" stroke="#00796B" stroke-width="1.5"/>
    <text x="310" y="70" text-anchor="middle" font-size="13" font-weight="bold" fill="#004D40">FileStateCache</text>
    <text x="310" y="90" text-anchor="middle" font-size="10" fill="#00796B">LRU Cache</text>
    <text x="310" y="107" text-anchor="middle" font-size="9" fill="#00897B">• 已读取文件缓存</text>
    <text x="310" y="120" text-anchor="middle" font-size="9" fill="#00897B">• 子代理共享</text>

    <!-- Arrow to next layer -->
    <path d="M 210 140 L 210 165" fill="none" stroke="#00796B" stroke-width="2" marker-end="url(#memArrow)"/>
  </g>

  <!-- LAYER 2: Session Memory -->
  <g transform="translate(30, 270)">
    <rect x="0" y="0" width="420" height="140" rx="10" fill="url(#gradSession)" stroke="#FFA000" stroke-width="2"/>
    <text x="210" y="35" text-anchor="middle" font-size="18" font-weight="bold" fill="#FF6F00">L2: 会话记忆 (Session Memory)</text>

    <!-- Transcript -->
    <rect x="20" y="50" width="180" height="75" rx="6" fill="white" stroke="#FFA000" stroke-width="1.5"/>
    <text x="110" y="70" text-anchor="middle" font-size="13" font-weight="bold" fill="#FF6F00">transcript.jsonl</text>
    <text x="110" y="90" text-anchor="middle" font-size="10" fill="#FFA000">会话转录</text>
    <text x="110" y="107" text-anchor="middle" font-size="9" fill="#FFA000">• --resume 支持</text>
    <text x="110" y="120" text-anchor="middle" font-size="9" fill="#FFA000">• 异步刷新</text>

    <!-- History -->
    <rect x="220" y="50" width="180" height="75" rx="6" fill="white" stroke="#FFA000" stroke-width="1.5"/>
    <text x="310" y="70" text-anchor="middle" font-size="13" font-weight="bold" fill="#FF6F00">history.jsonl</text>
    <text x="310" y="90" text-anchor="middle" font-size="10" fill="#FFA000">全局历史</text>
    <text x="310" y="107" text-anchor="middle" font-size="9" fill="#FFA000">• 跨会话共享</text>
    <text x="310" y="120" text-anchor="middle" font-size="9" fill="#FFA000">• 项目级过滤</text>

    <!-- Arrow -->
    <path d="M 210 410 L 210 435" fill="none" stroke="#FFA000" stroke-width="2" marker-end="url(#memArrow)"/>
  </g>

  <!-- LAYER 3: Project Memory -->
  <g transform="translate(30, 440)">
    <rect x="0" y="0" width="420" height="140" rx="10" fill="url(#gradProject)" stroke="#388E3C" stroke-width="2"/>
    <text x="210" y="35" text-anchor="middle" font-size="18" font-weight="bold" fill="#1B5E20">L3: 项目记忆 (Project Memory)</text>

    <!-- CLAUDE.md -->
    <rect x="20" y="50" width="180" height="75" rx="6" fill="white" stroke="#388E3C" stroke-width="1.5"/>
    <text x="110" y="70" text-anchor="middle" font-size="13" font-weight="bold" fill="#1B5E20">CLAUDE.md</text>
    <text x="110" y="90" text-anchor="middle" font-size="10" fill="#388E3C">项目级指令</text>
    <text x="110" y="107" text-anchor="middle" font-size="9" fill="#388E3C">• 自动发现</text>
    <text x="110" y="120" text-anchor="middle" font-size="9" fill="#388E3C">• 系统提示注入</text>

    <!-- .claude/ dir -->
    <rect x="220" y="50" width="180" height="75" rx="6" fill="white" stroke="#388E3C" stroke-width="1.5"/>
    <text x="310" y="70" text-anchor="middle" font-size="13" font-weight="bold" fill="#1B5E20">.claude/</text>
    <text x="310" y="90" text-anchor="middle" font-size="10" fill="#388E3C">配置目录</text>
    <text x="310" y="107" text-anchor="middle" font-size="9" fill="#388E3C">• 技能文件</text>
    <text x="310" y="120" text-anchor="middle" font-size="9" fill="#388E3C">• 插件配置</text>

    <!-- Arrow -->
    <path d="M 210 580 L 210 605" fill="none" stroke="#388E3C" stroke-width="2" marker-end="url(#memArrow)"/>
  </g>

  <!-- LAYER 4: User Memory -->
  <g transform="translate(30, 610)">
    <rect x="0" y="0" width="420" height="140" rx="10" fill="url(#gradUser)" stroke="#1976D2" stroke-width="2"/>
    <text x="210" y="35" text-anchor="middle" font-size="18" font-weight="bold" fill="#0D47A1">L4: 用户记忆 (User Memory)</text>

    <!-- MEMORY.md -->
    <rect x="20" y="50" width="180" height="75" rx="6" fill="white" stroke="#1976D2" stroke-width="1.5"/>
    <text x="110" y="70" text-anchor="middle" font-size="13" font-weight="bold" fill="#0D47A1">MEMORY.md</text>
    <text x="110" y="90" text-anchor="middle" font-size="10" fill="#1976D2">长期记忆</text>
    <text x="110" y="107" text-anchor="middle" font-size="9" fill="#1976D2">• 用户偏好</text>
    <text x="110" y="120" text-anchor="middle" font-size="9" fill="#1976D2">• 历史决策</text>

    <!-- settings.json -->
    <rect x="220" y="50" width="180" height="75" rx="6" fill="white" stroke="#1976D2" stroke-width="1.5"/>
    <text x="310" y="70" text-anchor="middle" font-size="13" font-weight="bold" fill="#0D47A1">settings.json</text>
    <text x="310" y="90" text-anchor="middle" font-size="10" fill="#1976D2">全局配置</text>
    <text x="310" y="107" text-anchor="middle" font-size="9" fill="#1976D2">• 权限规则</text>
    <text x="310" y="120" text-anchor="middle" font-size="9" fill="#1976D2">• 主题设置</text>
  </g>

  <!-- RIGHT SIDE: Context Management -->
  <g transform="translate(500, 100)">
    <rect x="0" y="0" width="870" height="650" rx="10" fill="none" stroke="#C2185B" stroke-width="2" stroke-dasharray="10,5"/>
    <text x="435" y="35" text-anchor="middle" font-size="18" font-weight="bold" fill="#C2185B">上下文管理系统 (Context Management)</text>

    <!-- Compact flow -->
    <g transform="translate(30, 50)">
      <!-- Snip -->
      <rect x="0" y="0" width="250" height="70" rx="8" fill="url(#gradCompact)" stroke="#D81B60" stroke-width="1.5"/>
      <text x="125" y="30" text-anchor="middle" font-size="14" font-weight="bold" fill="#880E4F">Snip Compact</text>
      <text x="125" y="50" text-anchor="middle" font-size="10" fill="#AD1457">轻量级消息修剪</text>
      <text x="125" y="65" text-anchor="middle" font-size="9" fill="#C2185B">feature: HISTORY_SNIP</text>

      <!-- Micro -->
      <rect x="280" y="0" width="250" height="70" rx="8" fill="url(#gradCompact)" stroke="#D81B60" stroke-width="1.5"/>
      <text x="415" y="30" text-anchor="middle" font-size="14" font-weight="bold" fill="#880E4F">Micro Compact</text>
      <text x="415" y="50" text-anchor="middle" font-size="10" fill="#AD1457">删除重复工具对</text>
      <text x="415" y="65" text-anchor="middle" font-size="9" fill="#C2185B">cache editing</text>

      <!-- Auto -->
      <rect x="560" y="0" width="250" height="70" rx="8" fill="url(#gradCompact)" stroke="#D81B60" stroke-width="1.5"/>
      <text x="690" y="30" text-anchor="middle" font-size="14" font-weight="bold" fill="#880E4F">Auto Compact</text>
      <text x="690" y="50" text-anchor="middle" font-size="10" fill="#AD1457">主动压缩 (90%)</text>
      <text x="690" y="65" text-anchor="middle" font-size="9" fill="#C2185B">buffer: 13k tokens</text>

      <!-- Collapse -->
      <rect x="0" y="90" width="250" height="70" rx="8" fill="#F8BBD0" stroke="#EC407A" stroke-width="1.5"/>
      <text x="125" y="120" text-anchor="middle" font-size="14" font-weight="bold" fill="#880E4F">Context Collapse</text>
      <text x="125" y="140" text-anchor="middle" font-size="10" fill="#AD1457">分级折叠 (90%/95%)</text>
      <text x="125" y="155" text-anchor="middle" font-size="9" fill="#C2185B">feature: CONTEXT_COLLAPSE</text>

      <!-- Reactive -->
      <rect x="280" y="90" width="250" height="70" rx="8" fill="#FCE4EC" stroke="#F48FB1" stroke-width="1.5" stroke-dasharray="5,3"/>
      <text x="415" y="120" text-anchor="middle" font-size="14" font-weight="bold" fill="#880E4F">Reactive Compact</text>
      <text x="415" y="140" text-anchor="middle" font-size="10" fill="#AD1457">413 错误恢复</text>
      <text x="415" y="155" text-anchor="middle" font-size="9" fill="#C2185B">fallback path</text>

      <!-- Flow arrows -->
      <path d="M 125 70 L 125 85" fill="none" stroke="#D81B60" stroke-width="1.5" marker-end="url(#memArrow)"/>
      <path d="M 415 70 L 415 85" fill="none" stroke="#D81B60" stroke-width="1.5" marker-end="url(#memArrow)"/>
      <path d="M 690 70 L 690 125 L 420 125" fill="none" stroke="#D81B60" stroke-width="1.5" marker-end="url(#memArrow)"/>
    </g>

    <!-- Token thresholds -->
    <g transform="translate(30, 250)">
      <rect x="0" y="0" width="810" height="140" rx="8" fill="#FFF9C4" stroke="#FBC02D" stroke-width="1.5"/>
      <text x="405" y="28" text-anchor="middle" font-size="14" font-weight="bold" fill="#F57F17">Token 阈值层次 (Token Thresholds)</text>

      <!-- Threshold bars -->
      <g transform="translate(30, 45)">
        <!-- Context Window -->
        <rect x="0" y="0" width="750" height="25" rx="3" fill="#E0E0E0" stroke="#9E9E9E" stroke-width="1"/>
        <text x="375" y="17" text-anchor="middle" font-size="10" fill="#424242">Context Window (200k tokens)</text>

        <!-- Blocking Limit -->
        <rect x="0" y="30" width="712" height="20" rx="2" fill="#EF9A9A" stroke="#C62828" stroke-width="1"/>
        <text x="356" y="15" text-anchor="middle" font-size="9" fill="#B71C1C">Blocking Limit (95% = 190k)</text>

        <!-- Auto Compact -->
        <rect x="0" y="55" width="675" height="20" rx="2" fill="#A5D6A7" stroke="#388E3C" stroke-width="1"/>
        <text x="337" y="15" text-anchor="middle" font-size="9" fill="#1B5E20">Auto Compact (90% = 180k)</text>

        <!-- Warning -->
        <rect x="0" y="80" width="700" height="20" rx="2" fill="#FFE082" stroke="#F9A825" stroke-width="1"/>
        <text x="350" y="15" text-anchor="middle" font-size="9" fill="#B71C1C">Warning (buffer: 20k tokens)</text>

        <!-- Scale labels -->
        <text x="0" y="115" font-size="8" fill="#616161">0</text>
        <text x="375" y="115" font-size="8" fill="#616161" text-anchor="middle">100k</text>
        <text x="750" y="115" font-size="8" fill="#616161" text-anchor="end">200k</text>
      </g>
    </g>

    <!-- Memory prefetch -->
    <g transform="translate(30, 410)">
      <rect x="0" y="0" width="810" height="80" rx="8" fill="#E1F5FE" stroke="#0288D1" stroke-width="1.5"/>
      <text x="405" y="28" text-anchor="middle" font-size="14" font-weight="bold" fill="#01579B">记忆预取 (Memory Prefetch)</text>

      <rect x="30" y="40" width="220" height="30" rx="4" fill="white" stroke="#0288D1" stroke-width="1"/>
      <text x="140" y="60" text-anchor="middle" font-size="10" fill="#01579B">Relevant Memory Prefetch</text>

      <rect x="270" y="40" width="220" height="30" rx="4" fill="white" stroke="#0288D1" stroke-width="1"/>
      <text x="380" y="60" text-anchor="middle" font-size="10" fill="#01579B">Skill Discovery Prefetch</text>

      <rect x="510" y="40" width="270" height="30" rx="4" fill="white" stroke="#0288D1" stroke-width="1"/>
      <text x="645" y="60" text-anchor="middle" font-size="10" fill="#01579B">Nested CLAUDE.md Injection</text>
    </g>

    <!-- Code references -->
    <text x="30" y="520" font-size="10" fill="#880E4F" font-family="monospace">
      src/services/compact/autoCompact.ts | src/history.ts | src/utils/sessionStorage.ts
    </text>
  </g>

  <!-- Cross-layer arrows -->
  <path d="M 450 170 L 495 170" fill="none" stroke="#00796B" stroke-width="2" marker-end="url(#memArrow)"/>
  <path d="M 450 340 L 495 340" fill="none" stroke="#FFA000" stroke-width="2" marker-end="url(#memArrow)"/>
  <path d="M 450 510 L 495 510" fill="none" stroke="#388E3C" stroke-width="2" marker-end="url(#memArrow)"/>
  <path d="M 450 680 L 495 680" fill="none" stroke="#1976D2" stroke-width="2" marker-end="url(#memArrow)"/>
</svg>
```

---

## D.3 上下文修剪策略

### 多层次修剪机制

Claude Code 实现了 5 层上下文修剪策略，按触发顺序排列：

| 层级 | 名称 | 触发条件 | 修剪策略 | 文件 |
|------|------|----------|----------|------|
| L1 | Snip | 每次迭代 | 移除旧消息但保留语义边界 | snipCompact.ts |
| L2 | Micro | 缓存编辑 | 删除重复 tool_use/tool_result 对 | microCompact.ts |
| L3 | Auto | 90% context window | LLM 总结对话历史 | autoCompact.ts |
| L4 | Collapse | 90% commit / 95% spawn | 分级折叠消息 | contextCollapse/ |
| L5 | Reactive | API 413 错误 | 紧急压缩恢复 | reactiveCompact.ts |

### 修剪代码位置

```typescript
// query.ts:400-548 - 每次迭代的上下文管理流程

// L1: Snip (400-410)
if (feature('HISTORY_SNIP')) {
  const snipResult = snipModule!.snipCompactIfNeeded(messagesForQuery)
  messagesForQuery = snipResult.messages
  snipTokensFreed = snipResult.tokensFreed
}

// L2: Micro (413-426)
const microcompactResult = await deps.microcompact(
  messagesForQuery,
  toolUseContext,
  querySource,
)
messagesForQuery = microcompactResult.messages

// L3: Auto (453-543)
const { compactionResult, consecutiveFailures } = await deps.autocompact(
  messagesForQuery,
  toolUseContext,
  cacheSafeParams,
)

// L4: Collapse (440-447)
if (feature('CONTEXT_COLLAPSE')) {
  const collapseResult = await contextCollapse.applyCollapsesIfNeeded(
    messagesForQuery,
    toolUseContext,
    querySource,
  )
}
```

---

## D.4 Harness Engineering 设计决策评价

### 可扩展性 (Scalability) - 8/10

**优点**:
- **分层设计**: 5 层策略可独立启用/禁用
- **Feature flags**: 每层都有独立的 feature flag
- **模块化**: 每层实现在独立文件中

**缺点**:
- **层间耦合**: 多层可能同时触发导致行为难预测
- **状态追踪复杂**: `autoCompactTracking` 携带跨迭代状态

**代码证据**:
```typescript
// autoCompact.ts:51-60 - 状态追踪
export type AutoCompactTrackingState = {
  compacted: boolean
  turnCounter: number
  turnId: string  // 唯一 ID per turn
  consecutiveFailures?: number  // 电路断路器
}
```

---

### 安全边界 (Safety Boundary) - 8/10

**优点**:
- **电路断路器**: `MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3`
- **会话持久化**: `recordTranscript()` 异步但有序
- **恢复路径**: Reactive Compact 作为最后防线

**缺点**:
- **数据丢失风险**: 压缩后原始消息不可恢复
- **并发写入**: history.jsonl 需要文件锁

**代码证据**:
```typescript
// history.ts:297-314 - 文件锁保护
release = await lock(historyPath, {
  stale: 10000,
  retries: {
    retries: 3,
    minTimeout: 50,
  },
})
```

---

### 可观察性 (Observability) - 7/10

**优点**:
- **分析事件**: `logEvent('tengu_auto_compact_succeeded', {...})`
- **失败追踪**: `consecutiveFailures` 记录压缩失败
- **Token 统计**: 输入/输出/缓存命中详细追踪

**缺点**:
- **调试困难**: 难以重现特定压缩决策的上下文
- **日志分散**: 各层日志格式不统一

---

### 性能损耗 (Performance Overhead) - 7/10

**优点**:
- **预判式压缩**: AutoCompact 在达到硬限制前压缩
- **缓存感知**: MicroCompact 利用 API 缓存删除字段

**缺点**:
- **每转开销**: 5 层检查每次迭代都执行
- **压缩本身消耗**: 压缩调用 LLM 消耗 token 和时间

**代码证据**:
```typescript
// autoCompact.ts:229-232 - 日志记录开销
logForDebugging(
  `autocompact: tokens=${tokenCount} threshold=${threshold} effectiveWindow=${effectiveWindow}`,
)
```

---

## D.5 最小化实现 (MRE) - Python

```python
"""
Memory Systems - Minimal Reference Implementation
视角 D: 记忆系统最小化实现 (约 95 行)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from collections import OrderedDict
import json
import hashlib


@dataclass
class Message:
    """消息类型"""
    type: str  # 'user', 'assistant', 'system'
    content: str
    uuid: str = field(default_factory=lambda: hashlib.uuid4().hex[:8])


class FileStateCache:
    """
    文件状态 LRU 缓存
    对应：src/utils/fileStateCache.ts
    """
    def __init__(self, max_size: int = 100):
        self.cache = OrderedDict()
        self.max_size = max_size

    def get(self, file_path: str) -> Optional[str]:
        if file_path in self.cache:
            # LRU: 移到末尾 (最近使用)
            self.cache.move_to_end(file_path)
            return self.cache[file_path]
        return None

    def set(self, file_path: str, content: str):
        if file_path in self.cache:
            self.cache.move_to_end(file_path)
        self.cache[file_path] = content
        # 剪枝：如果超出最大大小
        while len(self.cache) > self.max_size:
            self.cache.popitem(last=False)

    def clone(self) -> 'FileStateCache':
        """克隆缓存 (用于子代理)"""
        new_cache = FileStateCache(self.max_size)
        new_cache.cache = OrderedDict(self.cache)
        return new_cache


class SessionStorage:
    """
    会话存储 (transcript.jsonl)
    对应：src/utils/sessionStorage.ts
    """
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.messages: List[Message] = []
        self.flush_pending = False

    def record_transcript(self, messages: List[Message]):
        """记录会话转录 (异步刷新)"""
        self.messages = messages.copy()
        self.flush_pending = True
        # 实际实现会异步写入磁盘

    def load_transcript(self) -> List[Message]:
        """加载会话转录 (用于 --resume)"""
        # 实际实现会从磁盘读取
        return self.messages


class ContextManager:
    """
    上下文管理器
    对应：src/services/compact/autoCompact.ts
    """

    def __init__(
        self,
        context_window: int = 200000,
        auto_compact_threshold: float = 0.90,
        buffer_tokens: int = 13000,
    ):
        self.context_window = context_window
        self.threshold = context_window * auto_compact_threshold
        self.buffer_tokens = buffer_tokens
        self.compaction_count = 0
        self.consecutive_failures = 0
        self.max_failures = 3  # 电路断路器

    def should_auto_compact(self, messages: List[Message]) -> bool:
        """
        检查是否需要自动压缩

        对应：autoCompact.ts:shouldAutoCompact()
        """
        # 电路断路器检查
        if self.consecutive_failures >= self.max_failures:
            print(f"[CircuitBreaker] {self.consecutive_failures} failures - skipping")
            return False

        token_count = self._count_tokens(messages)
        effective_threshold = self.threshold - self.buffer_tokens

        print(f"[Check] tokens={token_count} threshold={effective_threshold}")
        return token_count > effective_threshold

    async def auto_compact(
        self,
        messages: List[Message],
        turn_id: str,
    ) -> Dict[str, Any]:
        """
        执行自动压缩

        对应：autoCompact.ts:autoCompactIfNeeded()
        """
        if not self.should_auto_compact(messages):
            return {"compacted": False}

        try:
            # 模拟 LLM 压缩 (实际实现会调用 Claude API)
            summary = self._generate_summary(messages)

            # 构建压缩后消息
            compacted_messages = [
                Message(
                    type="system",
                    content=f"Conversation summary: {summary}",
                    uuid="compact-summary"
                ),
                # 保留最后几条消息
                *messages[-5:]
            ]

            self.compaction_count += 1
            self.consecutive_failures = 0  # 重置失败计数

            return {
                "compacted": True,
                "messages": compacted_messages,
                "summary": summary,
                "turn_id": turn_id,
            }

        except Exception as e:
            self.consecutive_failures += 1
            return {
                "compacted": False,
                "error": str(e),
                "consecutive_failures": self.consecutive_failures,
            }

    def _generate_summary(self, messages: List[Message]) -> str:
        """生成对话摘要 (简化实现)"""
        # 实际实现会调用 LLM
        return f"Summary of {len(messages)} messages"

    def _count_tokens(self, messages: List[Message]) -> int:
        """估算 token 数"""
        return sum(len(m.content) // 4 for m in messages)


class MemorySystem:
    """
    完整记忆系统
    整合：工作记忆 + 会话记忆 + 上下文管理
    """

    def __init__(self, session_id: str):
        # L1: 工作记忆
        self.mutable_messages: List[Message] = []
        self.file_cache = FileStateCache()

        # L2: 会话记忆
        self.session_storage = SessionStorage(session_id)

        # 上下文管理
        self.context_manager = ContextManager()

    async def process_turn(self, user_input: str) -> str:
        """
        处理一轮对话

        流程:
        1. 添加用户消息
        2. 检查是否需要压缩
        3. 生成响应 (模拟)
        4. 记录会话
        """
        # 添加用户消息
        self.mutable_messages.append(Message(type="user", content=user_input))

        # 检查压缩
        if self.context_manager.should_auto_compact(self.mutable_messages):
            result = await self.context_manager.auto_compact(
                self.mutable_messages,
                turn_id=f"turn-{len(self.mutable_messages)}"
            )
            if result["compacted"]:
                print(f"[Compact] {result['summary']}")
                self.mutable_messages = result["messages"]

        # 生成响应 (模拟)
        response = f"Response to: {user_input}"
        self.mutable_messages.append(Message(type="assistant", content=response))

        # 记录会话
        self.session_storage.record_transcript(self.mutable_messages)

        return response

    def get_state(self) -> Dict:
        """获取当前状态 (用于调试)"""
        return {
            "message_count": len(self.mutable_messages),
            "cache_size": len(self.file_cache.cache),
            "compaction_count": self.context_manager.compaction_count,
            "consecutive_failures": self.context_manager.consecutive_failures,
        }


# 使用示例
async def main():
    # 创建记忆系统
    memory = MemorySystem(session_id="test-session")

    # 模拟多轮对话
    for i in range(20):
        response = await memory.process_turn(f"Message {i}")
        print(f"Turn {i}: {response}")

        # 打印状态
        state = memory.get_state()
        print(f"状态：{state}")
```

---

## D.6 挑战性思考问题

### 问题 D: 记忆系统的一致性与恢复

**场景**: Claude Code 的记忆系统存在一个潜在的一致性问题：当自动压缩 (Auto Compact) 和会话持久化 (Session Storage) 同时进行时，如果压缩成功但持久化失败（如磁盘满、进程被杀），用户重启后会发现：

1. 会话从压缩前的状态恢复（因为 transcript.jsonl 未更新）
2. 但 `lastSummarizedMessageId` 已被重置
3. 导致后续压缩逻辑混乱

此外，多会话并发写入同一 `history.jsonl` 文件时，尽管有文件锁，但在某些边缘情况下仍可能出现数据竞争。

**挑战问题**:
> 如果你要重新设计 Claude Code 的记忆系统以保证强一致性和可靠恢复，你会选择以下哪种架构方案？
>
> **方案 A: 预写日志 (WAL - Write-Ahead Logging)**
> - 任何状态变更前先写 WAL
> - 恢复时重放 WAL 重建状态
> - 类似数据库的崩溃恢复机制
>
> **方案 B: 不可变事件溯源 (Event Sourcing)**
> - 所有记忆操作都作为不可变事件追加
> - 状态是事件的投影，可随时重建
> - 快照用于优化恢复速度
>
> **方案 C: 两阶段提交 (2PC) for 压缩**
> - 压缩分 prepare 和 commit 两阶段
> - 只有持久化成功后才更新内存状态
> - 回滚机制处理失败情况
>
> **具体要求**:
> 1. 选择一种方案并详细说明数据结构设计
> 2. 分析该方案的恢复流程（如何从崩溃中恢复？）
> 3. 如何保证多会话并发写入的一致性？
> 4. 评估你的方案对以下指标的影响：
>    - 写入延迟
>    - 恢复时间
>    - 存储空间开销
>
> **提示**: 参考数据库系统 (PostgreSQL WAL)、分布式系统 (Raft 日志)、或版本控制系统 (Git 对象存储) 的设计模式。

---

*视角 D 分析完成*
