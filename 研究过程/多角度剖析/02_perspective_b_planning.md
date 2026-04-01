# 视角 B: 任务规划 (Planning & Reasoning)

## B.1 核心规划引擎架构

### Query 循环：决策核心

Claude Code 的任务规划核心位于 `src/query.ts` 中的 `query()` 和 `queryLoop()` 函数。这是一个基于**转 (Turn)** 的循环系统，每转包含：

1. **上下文准备** (Context Preparation)
2. **LLM 调用** (Model Sampling)
3. **工具执行** (Tool Execution)
4. **后置评估** (Post-evaluation)

### 决策流程图

```svg
<svg viewBox="0 0 1400 1000" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <marker id="arrowB" markerWidth="12" markerHeight="8" refX="10" refY="4" orient="auto">
      <polygon points="0 0, 12 4, 0 8" fill="#2E5C8A"/>
    </marker>
    <linearGradient id="gradInit" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#E3F2FD"/>
      <stop offset="100%" style="stop-color:#90CAF9"/>
    </linearGradient>
    <linearGradient id="gradContext" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#E8F5E9"/>
      <stop offset="100%" style="stop-color:#A5D6A7"/>
    </linearGradient>
    <linearGradient id="gradModel" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#FFF3E0"/>
      <stop offset="100%" style="stop-color:#FFCC80"/>
    </linearGradient>
    <linearGradient id="gradTool" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#F3E5F5"/>
      <stop offset="100%" style="stop-color:#CE93D8"/>
    </linearGradient>
    <linearGradient id="gradEval" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#FFEBEE"/>
      <stop offset="100%" style="stop-color:#EF9A9A"/>
    </linearGradient>
  </defs>

  <!-- Background -->
  <rect width="1400" height="1000" fill="#fafafa"/>

  <!-- Title -->
  <text x="700" y="45" text-anchor="middle" font-size="26" font-weight="bold" fill="#1a1a1a">
    Claude Code 任务规划与决策路径 (Planning &amp; Decision Flow)
  </text>
  <text x="700" y="75" text-anchor="middle" font-size="14" fill="#666">
    基于 query.ts 的 Query Loop 架构分析
  </text>

  <!-- MAIN LOOP CONTAINER -->
  <rect x="30" y="100" width="1340" height="850" rx="15" fill="none" stroke="#333" stroke-width="3" stroke-dasharray="10,5"/>
  <text x="700" y="125" text-anchor="middle" font-size="16" font-weight="bold" fill="#333">queryLoop() - 主循环 (每次迭代 = 一转/Turn)</text>

  <!-- PHASE 1: Context Management -->
  <g transform="translate(50, 150)">
    <rect x="0" y="0" width="400" height="200" rx="10" fill="url(#gradContext)" stroke="#4CAF50" stroke-width="2"/>
    <text x="200" y="35" text-anchor="middle" font-size="18" font-weight="bold" fill="#2E7D32">阶段 1: 上下文管理</text>
    <text x="200" y="55" text-anchor="middle" font-size="12" fill="#4CAF50">(Context Management)</text>

    <!-- Sub-steps -->
    <rect x="20" y="70" width="360" height="35" rx="5" fill="white" stroke="#4CAF50" stroke-width="1.5"/>
    <text x="190" y="92" text-anchor="middle" font-size="12" fill="#333">1. Tool Result Budget (applyToolResultBudget)</text>

    <rect x="20" y="110" width="360" height="35" rx="5" fill="white" stroke="#4CAF50" stroke-width="1.5"/>
    <text x="190" y="132" text-anchor="middle" font-size="12" fill="#333">2. Snip Compact (feature: HISTORY_SNIP)</text>

    <rect x="20" y="150" width="360" height="35" rx="5" fill="white" stroke="#4CAF50" stroke-width="1.5"/>
    <text x="190" y="172" text-anchor="middle" font-size="12" fill="#333">3. Micro/Auto/Collapse Compact</text>

    <!-- Token thresholds -->
    <text x="200" y="225" text-anchor="middle" font-size="11" fill="#666">
      阈值：AUTOCOMPACT_BUFFER_TOKENS = 13,000
    </text>
  </g>

  <!-- PHASE 2: Model Call -->
  <g transform="translate(480, 150)">
    <rect x="0" y="0" width="400" height="200" rx="10" fill="url(#gradModel)" stroke="#FF9800" stroke-width="2"/>
    <text x="200" y="35" text-anchor="middle" font-size="18" font-weight="bold" fill="#E65100">阶段 2: LLM API 调用</text>
    <text x="200" y="55" text-anchor="middle" font-size="12" fill="#F57C00">(deps.callModel - Streaming)</text>

    <!-- Streaming loop -->
    <rect x="20" y="70" width="360" height="50" rx="5" fill="white" stroke="#FF9800" stroke-width="1.5"/>
    <text x="200" y="90" text-anchor="middle" font-size="12" fill="#333">流式响应处理:</text>
    <text x="200" y="108" text-anchor="middle" font-size="11" fill="#666">message_start → content_block → message_delta</text>

    <rect x="20" y="125" width="360" height="35" rx="5" fill="white" stroke="#FF9800" stroke-width="1.5"/>
    <text x="200" y="147" text-anchor="middle" font-size="12" fill="#333">模型选择 (getRuntimeMainLoopModel)</text>

    <rect x="20" y="165" width="360" height="25" rx="5" fill="#FFF8E1" stroke="#FFB74D" stroke-width="1"/>
    <text x="200" y="182" text-anchor="middle" font-size="10" fill="#E65100">Thinking Config + Token Budget</text>
  </g>

  <!-- PHASE 3: Tool Execution -->
  <g transform="translate(910, 150)">
    <rect x="0" y="0" width="440" height="200" rx="10" fill="url(#gradTool)" stroke="#9C27B0" stroke-width="2"/>
    <text x="220" y="35" text-anchor="middle" font-size="18" font-weight="bold" fill="#6A1B9A">阶段 3: 工具执行</text>
    <text x="220" y="55" text-anchor="middle" font-size="12" fill="#8E24AA">(StreamingToolExecutor / runTools)</text>

    <!-- Tool execution modes -->
    <rect x="20" y="70" width="190" height="45" rx="5" fill="white" stroke="#9C27B0" stroke-width="1.5"/>
    <text x="115" y="90" text-anchor="middle" font-size="12" fill="#333" font-weight="bold">流式模式</text>
    <text x="115" y="106" text-anchor="middle" font-size="10" fill="#666">(StreamingToolExecutor)</text>

    <rect x="230" y="70" width="190" height="45" rx="5" fill="white" stroke="#9C27B0" stroke-width="1.5"/>
    <text x="325" y="90" text-anchor="middle" font-size="12" fill="#333" font-weight="bold">传统模式</text>
    <text x="325" y="106" text-anchor="middle" font-size="10" fill="#666">(runTools serial/concurrent)</text>

    <!-- Concurrency control -->
    <rect x="20" y="125" width="400" height="35" rx="5" fill="#F3E5F5" stroke="#CE93D8" stroke-width="1"/>
    <text x="220" y="147" text-anchor="middle" font-size="12" fill="#333">
      <tspan>分区执行：partitionToolCalls() → 并发安全工具分组</tspan>
    </text>

    <rect x="20" y="165" width="400" height="25" rx="5" fill="#F3E5F5" stroke="#CE93D8" stroke-width="1"/>
    <text x="220" y="182" text-anchor="middle" font-size="10" fill="#6A1B9A">权限检查 → 执行 → 结果收集</text>
  </g>

  <!-- ARROWS between phases -->
  <line x1="450" y1="250" x2="475" y2="250" stroke="#333" stroke-width="2.5" marker-end="url(#arrowB)"/>
  <line x1="880" y1="250" x2="905" y2="250" stroke="#333" stroke-width="2.5" marker-end="url(#arrowB)"/>

  <!-- PHASE 4: Post-Evaluation -->
  <g transform="translate(50, 380)">
    <rect x="0" y="0" width="1300" height="280" rx="10" fill="url(#gradEval)" stroke="#C62828" stroke-width="2"/>
    <text x="650" y="35" text-anchor="middle" font-size="18" font-weight="bold" fill="#B71C1C">阶段 4: 后置评估与决策 (Post-Evaluation &amp; Decision)</text>

    <!-- Decision Tree -->
    <g transform="translate(50, 50)">
      <!-- Root: needsFollowUp -->
      <polygon points="600,0 700,40 600,80 500,40" fill="#FFCDD2" stroke="#C62828" stroke-width="2"/>
      <text x="600" y="35" text-anchor="middle" font-size="12" fill="#B71C1C" font-weight="bold">needsFollowUp?</text>
      <text x="600" y="52" text-anchor="middle" font-size="11" fill="#B71C1C">(tool_use blocks?)</text>

      <!-- NO branch -->
      <line x1="600" y1="80" x2="600" y2="120" stroke="#C62828" stroke-width="2"/>
      <text x="615" y="105" font-size="11" fill="#C62828" font-weight="bold">NO</text>

      <!-- Stop Hook Check -->
      <rect x="470" y="120" width="260" height="50" rx="8" fill="white" stroke="#C62828" stroke-width="2"/>
      <text x="600" y="145" text-anchor="middle" font-size="12" fill="#333" font-weight="bold">handleStopHooks()</text>
      <text x="600" y="162" text-anchor="middle" font-size="10" fill="#666">评估是否继续</text>

      <!-- Token Budget Check -->
      <line x1="600" y1="170" x2="600" y2="200" stroke="#C62828" stroke-width="2"/>
      <rect x="450" y="200" width="300" height="40" rx="5" fill="#FFF8E1" stroke="#FFA000" stroke-width="1.5"/>
      <text x="600" y="225" text-anchor="middle" font-size="11" fill="#333">Token Budget Check (feature: TOKEN_BUDGET)</text>

      <!-- Exit points -->
      <line x1="600" y1="240" x2="600" y2="270" stroke="#C62828" stroke-width="2"/>
      <rect x="500" y="270" width="200" height="35" rx="5" fill="#C8E6C9" stroke="#2E7D32" stroke-width="2"/>
      <text x="600" y="293" text-anchor="middle" font-size="12" fill="#2E7D32" font-weight="bold">return { reason: 'completed' }</text>

      <!-- YES branch -->
      <line x1="700" y1="40" x2="850" y2="40" stroke="#C62828" stroke-width="2"/>
      <text x="775" y="35" font-size="11" fill="#C62828" font-weight="bold">YES</text>
      <line x1="850" y1="40" x2="850" y2="200" stroke="#C62828" stroke-width="2"/>
      <line x1="850" y1="200" x2="1050" y2="200" stroke="#C62828" stroke-width="2"/>
      <line x1="1050" y1="200" x2="1050" y2="270" stroke="#C62828" stroke-width="2" marker-end="url(#arrowB)"/>

      <rect x="950" y="270" width="200" height="35" rx="5" fill="#BBDEFB" stroke="#1976D2" stroke-width="2"/>
      <text x="1050" y="293" text-anchor="middle" font-size="12" fill="#1976D2" font-weight="bold">执行工具 → 下一转</text>
    </g>

    <!-- Recovery paths side box -->
    <g transform="translate(1050, 50)">
      <rect x="0" y="0" width="230" height="220" rx="8" fill="#FFFDE7" stroke="#FBC02D" stroke-width="2"/>
      <text x="115" y="28" text-anchor="middle" font-size="13" fill="#F57F17" font-weight="bold">恢复路径 (Recovery)</text>

      <rect x="10" y="40" width="210" height="32" rx="4" fill="white" stroke="#FBC02D" stroke-width="1"/>
      <text x="115" y="61" text-anchor="middle" font-size="10" fill="#333">1. Collapse Drain (90%/95%)</text>

      <rect x="10" y="77" width="210" height="32" rx="4" fill="white" stroke="#FBC02D" stroke-width="1"/>
      <text x="115" y="98" text-anchor="middle" font-size="10" fill="#333">2. Reactive Compact (413 恢复)</text>

      <rect x="10" y="114" width="210" height="32" rx="4" fill="white" stroke="#FBC02D" stroke-width="1"/>
      <text x="115" y="135" text-anchor="middle" font-size="10" fill="#333">3. Max Output Tokens 恢复 (3 次)</text>

      <rect x="10" y="151" width="210" height="32" rx="4" fill="white" stroke="#FBC02D" stroke-width="1"/>
      <text x="115" y="172" text-anchor="middle" font-size="10" fill="#333">4. Token Budget Continuation</text>

      <rect x="10" y="188" width="210" height="25" rx="4" fill="#FFF59D" stroke="#F9A825" stroke-width="1"/>
      <text x="115" y="205" text-anchor="middle" font-size="9" fill="#B71C1C">单一路径：每转只触发一种恢复</text>
    </g>
  </g>

  <!-- State transition box -->
  <g transform="translate(50, 690)">
    <rect x="0" y="0" width="1300" height="240" rx="10" fill="#ECEFF1" stroke="#546E7A" stroke-width="2"/>
    <text x="650" y="35" text-anchor="middle" font-size="16" font-weight="bold" fill="#37474F">状态转换 (State Transition at Continue Site)</text>

    <!-- Continue sites explanation -->
    <text x="50" y="65" font-size="12" fill="#546E7A">
      <tspan x="50" dy="0">query.ts 有 7 个 continue 站点，每个站点通过更新 state 对象跳转到下一次迭代：</tspan>
    </text>

    <!-- State update example -->
    <rect x="50" y="80" width="1200" height="140" rx="8" fill="#263238" stroke="#546E7A" stroke-width="1.5"/>
    <text x="70" y="105" font-size="11" fill="#80CBC4" font-family="monospace">
      <tspan x="70" dy="0">// query.ts:1171-1182 - Collapse Drain 恢复后的 continue</tspan>
      <tspan x="70" dy="18">const next: State = {</tspan>
      <tspan x="90" dy="18">messages: drained.messages,</tspan>
      <tspan x="90" dy="18">toolUseContext,</tspan>
      <tspan x="90" dy="18">autoCompactTracking: tracking,</tspan>
      <tspan x="90" dy="18">maxOutputTokensRecoveryCount,</tspan>
      <tspan x="90" dy="18">hasAttemptedReactiveCompact,</tspan>
      <tspan x="90" dy="18">maxOutputTokensOverride: undefined,</tspan>
      <tspan x="90" dy="18">pendingToolUseSummary: undefined,</tspan>
      <tspan x="90" dy="18">stopHookActive: undefined,</tspan>
      <tspan x="90" dy="18">turnCount,</tspan>
      <tspan x="90" dy="18">transition: { reason: 'collapse_drain_retry', committed: drained.committed },</tspan>
      <tspan x="70" dy="18">}</tspan>
      <tspan x="70" dy="18">state = next</tspan>
      <tspan x="70" dy="18">continue  // → 跳转到 while(true) 开头</tspan>
    </text>

    <!-- Transition reasons -->
    <g transform="translate(50, 240)">
      <text x="0" y="15" font-size="11" fill="#546E7A" font-weight="bold">transition.reason 可能值:</text>
      <rect x="150" y="3" width="140" height="22" rx="3" fill="#B3E5FC" stroke="#0288D1" stroke-width="1"/>
      <text x="220" y="18" font-size="10" fill="#01579B">collapse_drain_retry</text>
      <rect x="300" y="3" width="140" height="22" rx="3" fill="#B3E5FC" stroke="#0288D1" stroke-width="1"/>
      <text x="370" y="18" font-size="10" fill="#01579B">reactive_compact_retry</text>
      <rect x="450" y="3" width="140" height="22" rx="3" fill="#B3E5FC" stroke="#0288D1" stroke-width="1"/>
      <text x="520" y="18" font-size="10" fill="#01579B">max_output_tokens_recovery</text>
      <rect x="600" y="3" width="140" height="22" rx="3" fill="#B3E5FC" stroke="#0288D1" stroke-width="1"/>
      <text x="670" y="18" font-size="10" fill="#01579B">stop_hook_blocking</text>
      <rect x="750" y="3" width="140" height="22" rx="3" fill="#B3E5FC" stroke="#0288D1" stroke-width="1"/>
      <text x="820" y="18" font-size="10" fill="#01579B">token_budget_continuation</text>
      <rect x="900" y="3" width="80" height="22" rx="3" fill="#C8E6C9" stroke="#2E7D32" stroke-width="1"/>
      <text x="940" y="18" font-size="10" fill="#2E7D32">next_turn</text>
    </g>
  </g>

  <!-- Loop back arrow -->
  <path d="M 1350 520 L 1380 520 L 1380 400 L 1350 400" fill="none" stroke="#4CAF50" stroke-width="3" marker-end="url(#arrowB)" stroke-dasharray="8,4"/>
  <text x="1365" y="460" font-size="11" fill="#2E7D32" font-weight="bold">循环继续</text>
</svg>
```

