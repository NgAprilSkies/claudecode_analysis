# Claude Code 综合架构图

## 完整系统架构全景图

```svg
<svg viewBox="0 0 1600 1200" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <marker id="arch Arrow" markerWidth="12" markerHeight="8" refX="10" refY="4" orient="auto">
      <polygon points="0 0, 12 4, 0 8" fill="#2c3e50"/>
    </marker>
    <linearGradient id="grad User" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#3498db;stop-opacity:1"/>
      <stop offset="100%" style="stop-color:#2980b9;stop-opacity:1"/>
    </linearGradient>
    <linearGradient id="grad Engine" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#9b59b6;stop-opacity:1"/>
      <stop offset="100%" style="stop-color:#8e44ad;stop-opacity:1"/>
    </linearGradient>
    <linearGradient id="grad Query" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#e74c3c;stop-opacity:1"/>
      <stop offset="100%" style="stop-color:#c0392b;stop-opacity:1"/>
    </linearGradient>
    <linearGradient id="grad Tool" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#27ae60;stop-opacity:1"/>
      <stop offset="100%" style="stop-color:#229954;stop-opacity:1"/>
    </linearGradient>
    <linearGradient id="grad Memory" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#f39c12;stop-opacity:1"/>
      <stop offset="100%" style="stop-color:#d68910;stop-opacity:1"/>
    </linearGradient>
    <linearGradient id="grad State" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#1abc9c;stop-opacity:1"/>
      <stop offset="100%" style="stop-color:#16a085;stop-opacity:1"/>
    </linearGradient>
  </defs>

  <!-- Background -->
  <rect width="1600" height="1200" fill="#ecf0f1"/>

  <!-- Title -->
  <text x="800" y="50" text-anchor="middle" font-size="28" font-weight="bold" fill="#2c3e50">
    Claude Code 完整系统架构图
  </text>
  <text x="800" y="80" text-anchor="middle" font-size="16" fill="#7f8c8d">
    Claude Code Complete System Architecture
  </text>

  <!-- USER LAYER -->
  <g transform="translate(50, 110)">
    <rect x="0" y="0" width="1500" height="80" rx="10" fill="url(#grad User)" stroke="#2471a3" stroke-width="3"/>
    <text x="750" y="35" text-anchor="middle" font-size="20" font-weight="bold" fill="white">用户交互层 (User Interaction Layer)</text>
    <text x="750" y="60" text-anchor="middle" font-size="14" fill="#d6eaf8">CLI / SDK / REPL / Cowork / Desktop App</text>
  </g>

  <!-- Arrow -->
  <path d="M 750 190 L 750 215" fill="none" stroke="#2c3e50" stroke-width="3" marker-end="url(#arch Arrow)"/>

  <!-- QUERY ENGINE LAYER -->
  <g transform="translate(50, 220)">
    <rect x="0" y="0" width="300" height="200" rx="10" fill="url(#grad Engine)" stroke="#7d3c98" stroke-width="3"/>
    <text x="150" y="40" text-anchor="middle" font-size="18" font-weight="bold" fill="white">QueryEngine</text>
    <text x="150" y="70" text-anchor="middle" font-size="12" fill="#e8daef">核心引擎类</text>
    <text x="150" y="110" text-anchor="middle" font-size="11" fill="#d6eaf8">• submitMessage()</text>
    <text x="150" y="135" text-anchor="middle" font-size="11" fill="#d6eaf8">• interrupt()</text>
    <text x="150" y="160" text-anchor="middle" font-size="11" fill="#d6eaf8">• getMessages()</text>
    <text x="150" y="185" text-anchor="middle" font-size="11" fill="#d6eaf8">• getSessionId()</text>
  </g>

  <!-- Query Loop -->
  <g transform="translate(380, 220)">
    <rect x="0" y="0" width="500" height="200" rx="10" fill="url(#grad Query)" stroke="#a93226" stroke-width="3"/>
    <text x="250" y="35" text-anchor="middle" font-size="18" font-weight="bold" fill="white">Query Loop (query.ts)</text>
    <text x="250" y="60" text-anchor="middle" font-size="12" fill="#fadbd8">核心决策循环</text>

    <!-- Loop steps -->
    <rect x="20" y="80" width="220" height="45" rx="5" fill="#fadbd8" stroke="#c0392b" stroke-width="1.5"/>
    <text x="130" y="100" text-anchor="middle" font-size="11" fill="#922b21">1. 上下文管理</text>
    <text x="130" y="117" text-anchor="middle" font-size="10" fill="#922b21">(Snip/Micro/Auto/Collapse)</text>

    <rect x="260" y="80" width="220" height="45" rx="5" fill="#fadbd8" stroke="#c0392b" stroke-width="1.5"/>
    <text x="370" y="100" text-anchor="middle" font-size="11" fill="#922b21">2. LLM API 调用</text>
    <text x="370" y="117" text-anchor="middle" font-size="10" fill="#922b21">(deps.callModel - 流式)</text>

    <rect x="20" y="135" width="220" height="45" rx="5" fill="#fadbd8" stroke="#c0392b" stroke-width="1.5"/>
    <text x="130" y="155" text-anchor="middle" font-size="11" fill="#922b21">3. 工具执行</text>
    <text x="130" y="172" text-anchor="middle" font-size="10" fill="#922b21">(StreamingToolExecutor)</text>

    <rect x="260" y="135" width="220" height="45" rx="5" fill="#fadbd8" stroke="#c0392b" stroke-width="1.5"/>
    <text x="370" y="155" text-anchor="middle" font-size="11" fill="#922b21">4. 后置评估</text>
    <text x="370" y="172" text-anchor="middle" font-size="10" fill="#922b21">(Stop Hooks + Budget)</text>
  </g>

  <!-- Context Management -->
  <g transform="translate(910, 220)">
    <rect x="0" y="0" width="340" height="200" rx="10" fill="#f9e79f" stroke="#f1c40f" stroke-width="3"/>
    <text x="170" y="35" text-anchor="middle" font-size="16" font-weight="bold" fill="#7d6608">上下文管理层次</text>

    <rect x="15" y="55" width="310" height="28" rx="4" fill="white" stroke="#f39c12" stroke-width="1"/>
    <text x="170" y="74" text-anchor="middle" font-size="10" fill="#333">L1: Snip Compact (轻量级修剪)</text>

    <rect x="15" y="88" width="310" height="28" rx="4" fill="white" stroke="#f39c12" stroke-width="1"/>
    <text x="170" y="107" text-anchor="middle" font-size="10" fill="#333">L2: Micro Compact (缓存编辑)</text>

    <rect x="15" y="121" width="310" height="28" rx="4" fill="white" stroke="#f39c12" stroke-width="1"/>
    <text x="170" y="140" text-anchor="middle" font-size="10" fill="#333">L3: Auto Compact (90% 主动)</text>

    <rect x="15" y="154" width="310" height="28" rx="4" fill="white" stroke="#f39c12" stroke-width="1"/>
    <text x="170" y="173" text-anchor="middle" font-size="10" fill="#333">L4: Context Collapse (分级)</text>

    <rect x="15" y="187" width="310" height="28" rx="4" fill="#fdebd0" stroke="#e67e22" stroke-width="1"/>
    <text x="170" y="206" text-anchor="middle" font-size="10" fill="#d35400">L5: Reactive Compact (413 恢复)</text>
  </g>

  <!-- Arrow from Query Loop to Context -->
  <path d="M 880 320 L 905 320" fill="none" stroke="#2c3e50" stroke-width="2" marker-end="url(#arch Arrow)"/>

  <!-- TOOL SYSTEM LAYER -->
  <g transform="translate(50, 450)">
    <rect x="0" y="0" width="1500" height="280" rx="10" fill="url(#grad Tool)" stroke="#1e8449" stroke-width="3"/>
    <text x="750" y="35" text-anchor="middle" font-size="20" font-weight="bold" fill="white">工具系统 (Tool System)</text>

    <!-- Built-in Tools -->
    <g transform="translate(30, 55)">
      <rect x="0" y="0" width="350" height="200" rx="8" fill="#d5f5e3" stroke="#27ae60" stroke-width="2"/>
      <text x="175" y="30" text-anchor="middle" font-size="16" font-weight="bold" fill="#196f3d">Built-in Tools</text>

      <text x="20" y="55" font-size="11" fill="#1e8449">• AgentTool (子代理)</text>
      <text x="20" y="75" font-size="11" fill="#1e8449">• BashTool (Shell 命令)</text>
      <text x="20" y="95" font-size="11" fill="#1e8449">• FileReadTool (读取文件)</text>
      <text x="20" y="115" font-size="11" fill="#1e8449">• FileEditTool (编辑文件)</text>
      <text x="20" y="135" font-size="11" fill="#1e8449">• FileWriteTool (写入文件)</text>
      <text x="20" y="155" font-size="11" fill="#1e8449">• GlobTool (文件搜索)</text>
      <text x="20" y="175" font-size="11" fill="#1e8449">• GrepTool (内容搜索)</text>
      <text x="190" y="55" font-size="11" fill="#1e8449">• WebSearchTool</text>
      <text x="190" y="75" font-size="11" fill="#1e8449">• WebFetchTool</text>
      <text x="190" y="95" font-size="11" fill="#1e8449">• TodoWriteTool</text>
      <text x="190" y="115" font-size="11" fill="#1e8449">• TaskCreate/Update/List</text>
      <text x="190" y="135" font-size="11" fill="#1e8449">• AskUserQuestionTool</text>
      <text x="190" y="155" font-size="11" fill="#1e8449">• SkillTool (技能)</text>
      <text x="190" y="175" font-size="11" fill="#1e8449">• EnterPlanModeTool</text>
    </g>

    <!-- MCP Tools -->
    <g transform="translate(410, 55)">
      <rect x="0" y="0" width="350" height="200" rx="8" fill="#fdebd0" stroke="#e67e22" stroke-width="2"/>
      <text x="175" y="30" text-anchor="middle" font-size="16" font-weight="bold" fill="#a04000">MCP Tools</text>
      <text x="175" y="55" text-anchor="middle" font-size="11" fill="#ba4a00">Model Context Protocol</text>

      <rect x="15" y="70" width="320" height="35" rx="4" fill="white" stroke="#e67e22" stroke-width="1"/>
      <text x="175" y="92" text-anchor="middle" font-size="10" fill="#333">• 动态服务器发现</text>

      <rect x="15" y="110" width="320" height="35" rx="4" fill="white" stroke="#e67e22" stroke-width="1"/>
      <text x="175" y="132" text-anchor="middle" font-size="10" fill="#333">• 工具自动注册</text>

      <rect x="15" y="150" width="320" height="35" rx="4" fill="white" stroke="#e67e22" stroke-width="1"/>
      <text x="175" y="172" text-anchor="middle" font-size="10" fill="#333">• 协议适配层</text>
    </g>

    <!-- Tool Execution -->
    <g transform="translate(790, 55)">
      <rect x="0" y="0" width="350" height="200" rx="8" fill="#e8daef" stroke="#8e44ad" stroke-width="2"/>
      <text x="175" y="30" text-anchor="middle" font-size="16" font-weight="bold" fill="#5b2c6f">工具执行流程</text>

      <rect x="15" y="55" width="320" height="30" rx="4" fill="white" stroke="#8e44ad" stroke-width="1"/>
      <text x="175" y="75" text-anchor="middle" font-size="10" fill="#333">1. canUseTool() - 权限检查</text>

      <rect x="15" y="90" width="320" height="30" rx="4" fill="white" stroke="#8e44ad" stroke-width="1"/>
      <text x="175" y="110" text-anchor="middle" font-size="10" fill="#333">2. StreamingToolExecutor - 并发分区</text>

      <rect x="15" y="125" width="320" height="30" rx="4" fill="white" stroke="#8e44ad" stroke-width="1"/>
      <text x="175" y="145" text-anchor="middle" font-size="10" fill="#333">3. Tool.call() - 实际执行</text>

      <rect x="15" y="160" width="320" height="30" rx="4" fill="white" stroke="#8e44ad" stroke-width="1"/>
      <text x="175" y="180" text-anchor="middle" font-size="10" fill="#333">4. renderToolResultMessage() - UI</text>
    </g>

    <!-- Permission System -->
    <g transform="translate(1170, 55)">
      <rect x="0" y="0" width="300" height="200" rx="8" fill="#fadbd8" stroke="#c0392b" stroke-width="2"/>
      <text x="150" y="30" text-anchor="middle" font-size="16" font-weight="bold" fill="#922b21">权限系统</text>

      <rect x="10" y="50" width="280" height="30" rx="4" fill="white" stroke="#c0392b" stroke-width="1"/>
      <text x="150" y="70" text-anchor="middle" font-size="10" fill="#333">PermissionMode: default/auto/bypass/plan</text>

      <rect x="10" y="85" width="280" height="30" rx="4" fill="white" stroke="#c0392b" stroke-width="1"/>
      <text x="150" y="105" text-anchor="middle" font-size="10" fill="#333">alwaysAllowRules</text>

      <rect x="10" y="120" width="280" height="30" rx="4" fill="white" stroke="#c0392b" stroke-width="1"/>
      <text x="150" y="140" text-anchor="middle" font-size="10" fill="#333">alwaysDenyRules</text>

      <rect x="10" y="155" width="280" height="30" rx="4" fill="white" stroke="#c0392b" stroke-width="1"/>
      <text x="150" y="175" text-anchor="middle" font-size="10" fill="#333">alwaysAskRules</text>
    </g>
  </g>

  <!-- MEMORY SYSTEM LAYER -->
  <g transform="translate(50, 760)">
    <rect x="0" y="0" width="1500" height="250" rx="10" fill="url(#grad Memory)" stroke="#b7950b" stroke-width="3"/>
    <text x="750" y="35" text-anchor="middle" font-size="20" font-weight="bold" fill="white">记忆系统 (Memory System)</text>

    <!-- L1: Working -->
    <g transform="translate(30, 55)">
      <rect x="0" y="0" width="280" height="170" rx="8" fill="#fef9e7" stroke="#f4d03f" stroke-width="2"/>
      <text x="140" y="30" text-anchor="middle" font-size="15" font-weight="bold" fill="#7d6608">L1: 工作记忆</text>

      <rect x="10" y="45" width="260" height="50" rx="4" fill="white" stroke="#f4d03f" stroke-width="1"/>
      <text x="140" y="65" text-anchor="middle" font-size="11" fill="#333" font-weight="bold">mutableMessages</text>
      <text x="140" y="82" text-anchor="middle" font-size="10" fill="#7d6608">当前对话消息数组</text>

      <rect x="10" y="105" width="260" height="50" rx="4" fill="white" stroke="#f4d03f" stroke-width="1"/>
      <text x="140" y="125" text-anchor="middle" font-size="11" fill="#333" font-weight="bold">FileStateCache</text>
      <text x="140" y="142" text-anchor="middle" font-size="10" fill="#7d6608">LRU 文件读取缓存</text>
    </g>

    <!-- L2: Session -->
    <g transform="translate(340, 55)">
      <rect x="0" y="0" width="280" height="170" rx="8" fill="#fef9e7" stroke="#f4d03f" stroke-width="2"/>
      <text x="140" y="30" text-anchor="middle" font-size="15" font-weight="bold" fill="#7d6608">L2: 会话记忆</text>

      <rect x="10" y="45" width="260" height="50" rx="4" fill="white" stroke="#f4d03f" stroke-width="1"/>
      <text x="140" y="65" text-anchor="middle" font-size="11" fill="#333" font-weight="bold">transcript.jsonl</text>
      <text x="140" y="82" text-anchor="middle" font-size="10" fill="#7d6608">会话转录 (支持 --resume)</text>

      <rect x="10" y="105" width="260" height="50" rx="4" fill="white" stroke="#f4d03f" stroke-width="1"/>
      <text x="140" y="125" text-anchor="middle" font-size="11" fill="#333" font-weight="bold">history.jsonl</text>
      <text x="140" y="142" text-anchor="middle" font-size="10" fill="#7d6608">全局命令历史</text>
    </g>

    <!-- L3: Project -->
    <g transform="translate(650, 55)">
      <rect x="0" y="0" width="280" height="170" rx="8" fill="#fef9e7" stroke="#f4d03f" stroke-width="2"/>
      <text x="140" y="30" text-anchor="middle" font-size="15" font-weight="bold" fill="#7d6608">L3: 项目记忆</text>

      <rect x="10" y="45" width="260" height="50" rx="4" fill="white" stroke="#f4d03f" stroke-width="1"/>
      <text x="140" y="65" text-anchor="middle" font-size="11" fill="#333" font-weight="bold">CLAUDE.md</text>
      <text x="140" y="82" text-anchor="middle" font-size="10" fill="#7d6608">项目级指令 (自动发现)</text>

      <rect x="10" y="105" width="260" height="50" rx="4" fill="white" stroke="#f4d03f" stroke-width="1"/>
      <text x="140" y="125" text-anchor="middle" font-size="11" fill="#333" font-weight="bold">.claude/</text>
      <text x="140" y="142" text-anchor="middle" font-size="10" fill="#7d6608">技能/插件配置</text>
    </g>

    <!-- L4: User -->
    <g transform="translate(960, 55)">
      <rect x="0" y="0" width="280" height="170" rx="8" fill="#fef9e7" stroke="#f4d03f" stroke-width="2"/>
      <text x="140" y="30" text-anchor="middle" font-size="15" font-weight="bold" fill="#7d6608">L4: 用户记忆</text>

      <rect x="10" y="45" width="260" height="50" rx="4" fill="white" stroke="#f4d03f" stroke-width="1"/>
      <text x="140" y="65" text-anchor="middle" font-size="11" fill="#333" font-weight="bold">MEMORY.md</text>
      <text x="140" y="82" text-anchor="middle" font-size="10" fill="#7d6608">长期记忆/用户偏好</text>

      <rect x="10" y="105" width="260" height="50" rx="4" fill="white" stroke="#f4d03f" stroke-width="1"/>
      <text x="140" y="125" text-anchor="middle" font-size="11" fill="#333" font-weight="bold">settings.json</text>
      <text x="140" y="142" text-anchor="middle" font-size="10" fill="#7d6608">全局配置 (权限规则等)</text>
    </g>

    <!-- Memory Prefetch -->
    <g transform="translate(1270, 55)">
      <rect x="0" y="0" width="200" height="170" rx="8" fill="#fff" stroke="#b7950b" stroke-width="2" stroke-dasharray="5,3"/>
      <text x="100" y="50" text-anchor="middle" font-size="13" font-weight="bold" fill="#7d6608">Memory Prefetch</text>
      <text x="100" y="75" text-anchor="middle" font-size="10" fill="#922b21">• Relevant Memory</text>
      <text x="100" y="95" text-anchor="middle" font-size="10" fill="#922b21">• Skill Discovery</text>
      <text x="100" y="115" text-anchor="middle" font-size="10" fill="#922b21">• Nested CLAUDE.md</text>
      <text x="100" y="145" text-anchor="middle" font-size="9" fill="#b7950b">异步预取机制</text>
    </g>
  </g>

  <!-- STATE MANAGEMENT LAYER -->
  <g transform="translate(50, 1040)">
    <rect x="0" y="0" width="1500" height="130" rx="10" fill="url(#grad State)" stroke="#117a65" stroke-width="3"/>
    <text x="750" y="35" text-anchor="middle" font-size="18" font-weight="bold" fill="white">状态管理 (State Management)</text>

    <!-- AppState -->
    <g transform="translate(30, 50)">
      <rect x="0" y="0" width="280" height="60" rx="6" fill="#e8f8f5" stroke="#1abc9c" stroke-width="2"/>
      <text x="140" y="25" text-anchor="middle" font-size="13" font-weight="bold" fill="#0e6655">AppState (Immutable)</text>
      <text x="140" y="45" text-anchor="middle" font-size="10" fill="#148f77">100+ 字段：messages, mcp, fileHistory...</text>
    </g>

    <!-- Store -->
    <g transform="translate(340, 50)">
      <rect x="0" y="0" width="280" height="60" rx="6" fill="#e8f8f5" stroke="#1abc9c" stroke-width="2"/>
      <text x="140" y="25" text-anchor="middle" font-size="13" font-weight="bold" fill="#0e6655">Store 模式</text>
      <text x="140" y="45" text-anchor="middle" font-size="10" fill="#148f77">getState() / setState() / subscribe()</text>
    </g>

    <!-- Feature Flags -->
    <g transform="translate(650, 50)">
      <rect x="0" y="0" width="280" height="60" rx="6" fill="#e8f8f5" stroke="#1abc9c" stroke-width="2"/>
      <text x="140" y="25" text-anchor="middle" font-size="13" font-weight="bold" fill="#0e6655">Feature Flags</text>
      <text x="140" y="45" text-anchor="middle" font-size="10" fill="#148f77">bun:bundle feature() + GrowthBook</text>
    </g>

    <!-- Analytics -->
    <g transform="translate(960, 50)">
      <rect x="0" y="0" width="280" height="60" rx="6" fill="#e8f8f5" stroke="#1abc9c" stroke-width="2"/>
      <text x="140" y="25" text-anchor="middle" font-size="13" font-weight="bold" fill="#0e6655">Analytics</text>
      <text x="140" y="45" text-anchor="middle" font-size="10" fill="#148f77">logEvent() + Profiling Checkpoints</text>
    </g>

    <!-- Error Handling -->
    <g transform="translate(1270, 50)">
      <rect x="0" y="0" width="200" height="60" rx="6" fill="#e8f8f5" stroke="#1abc9c" stroke-width="2"/>
      <text x="100" y="25" text-anchor="middle" font-size="13" font-weight="bold" fill="#0e6655">Error Handling</text>
      <text x="100" y="45" text-anchor="middle" font-size="10" fill="#148f77">logError() + 内存缓冲区</text>
    </g>
  </g>

  <!-- Connecting Arrows between layers -->
  <path d="M 750 420 L 750 445" fill="none" stroke="#2c3e50" stroke-width="3" marker-end="url(#arch Arrow)"/>
  <path d="M 750 730 L 750 755" fill="none" stroke="#2c3e50" stroke-width="3" marker-end="url(#arch Arrow)"/>
  <path d="M 750 1010 L 750 1035" fill="none" stroke="#2c3e50" stroke-width="3" marker-end="url(#arch Arrow)"/>

  <!-- Legend -->
  <g transform="translate(50, 1185)">
    <text x="0" y="12" font-size="11" fill="#7f8c8d" font-style="italic">
      图例：蓝色=用户层 | 紫色=引擎层 | 红色=查询循环 | 黄色=上下文管理 | 绿色=工具系统 | 橙色=记忆系统 | 青色=状态管理
    </text>
  </g>
</svg>
```

