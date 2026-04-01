# 视角 B：任务规划 - 挑战性工程问题

## 问题：决策逻辑分散，难以全局理解

### 背景

当前的决策系统有 9 个 continue 站点，每个站点代表一种决策路径。这种设计的缺点是：

1. **决策逻辑分散**
   - 难以全局理解所有决策路径
   - 新开发者需要阅读多处代码才能理解完整流程

2. **新增决策路径需要修改核心循环**
   - 违反开闭原则（对扩展开放，对修改关闭）
   - 每次新增决策类型都要改动 `queryLoop` 函数

3. **决策之间的优先级关系不明确**
   - 当多个决策条件同时满足时，处理顺序依赖代码位置
   - 难以动态调整优先级

---

## 思考题

如果要设计一个更加模块化、可扩展的决策系统，你会采用什么架构模式？

### 方案对比

| 方案 | 优点 | 缺点 |
|------|------|------|
| **状态机模式** | 状态显式化，转换清晰 | 状态转换复杂时难以维护 |
| **责任链模式** | 链式传递，易于扩展 | 性能开销，链条过长难调试 |
| **策略模式** | 可插拔策略 | 配置复杂，策略间耦合 |
| **规则引擎** | 灵活配置，业务友好 | 实现复杂，学习成本高 |

---

## 推荐方案设计

### 基于责任链的决策处理器

```python
class DecisionHandler:
    def __init__(self):
        self.handlers = []
        self.priorities = {}

    def register(self, handler, priority=0, conditions=None):
        """注册决策处理器"""
        self.handlers.append((priority, handler, conditions or []))
        self.handlers.sort(key=lambda x: x[0], reverse=True)

    async def process(self, context):
        """处理决策"""
        for priority, handler, conditions in self.handlers:
            if all(c.check(context) for c in conditions):
                decision = await handler.handle(context)
                if decision:
                    return decision
        return None
```

### 使用示例

```python
# 注册决策处理器
engine = DecisionEngine()

# 高优先级：Token 超限处理
engine.register(
    CompactHandler(),
    priority=10,
    conditions=[TokenThresholdCondition(threshold=0.8)]
)

# 中优先级：错误处理
engine.register(
    ErrorHandler(),
    priority=5,
    conditions=[ErrorCondition()]
)

# 低优先级：默认继续
engine.register(
    ContinueHandler(),
    priority=1,
    conditions=[]
)
```

---

## 延伸思考

1. 如何实现**运行时动态注册**新的决策处理器？
2. 如何设计**决策追踪系统**以便调试和审计？
3. 如何处理**决策冲突**（多个处理器同时触发）？
4. 如何实现**决策超时**和**降级处理**？