---

## B.2 任务拆解与决策路径

### 决策路径选择机制

Claude Code 使用**多层上下文管理策略**来动态调整决策路径：

```
┌─────────────────────────────────────────────────────────────────┐
│                    上下文管理层次结构                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  L1: Tool Result Budget (第一道防线)                             │
│      - 限制工具结果的 aggregate 大小                             │
│      - 文件：utils/toolResultStorage.ts                         │
│      - 阈值：per-message 预算                                    │
│                                                                 │
│  L2: Snip Compact (轻量级修剪)                                   │
│      - 移除旧消息但保留语义边界                                 │
│      - 文件：services/compact/snipCompact.ts                    │
│      - Feature: HISTORY_SNIP                                    │
│                                                                 │
│  L3: Micro Compact (缓存编辑)                                    │
│      - 删除重复的 tool_use/tool_result 对                        │
│      - 文件：services/compact/microCompact.ts                   │
│      - 触发：缓存命中率下降时                                    │
│                                                                 │
│  L4: Auto Compact (主动压缩)                                     │
│      - 达到阈值前主动压缩 (90% context window)                  │
│      - 文件：services/compact/autoCompact.ts                    │
│      - 阈值：effectiveWindow - 13,000 tokens                    │
│                                                                 │
│  L5: Context Collapse (折叠式压缩)                              │
│      - 分级提交 (90% commit, 95% blocking spawn)                │
│      - 文件：services/contextCollapse/index.js                  │
│      - Feature: CONTEXT_COLLAPSE                                │
│                                                                 │
│  L6: Reactive Compact (被动恢复)                                │
│      - API 返回 413 后的最后防线                                 │
│      - 文件：services/compact/reactiveCompact.ts                │
│      - 触发：isWithheldPromptTooLong()                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 动态调整代码位置

| 调整类型 | 文件 | 关键函数 | 行号 |
|----------|------|----------|------|
| Snip | query.ts | `snipModule!.snipCompactIfNeeded()` | 401-410 |
| Micro | query.ts | `deps.microcompact()` | 413-426 |
| Auto | query.ts | `deps.autocompact()` | 453-543 |
| Collapse | query.ts | `contextCollapse.applyCollapsesIfNeeded()` | 440-447 |
| Reactive | query.ts | `reactiveCompact.tryReactiveCompact()` | 1119-1166 |

---

## B.3 规划系统数据流

### 关键数据流图

```svg
<svg viewBox="0 0 1300 700" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <marker id="flowArrow" markerWidth="14" markerHeight="10" refX="12" refY="5" orient="auto">
      <polygon points="0 0, 14 5, 0 10" fill="#1976D2"/>
    </marker>
    <linearGradient id="gradUser" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#E3F2FD;stop-opacity:1"/>
      <stop offset="100%" style="stop-color:#90CAF9;stop-opacity:1"/>
    </linearGradient>
    <linearGradient id="gradLLM" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#FFF8E1;stop-opacity:1"/>
      <stop offset="100%" style="stop-color:#FFCC80;stop-opacity:1"/>
    </linearGradient>
    <linearGradient id="gradTool" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#F3E5F5;stop-opacity:1"/>
      <stop offset="100%" style="stop-color:#CE93D8;stop-opacity:1"/>
    </linearGradient>
    <linearGradient id="gradMem" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#E8F5E9;stop-opacity:1"/>
      <stop offset="100%" style="stop-color:#A5D6A7;stop-opacity:1"/>
    </linearGradient>
  </defs>

  <!-- Title -->
  <text x="650" y="40" text-anchor="middle" font-size="22" font-weight="bold" fill="#333">
    任务规划数据流 (Planning Data Flow)
  </text>

  <!-- User Input -->
  <g transform="translate(50, 80)">
    <rect x="0" y="0" width="250" height="100" rx="8" fill="url(#gradUser)" stroke="#1976D2" stroke-width="2"/>
    <text x="125" y="35" text-anchor="middle" font-size="16" font-weight="bold" fill="#0D47A1">用户输入</text>
    <text x="125" y="58" text-anchor="middle" font-size="12" fill="#1565C0">processUserInput()</text>
    <text x="125" y="80" text-anchor="middle" font-size="11" fill="#1976D2">• Slash 命令解析</text>
  </g>

  <!-- Context Prep -->
  <g transform="translate(350, 80)">
    <rect x="0" y="0" width="280" height="120" rx="8" fill="url(#gradMem)" stroke="#388E3C" stroke-width="2"/>
    <text x="140" y="35" text-anchor="middle" font-size="16" font-weight="bold" fill="#1B5E20">上下文准备</text>

    <text x="20" y="60" font-size="11" fill="#2E7D32">• System Context (Git, CLAUDE.md)</text>
    <text x="20" y="80" font-size="11" fill="#2E7D32">• User Context (Memory, Date)</text>
    <text x="20" y="100" font-size="11" fill="#2E7D32">• Tool Pool Assembly</text>
  </g>

  <!-- LLM Call -->
  <g transform="translate(680, 80)">
    <rect x="0" y="0" width="280" height="120" rx="8" fill="url(#gradLLM)" stroke="#F57C00" stroke-width="2"/>
    <text x="140" y="35" text-anchor="middle" font-size="16" font-weight="bold" fill="#E65100">LLM API 调用</text>
    <text x="140" y="60" text-anchor="middle" font-size="12" fill="#EF6C00">deps.callModel()</text>
    <text x="140" y="82" text-anchor="middle" font-size="11" fill="#F57C00">• Streaming: message_start</text>
    <text x="140" y="100" text-anchor="middle" font-size="11" fill="#F57C00">• Thinking Config</text>
  </g>

  <!-- Decision -->
  <g transform="translate(1010, 80)">
    <polygon points="140,0 280,60 140,120 0,60" fill="#FFCDD2" stroke="#C62828" stroke-width="2"/>
    <text x="140" y="55" text-anchor="middle" font-size="14" font-weight="bold" fill="#B71C1C">决策</text>
    <text x="140" y="75" text-anchor="middle" font-size="11" fill="#C62828">Tool Use?</text>
  </g>

  <!-- Arrows Row 1 -->
  <line x1="300" y1="130" x2="345" y2="130" stroke="#1976D2" stroke-width="2.5" marker-end="url(#flowArrow)"/>
  <line x1="630" y1="130" x2="675" y2="130" stroke="#388E3C" stroke-width="2.5" marker-end="url(#flowArrow)"/>
  <line x1="960" y1="130" x2="1005" y2="130" stroke="#F57C00" stroke-width="2.5" marker-end="url(#flowArrow)"/>

  <!-- Tool Execution Path (YES) -->
  <g transform="translate(100, 250)">
    <rect x="0" y="0" width="300" height="100" rx="8" fill="url(#gradTool)" stroke="#7B1FA2" stroke-width="2"/>
    <text x="150" y="35" text-anchor="middle" font-size="16" font-weight="bold" fill="#4A148C">工具执行</text>
    <text x="150" y="60" text-anchor="middle" font-size="12" fill="#6A1B9A">StreamingToolExecutor / runTools</text>
    <text x="150" y="80" text-anchor="middle" font-size="11" fill="#7B1FA2">• 权限检查 → 执行 → 结果</text>
  </g>

  <!-- Attachment Injection -->
  <g transform="translate(450, 250)">
    <rect x="0" y="0" width="300" height="100" rx="8" fill="#FFF9C4" stroke="#FBC02D" stroke-width="2"/>
    <text x="150" y="35" text-anchor="middle" font-size="14" font-weight="bold" fill="#F57F17">附件注入</text>
    <text x="150" y="58" text-anchor="middle" font-size="11" fill="#F9A825">• Memory Prefetch</text>
    <text x="150" y="78" text-anchor="middle" font-size="11" fill="#F9A825">• Skill Discovery</text>
    <text x="150" y="95" text-anchor="middle" font-size="11" fill="#F9A825">• Queued Commands</text>
  </g>

  <!-- Next Turn -->
  <g transform="translate(800, 250)">
    <rect x="0" y="0" width="280" height="100" rx="8" fill="#E0E0E0" stroke="#616161" stroke-width="2"/>
    <text x="140" y="45" text-anchor="middle" font-size="16" font-weight="bold" fill="#212121">状态更新</text>
    <text x="140" y="70" text-anchor="middle" font-size="12" fill="#424242">state = next</text>
    <text x="140" y="90" text-anchor="middle" font-size="11" fill="#616161">continue → 下一转</text>
  </g>

  <!-- Arrows Row 2 -->
  <path d="M 270 230 L 270 245 L 145 245" fill="none" stroke="#7B1FA2" stroke-width="2" marker-end="url(#flowArrow)"/>
  <line x1="400" y1="300" x2="445" y2="300" stroke="#7B1FA2" stroke-width="2.5" marker-end="url(#flowArrow)"/>
  <line x1="750" y1="300" x2="795" y2="300" stroke="#F9A825" stroke-width="2.5" marker-end="url(#flowArrow)"/>
  <line x1="1080" y1="300" x2="1125" y2="300" stroke="#616161" stroke-width="2.5" marker-end="url(#flowArrow)"/>

  <!-- Loop back -->
  <path d="M 1100 300 L 1250 300 L 1250 130 L 960 130" fill="none" stroke="#4CAF50" stroke-width="2.5" stroke-dasharray="8,4" marker-end="url(#flowArrow)"/>
  <text x="1180" y="115" font-size="11" fill="#2E7D32" font-weight="bold">循环</text>

  <!-- Direct Response Path (NO) -->
  <g transform="translate(1050, 400)">
    <line x1="-70" y1="-280" x2="-70" y2="-260" stroke="#C62828" stroke-width="2"/>
    <line x1="-70" y1="-260" x2="50" y2="-260" stroke="#C62828" stroke-width="2"/>
    <line x1="50" y1="-260" x2="50" y2="-100" stroke="#C62828" stroke-width="2" marker-end="url(#flowArrow)"/>

    <rect x="0" y="-80" width="200" height="60" rx="6" fill="#C8E6C9" stroke="#2E7D32" stroke-width="2"/>
    <text x="100" y="-55" text-anchor="middle" font-size="13" font-weight="bold" fill="#1B5E20">Stop Hooks</text>
    <text x="100" y="-35" text-anchor="middle" font-size="11" fill="#2E7D32">handleStopHooks()</text>
  </g>

  <!-- Token Budget -->
  <g transform="translate(100, 420)">
    <rect x="0" y="0" width="280" height="90" rx="8" fill="#E1F5FE" stroke="#0288D1" stroke-width="2"/>
    <text x="140" y="35" text-anchor="middle" font-size="14" font-weight="bold" fill="#01579B">Token Budget</text>
    <text x="140" y="58" text-anchor="middle" font-size="11" fill="#0277BD">• Per-turn 预算检查</text>
    <text x="140" y="78" text-anchor="middle" font-size="11" fill="#0277BD">• Diminishing Returns 检测</text>
  </g>

  <!-- Completion -->
  <g transform="translate(450, 430)">
    <rect x="0" y="0" width="250" height="70" rx="8" fill="#C8E6C9" stroke="#2E7D32" stroke-width="2"/>
    <text x="125" y="40" text-anchor="middle" font-size="16" font-weight="bold" fill="#1B5E20">完成</text>
    <text x="125" y="60" text-anchor="middle" font-size="11" fill="#2E7D32">return { reason: 'completed' }</text>
  </g>

  <!-- Arrows Row 3 -->
  <line x1="250" y1="465" x2="275" y2="465" stroke="#0288D1" stroke-width="2.5" marker-end="url(#flowArrow)"/>
  <line x1="700" y1="465" x2="725" y2="465" stroke="#2E7D32" stroke-width="2.5" marker-end="url(#flowArrow)"/>
