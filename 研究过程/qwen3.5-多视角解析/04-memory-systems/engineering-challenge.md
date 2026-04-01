# 视角 D：记忆系统 - 挑战性工程问题

## 问题：当前记忆系统设计的挑战

### 背景

当前的记忆系统设计存在以下挑战：

1. **压缩质量不一致**
   - snip/micro/autocompact 产生的摘要质量参差不齐
   - snip 只是简单删除，丢失信息
   - autocompact 依赖 LLM，成本高且不可控

2. **记忆检索效率低**
   - 线性搜索在大规模记忆中效率低下
   - 时间线索引不足以支持语义检索
   - 无法找到"相关但不连续"的记忆

3. **上下文污染**
   - 不相关信息可能混入压缩摘要
   - 压缩后的摘要可能包含噪声
   - 重要细节可能被忽略

4. **记忆一致性**
   - 多 agent 场景下记忆同步困难
   - 不同 agent 可能有不同的记忆视图
   - 记忆冲突解决机制缺失

---

## 思考题

设计一个更智能的记忆系统，考虑以下方案：

### 1. 语义压缩

```python
class SemanticCompressor:
    def __init__(self, embedding_model):
        self.embedding_model = embedding_model
        self.memory_embeddings = {}

    def compute_similarity(self, text1: str, text2: str) -> float:
        """计算语义相似度"""
        emb1 = self.embedding_model.encode(text1)
        emb2 = self.embedding_model.encode(text2)
        return cosine_similarity(emb1, emb2)

    def smart_compress(self, entries: List[MemoryEntry]) -> str:
        """智能压缩：基于语义聚类"""
        # 1. 计算所有条目的 embedding
        # 2. 聚类相似的条目
        # 3. 为每个聚类生成摘要
        # 4. 合并聚类摘要
        ...
```

### 2. 记忆评分系统

```python
class MemoryScorer:
    """记忆评分器"""

    def compute_score(self, entry: MemoryEntry) -> float:
        """计算记忆重要性分数"""
        # 因素：时效性、使用频率、重要性标记
        recency_score = self._recency_factor(entry.timestamp)
        frequency_score = self._usage_frequency(entry.id)
        importance_score = self._importance_marker(entry.metadata)

        return (
            recency_score * 0.3 +
            frequency_score * 0.4 +
            importance_score * 0.3
        )

    def _recency_factor(self, timestamp: float) -> float:
        """时效性因子：越新分数越高"""
        age_days = (time.time() - timestamp) / 86400
        return 1.0 / (1.0 + age_days)  # 衰减函数
```

### 3. 分层检索

```python
class HierarchicalRetriever:
    """分层检索器"""

    def __init__(self, memory_store: MemoryStore, scorer: MemoryScorer):
        self.memory_store = memory_store
        self.scorer = scorer
        self.index = {}  # 关键词→记忆 ID

    def retrieve(self, query: str, top_k: int = 10) -> List[MemoryEntry]:
        """分层检索"""
        # 1. 关键词检索
        keyword_results = self._keyword_search(query)

        # 2. 语义检索
        semantic_results = self._semantic_search(query)

        # 3. 融合结果（加权排序）
        merged = self._merge_results(keyword_results, semantic_results)

        # 4. 应用评分过滤
        scored = [(e, self.scorer.compute_score(e)) for e in merged]
        scored.sort(key=lambda x: x[1], reverse=True)

        return [e for e, _ in scored[:top_k]]
```

---

## 多 Agent 记忆同步方案

```python
class MultiAgentMemorySync:
    """多 Agent 记忆同步器"""

    def __init__(self, central_store: MemoryStore):
        self.central_store = central_store
        self.local_caches = {}  # agent_id → cache

    def broadcast(self, entry: MemoryEntry, exclude: List[str] = None):
        """广播记忆更新"""
        for agent_id, cache in self.local_caches.items():
            if agent_id not in (exclude or []):
                cache.add(entry)

    def sync(self, agent_id: str) -> List[MemoryEntry]:
        """同步记忆到指定 agent"""
        cache = self.local_caches.get(agent_id)
        if not cache:
            return list(self.central_store.entries.values())

        # 增量同步：只同步 cache 中没有的条目
        missing_ids = set(self.central_store.entries.keys()) - set(cache.entries.keys())
        return [self.central_store.entries[eid] for eid in missing_ids]

    def resolve_conflicts(self, entries: List[MemoryEntry]) -> MemoryEntry:
        """解决记忆冲突"""
        # 策略：最新时间戳获胜
        return max(entries, key=lambda e: e.timestamp)
```

---

## 延伸思考

1. **记忆图**: 如何使用知识图谱组织记忆之间的关系？
   - 实体抽取和关系识别
   - 图结构存储和查询
   - 基于图的推理

2. **可解释性**: 如何让记忆检索过程可解释？
   - 检索原因追踪
   - 相关性评分解释
   - 记忆来源溯源

3. **增量学习**: 如何从用户反馈中学习记忆的重要性？
   - 显式反馈收集
   - 隐式行为分析
   - 评分模型在线更新

4. **隐私保护**: 如何保护敏感记忆？
   - 记忆加密存储
   - 访问控制策略
   - 敏感信息自动识别和脱敏