---

## 架构关键点说明

### 1. 数据流路径

```
用户输入
    ↓
QueryEngine.submitMessage()
    ↓
queryLoop() 循环
    ├─→ 上下文管理 (Snip → Micro → Auto → Collapse)
    ├─→ LLM API 调用 (流式)
    ├─→ 工具执行 (权限检查 → 并发分区 → 执行 → 结果)
    └─→ 后置评估 (Stop Hooks → Token Budget → 决策)
    ↓
状态更新 (state = next) + continue
```

### 2. 状态载体 (State Carrier)

```typescript
type State = {
  messages: Message[]
  toolUseContext: ToolUseContext
  autoCompactTracking: AutoCompactTrackingState
  maxOutputTokensRecoveryCount: number
  hasAttemptedReactiveCompact: boolean
  maxOutputTokensOverride?: number
  pendingToolUseSummary?: Promise<...>
  stopHookActive?: boolean
  turnCount: number
  transition?: { reason: '...' }
}
```

### 3. Continue 站点 (7 个)

| Continue 原因 | 触发条件 | transition.reason |
|--------------|----------|-------------------|
| Collapse Drain | 上下文折叠恢复 | `collapse_drain_retry` |
| Reactive Compact | 413 错误恢复 | `reactive_compact_retry` |
| Max Output Tokens | token 限制恢复 | `max_output_tokens_recovery` |
| Stop Hook Blocking | 后置钩子阻塞 | `stop_hook_blocking` |
| Token Budget | 预算 continuation | `token_budget_continuation` |
| Next Turn | 正常下一转 | `next_turn` |
| (退出) | 完成 | `completed` |

---

*本架构图应与各视角详细文档配合阅读*
*文档位置：`research/` 目录*