</svg>
```

---

## B.4 Harness Engineering 设计决策评价

### 可扩展性 (Scalability) - 8/10

**优点**:
- **分层上下文管理**: 6 层策略可按需启用/禁用
- **Feature flags 驱动**: 每层都有独立的 feature flag
- **继续站点模式**: 统一的 `state = next; continue` 模式便于添加新路径

**缺点**:
- **复杂性耦合**: 7 个 continue 站点分散在 1400+ 行代码中
- **状态载体膨胀**: `State` 类型有 10+ 字段，追踪困难

**代码证据**:
```typescript
// query.ts:1093-1115 - Collapse Drain 恢复路径
if (feature('CONTEXT_COLLAPSE') && contextCollapse &&
    state.transition?.reason !== 'collapse_drain_retry') {
  const drained = contextCollapse.recoverFromOverflow(messagesForQuery, querySource)
  if (drained.committed > 0) {
    const next: State = {
      messages: drained.messages,
      toolUseContext,
      autoCompactTracking: tracking,
      // ... 10+ 字段
      transition: { reason: 'collapse_drain_retry', committed: drained.committed },
    }
    state = next
    continue  // 跳转到 while 开头
  }
}
```

---

### 安全边界 (Safety Boundary) - 9/10

**优点**:
- **多层恢复路径**: 单一路径失效时有备用方案
- **电路断路器**: `MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3` 防止无限重试
- **预算强制执行**: Token Budget 提前终止低效任务

**代码证据**:
```typescript
// autoCompact.ts:257-265 - 电路断路器
if (tracking?.consecutiveFailures !== undefined &&
    tracking.consecutiveFailures >= MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES) {
  return { wasCompacted: false }  // 停止重试
}
```

---

### 可观察性 (Observability) - 7/10

**优点**:
- **Transition Tracking**: `transition.reason` 记录每次继续的原因
- **分析事件**: `logEvent('tengu_auto_compact_succeeded', {...})`
- **Profiling Checkpoints**: `queryCheckpoint()` 标记关键路径

**缺点**:
- **恢复路径日志不足**: 难以诊断为什么特定恢复被触发
- **状态快照有限**: 无法重现特定时刻的完整 `State`

---

### 性能损耗 (Performance Overhead) - 7/10

**优点**:
- **预判式压缩**: AutoCompact 在达到硬限制前压缩
- **缓存感知**: MicroCompact 删除重复工具对

**缺点**:
- **每转检查开销**: 6 层上下文管理每次迭代都要检查
- **记忆化局限**: `getGitStatus` 等记忆化只在会话级别

**代码证据**:
```typescript
// query.ts:400-548 - 每次迭代都执行这些检查
// Snip (400-410)
if (feature('HISTORY_SNIP')) {
  const snipResult = snipModule!.snipCompactIfNeeded(messagesForQuery)
  // ...
}
// Micro (413-426)
const microcompactResult = await deps.microcompact(...)
// Auto (453-543)
const { compactionResult, consecutiveFailures } = await deps.autocompact(...)
// Collapse (440-447)
if (feature('CONTEXT_COLLAPSE')) {
  const collapseResult = await contextCollapse.applyCollapsesIfNeeded(...)
}
```

---

## B.5 最小化实现 (MRE) - Python

```python
"""
Planning & Reasoning - Minimal Reference Implementation
视角 B: 任务规划最小化实现 (约 90 行)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
import random


class TransitionReason(Enum):
    """继续原因类型"""
    NEXT_TURN = "next_turn"
    MAX_OUTPUT_TOKENS_RECOVERY = "max_output_tokens_recovery"
    STOP_HOOK_BLOCKING = "stop_hook_blocking"
    TOKEN_BUDGET_CONTINUATION = "token_budget_continuation"
    COMPLETED = "completed"


@dataclass
class State:
    """查询循环状态载体"""
    messages: List[Dict] = field(default_factory=list)
    tool_context: Dict = field(default_factory=dict)
    turn_count: int = 1
    max_output_tokens_recovery: int = 0
    has_attempted_compact: bool = False
    transition: Optional[TransitionReason] = None


@dataclass
class QueryConfig:
    """查询配置"""
    max_turns: int = 10
    context_window: int = 200000
    auto_compact_threshold: float = 0.90  # 90% 触发
    max_output_tokens_recovery: int = 3


class PlanningEngine:
    """规划引擎 - 核心决策循环"""

    def __init__(self, config: QueryConfig):
        self.config = config
        self.state = State()

    async def query_loop(self, user_input: str) -> Dict:
        """
        主查询循环 (对应 query.ts:queryLoop)

        流程:
        1. 上下文管理 (Snip/Micro/Auto/Collapse)
        2. 调用 LLM
        3. 工具执行
        4. 后置评估 → 决定下一转或完成
        """
        # 初始化状态
        self.state.messages.append({"type": "user", "content": user_input})

        while True:
            # ========== 阶段 1: 上下文管理 ==========
            context_result = await self._manage_context()
            if context_result.compacted:
                yield {"type": "system", "subtype": "compact_boundary"}

            # ========== 阶段 2: 调用 LLM ==========
            assistant_message = await self._call_llm()
            yield assistant_messages

            # ========== 阶段 3: 决策 ==========
            needs_follow_up = self._needs_tool_execution(assistant_messages)

            if not needs_follow_up:
                # 无需工具 → 进入后置评估
                stop_result = await self._handle_stop_hooks()

                if stop_result.prevent_continuation:
                    return self._build_result("stop_hook_prevented")

                # Token Budget 检查
                budget_decision = self._check_token_budget()
                if budget_decision.continue_turn:
                    self.state.messages.append({
                        "type": "user",
                        "content": budget_decision.nudge_message,
                        "is_meta": True
                    })
                    self.state.transition = TransitionReason.TOKEN_BUDGET_CONTINUATION
                    continue  # 下一转

                return self._build_result("completed")

            # ========== 阶段 4: 工具执行 ==========
            tool_messages = await self._execute_tools(assistant_messages)
            self.state.messages.extend(tool_messages)

            # 检查最大转数
            if self.state.turn_count >= self.config.max_turns:
                return self._build_result("max_turns_reached")

            # 准备下一转
            self._prepare_next_turn()
            self.state.transition = TransitionReason.NEXT_TURN
            # continue → 下一次迭代

    async def _manage_context(self) -> Any:
        """
        上下文管理 (Snip → Micro → Auto → Collapse)

        对应 query.ts:400-548
        """
        tokens_used = self._count_tokens()
        threshold = self.config.context_window * self.config.auto_compact_threshold

        if tokens_used > threshold:
            # 触发自动压缩
            print(f"[AutoCompact] {tokens_used} > {threshold}")
            return type('Result', (), {'compacted': True})()

        return type('Result', (), {'compacted': False})()

    async def _call_llm(self) -> Dict:
        """
        调用 LLM API (模拟)

        对应 query.ts:659-863 (streaming loop)
        """
        # 实际实现会调用 Claude API
        return {
            "type": "assistant",
            "content": "Thought process...",
            "tool_calls": self._simulate_tool_calls()
        }

    def _needs_tool_execution(self, message: Dict) -> bool:
        """
        决策：是否需要工具执行

        对应 query.ts:1062 (needsFollowUp check)
        """
        return bool(message.get("tool_calls"))

    async def _execute_tools(self, assistant_message: Dict) -> List[Dict]:
        """
        工具执行

        对应 query.ts:1363-1410
        """
        results = []
        for tool_call in assistant_message.get("tool_calls", []):
            # 权限检查 → 执行 → 结果
            result = await self._call_tool(tool_call)
            results.append({
                "type": "user",
                "tool_result": result,
                "tool_use_id": tool_call["id"]
            })
        return results

    async def _handle_stop_hooks(self) -> Any:
        """
        Stop Hooks - 后置评估

        对应 query.ts:1267-1280
        """
        # 评估是否应该继续
        prevent = False  # 简化实现
        return type('Result', (), {
            'prevent_continuation': prevent,
            'blocking_errors': []
        })()

    def _check_token_budget(self) -> Any:
        """
        Token Budget 检查

        对应 query.ts:1308-1354
        """
        # 简化实现：总是继续
        return type('Result', (), {
            'continue_turn': False,
            'nudge_message': None
        })()

    def _prepare_next_turn(self):
        """准备下一转状态"""
        self.state.turn_count += 1
        self.state.max_output_tokens_recovery = 0
        self.state.has_attempted_compact = False

    def _count_tokens(self) -> int:
        """估算 token 数"""
        return sum(len(str(m)) for m in self.state.messages) // 4

    def _simulate_tool_calls(self) -> List[Dict]:
        """模拟工具调用 (测试用)"""
        return []  # 简化实现

    async def _call_tool(self, tool_call: Dict) -> Any:
        """调用单个工具"""
        return f"Result for {tool_call.get('name', 'unknown')}"

    def _build_result(self, reason: str) -> Dict:
        """构建最终结果"""
        return {
            "type": "result",
            "subtype": "success" if reason == "completed" else "error",
            "reason": reason,
            "turn_count": self.state.turn_count,
            "messages": self.state.messages,
        }


# 使用示例
async def main():
    config = QueryConfig(max_turns=5)
    engine = PlanningEngine(config)

    async for msg in engine.query_loop("分析这个项目"):
        print(f"消息：{msg.get('type')}")
```

---

## B.6 挑战性思考问题

### 问题 B: 上下文管理策略的选择

**场景**: Claude Code 实现了 6 层上下文管理策略 (Snip → Micro → Auto → Collapse → Reactive)，每层都有不同的触发条件和压缩策略。在某些边缘情况下，多层策略可能同时触发（如：Snip 释放了 token 但 Auto 仍认为超过阈值），导致压缩行为难以预测。

**挑战问题**:
> 如果你要重新设计上下文管理层次结构，你会选择以下哪种架构改进方案？请分析每种方案的优劣，并给出你的推荐。
>
> **方案 A: 统一调度器模式**
> - 添加一个中央调度器，根据当前 token 使用率动态选择最优压缩策略
> - 各层策略不再顺序执行，而是作为可插拔的"策略提供者"
>
> **方案 B: 反馈控制环路**
> - 引入 PID 控制器思想，根据历史压缩效果动态调整触发阈值
> - 例如：如果 Auto Compact 频繁触发但效果差，自动提高阈值
>
> **方案 C: 预测式压缩**
> - 基于 token 增长率预测何时需要压缩，提前在低峰期执行
> - 类似 JVM 的 GC 预测机制
>
> **具体要求**:
> 1. 选择一种方案并详细说明实现设计（需要修改哪些接口，添加什么数据结构）
> 2. 分析该方案对以下指标的影响：
>    - API 调用成本（压缩本身消耗 token）
>    - 响应延迟（压缩执行时间）
>    - 上下文质量（保留的语义信息量）
> 3. 如何验证你的改进有效？设计一个可量化的评估方案

**提示**: 参考分布式系统中的负载均衡策略、数据库的查询优化器设计、或操作系统的内存页面置换算法。

---

*视角 B 分析完成*
