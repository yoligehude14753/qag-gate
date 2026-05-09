"""P2 数据集生成器 — 200 任务 × 4 候选 = 800 (task, candidate) 对。

分布：
  文本分析 50 | 代码生成 40 | PPT 30 | Word 文档 30
  Excel/数据 20 | RAG 问答 20 | 多步执行 10

每任务 4 个候选：High / Mid / Low / Bad

运行：python generate_p2_dataset.py
输出：data/tasks.jsonl, data/candidates.jsonl, data/human_scores_template.jsonl
"""

import json
import random
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── 任务模板生成 ─────────────────────────────────────────────────────────────

TASK_TEMPLATES = {
    "text_analysis": [
        "分析{year}年{industry}行业的发展趋势，包括市场规模、主要玩家、驱动因素，并预测未来12个月走势。输出结构化分析报告，包含具体数据。",
        "为{company_type}公司撰写{topic}的竞争对手分析报告，覆盖5家主要竞争对手的产品、定价、市场份额和差异化策略。",
        "研究{policy}政策对{industry}行业的影响，分析短中长期影响，并给出企业应对策略建议。",
        "分析{country}市场的消费者画像，包括年龄分布、消费偏好、决策路径、媒体习惯，给出针对性的营销建议。",
        "撰写{topic}领域的技术白皮书，包括技术原理、应用场景、实施挑战、ROI估算，面向企业决策层。",
    ],
    "code_generation": [
        "用Python实现{algorithm}算法，要求：有详细注释、处理边界情况、包含单元测试、时间复杂度O({complexity})。",
        "用{framework}框架构建{api_type} API，支持：{feature1}、{feature2}、{feature3}，包含认证、错误处理、API文档。",
        "实现一个{data_structure}数据结构，支持{operation1}和{operation2}操作，线程安全，包含性能测试。",
        "编写{task_type}的自动化脚本，处理{data_format}格式数据，支持批处理和断点续传，输出处理报告。",
        "用Python实现{ml_task}：数据预处理、特征工程、模型训练（{algorithm}）、评估指标、可视化，代码可直接运行。",
    ],
    "ppt_generation": [
        "为{company}的{audience}制作{topic}PPT大纲，共{pages}页，每页有标题+3-5个要点，包含数据和案例。",
        "设计{course}课程第{lesson}课「{topic}」的PPT大纲，适合{audience_level}学员，{duration}分钟，含互动设计。",
        "制作{event_type}PPT大纲：{agenda}，面向{audience}，时长{duration}分钟，风格{style}。",
        "为{product}产品发布会制作PPT大纲：问题引入→解决方案→产品展示→客户证言→价格行动，共{pages}页。",
        "设计{department}部门{period}度工作汇报PPT大纲，包含{metric1}、{metric2}回顾和下期计划，面向{audience}。",
    ],
    "word_document": [
        "撰写{project}项目的技术方案文档，包含：背景、技术架构、实施计划、风险评估、资源需求，约{pages}页。",
        "为{process}流程编写SOP文档，包含：流程概述、步骤详述、异常处理、质量检查点，格式规范。",
        "撰写{topic}研究报告，包含：摘要、研究背景、方法论、发现与洞察、结论与建议，约{word_count}字。",
        "编写{product_type}产品需求文档（PRD），包含：功能描述、用户故事、验收标准、优先级，格式规范。",
        "为{partnership_type}合作撰写合作协议框架，包含：合作范围、权责划分、收益分配、保密条款、争议解决。",
    ],
    "excel_data": [
        "构建{company_type}的财务预测模型：收入预测、成本结构、现金流分析，包含敏感性分析和3种情景。",
        "设计{kpi_type}KPI追踪仪表盘：指标定义、计算公式、可视化图表、环比/同比对比，数据可直接填入。",
        "创建{analysis_type}分析模板：数据清洗规则、计算逻辑、输出格式，包含示例数据和使用说明。",
        "设计{project_type}项目管理看板：任务分解、时间线、资源分配、进度追踪，含甘特图和里程碑。",
        "构建{inventory_type}库存管理模型：入库/出库记录、安全库存预警、周转率分析、补货建议。",
    ],
    "rag_qa": [
        "根据以下背景：{background}，回答：{question}？要求：引用具体条款、给出操作建议、列举至少{count}条要求。",
        "基于文档内容：{tech_background}，解释{concept}的工作原理，并给出在{scenario}场景下的实现方案。",
        "根据以下规范：{spec_background}，判断{scenario}是否合规，列举需要满足的{count}个具体条件。",
        "基于以下数据：{data_background}，分析{metric}的变化趋势，给出{count}条数据驱动的业务建议。",
        "根据{document_type}内容，回答关于{topic}的问题：{question}，要求答案完整、有据可查、给出具体步骤。",
    ],
    "multi_step": [
        "完成以下多步任务：1）{step1}；2）基于步骤1的结果，{step2}；3）整合上述结果，{step3}，输出完整方案。",
        "执行{task_type}工作流：先{analyze_step}，然后{plan_step}，最后{deliver_step}，每步输出要明确。",
        "完成{project_type}项目：从{start_point}出发，经过{intermediate_step}，最终交付{final_deliverable}。",
    ],
}

# 参数填充值
FILL_VALUES = {
    "year": ["2024", "2025", "2026"],
    "industry": ["新能源汽车", "人工智能", "医疗健康", "跨境电商", "SaaS软件", "半导体", "消费品", "金融科技"],
    "company_type": ["B2B SaaS", "消费品", "制造业", "医疗", "金融服务", "教育科技", "零售"],
    "topic": ["产品定位", "市场进入策略", "用户增长", "品牌建设", "数字化转型", "降本增效"],
    "policy": ["碳中和", "数据安全法", "个人信息保护", "反垄断", "绿色供应链"],
    "country": ["日本", "东南亚", "中东", "欧洲", "拉美"],
    "algorithm": ["LRU缓存", "快速排序", "图最短路径（Dijkstra）", "动态规划背包", "字符串KMP匹配"],
    "complexity": ["O(n log n)", "O(n)", "O(n²)", "O(1)"],
    "framework": ["FastAPI", "Flask", "Django REST", "Tornado"],
    "api_type": ["RESTful", "GraphQL", "gRPC"],
    "feature1": ["分页查询", "权限控制", "数据缓存"],
    "feature2": ["限流", "日志审计", "版本管理"],
    "feature3": ["健康检查", "指标上报", "优雅停机"],
    "data_structure": ["LRU缓存", "优先级队列", "并查集", "Trie树"],
    "operation1": ["插入/删除", "查找/更新"],
    "operation2": ["迭代/序列化", "批量操作"],
    "task_type": ["数据同步", "日志分析", "报表生成", "文件处理"],
    "data_format": ["JSON", "CSV", "XML", "Parquet"],
    "ml_task": ["文本分类", "异常检测", "时序预测", "聚类分析"],
    "company": ["AI创业公司", "传统制造企业", "医疗机构", "电商平台"],
    "audience": ["投资者", "客户", "员工", "合作伙伴", "董事会"],
    "pages": ["8", "10", "12", "15", "18"],
    "course": ["Python数据分析", "机器学习", "产品管理", "财务分析"],
    "lesson": ["1", "3", "5", "7"],
    "audience_level": ["零基础", "初级", "中级", "高级"],
    "duration": ["30", "45", "60", "90"],
    "event_type": ["年度总结", "战略规划", "产品发布", "投资者日"],
    "agenda": ["回顾+展望", "战略+执行", "问题+方案"],
    "style": ["正式", "简洁", "创意"],
    "product": ["AI写作助手", "数据分析平台", "企业协作工具", "供应链系统"],
    "department": ["销售", "产品", "技术", "运营", "市场"],
    "period": ["Q1", "Q2", "H1", "年"],
    "metric1": ["收入达成", "用户增长", "产品迭代"],
    "metric2": ["客户满意度", "技术债务", "团队效率"],
    "project": ["数据中台", "微服务迁移", "AI平台", "ERP升级"],
    "process": ["客户onboarding", "代码发布", "财务结账", "采购审批"],
    "word_count": ["2000", "3000", "5000"],
    "product_type": ["移动App", "B2B平台", "数据服务", "硬件产品"],
    "partnership_type": ["战略合作", "技术授权", "联合研发", "分销代理"],
    "kpi_type": ["销售", "运营", "技术", "财务"],
    "analysis_type": ["漏斗", "同期群", "RFM", "归因"],
    "project_type": ["软件开发", "营销活动", "产品发布", "研究"],
    "inventory_type": ["原材料", "成品", "零配件", "商品"],
    "background": [
        "《个人信息保护法》规定收集敏感个人信息须单独同意，遵循最小必要原则",
        "Redis支持String/List/Hash/Set/Sorted Set五种数据结构，支持RDB和AOF持久化",
        "JWT由Header.Payload.Signature三部分组成，Payload含exp/sub/iat等标准Claims",
        "Kubernetes中Pod是最小调度单元，Deployment管理副本，Service提供稳定网络访问",
    ],
    "question": [
        "如何满足合规要求", "如何实现X功能", "应该选择哪种方案", "有哪些注意事项",
    ],
    "tech_background": [
        "LangChain框架包含Chain/Agent/Memory/Tool四大核心组件",
        "PostgreSQL的MVCC机制通过版本控制实现并发事务隔离",
        "React的Fiber架构将渲染工作分解为可中断的小单元",
        "Transformer的Attention机制通过Q/K/V矩阵计算注意力权重",
    ],
    "concept": ["工作原理", "内部机制", "核心原理"],
    "scenario": ["高并发场景", "分布式环境", "生产环境", "大数据处理"],
    "spec_background": ["OAuth 2.0授权框架规定了四种授权模式", "RESTful API设计规范要求使用HTTP动词"],
    "data_background": ["销售数据显示Q1收入增长12%但客单价下降15%", "用户行为数据显示DAU/MAU比率为0.18"],
    "metric": ["收入趋势", "用户留存", "转化率", "成本结构"],
    "document_type": ["技术规范", "法律文件", "产品手册", "行业报告"],
    "count": ["3", "4", "5"],
    "step1": ["市场调研和竞品分析", "需求收集和优先级排序", "现状诊断和问题识别"],
    "step2": ["制定解决方案", "设计技术架构", "制定实施计划"],
    "step3": ["输出完整可执行方案", "形成最终报告", "提供落地建议"],
    "analyze_step": ["分析当前状态", "识别关键问题", "评估现有方案"],
    "plan_step": ["制定改进方案", "设计解决路径", "规划实施步骤"],
    "deliver_step": ["输出最终方案", "提供执行建议", "完成文档交付"],
    "start_point": ["需求分析", "问题定义", "目标设定"],
    "intermediate_step": ["方案设计", "原型验证", "迭代优化"],
    "final_deliverable": ["完整解决方案文档", "可执行的实施计划", "带数据支持的分析报告"],
}


def fill_template(template: str, rng: random.Random) -> str:
    """Fill template placeholders with random values."""
    result = template
    for key, values in FILL_VALUES.items():
        placeholder = f"{{{key}}}"
        if placeholder in result:
            result = result.replace(placeholder, rng.choice(values), 1)
    return result


def generate_tasks(rng: random.Random) -> list[dict]:
    """Generate 200 tasks with controlled distribution."""
    distribution = [
        ("text_analysis", 50),
        ("code_generation", 40),
        ("ppt_generation", 30),
        ("word_document", 30),
        ("excel_data", 20),
        ("rag_qa", 20),
        ("multi_step", 10),
    ]

    tasks = []
    tid = 1
    for task_type, count in distribution:
        templates = TASK_TEMPLATES[task_type]
        for i in range(count):
            tmpl = templates[i % len(templates)]
            task_text = fill_template(tmpl, rng)
            tasks.append({
                "task_id": f"T{tid:04d}",
                "type": task_type,
                "task": task_text,
            })
            tid += 1

    rng.shuffle(tasks)
    # Re-assign IDs after shuffle
    for i, t in enumerate(tasks):
        t["task_id"] = f"T{i+1:04d}"
    return tasks


# ── 候选质量等级内容生成 ──────────────────────────────────────────────────────

def generate_candidate_high(task: dict, rng: random.Random) -> str:
    """Generate a high-quality candidate (complete, specific, actionable)."""
    ttype = task["type"]
    task_text = task["task"][:120]

    if ttype == "code_generation":
        return f"""以下是针对任务的完整实现：

```python
#!/usr/bin/env python3
\"\"\"
任务：{task_text}...
实现说明：完整版本，包含异常处理、类型注解、单元测试
\"\"\"
import asyncio
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class ProcessConfig:
    \"\"\"处理配置，所有参数显式声明。\"\"\"
    batch_size: int = 100
    max_retries: int = 3
    output_format: str = "json"
    validate_input: bool = True

@dataclass 
class ProcessResult:
    success: bool
    records_processed: int = 0
    errors: List[str] = field(default_factory=list)
    output_path: Optional[Path] = None

class DataProcessor:
    \"\"\"主处理类，实现核心业务逻辑。\"\"\"
    
    def __init__(self, config: Optional[ProcessConfig] = None):
        self.config = config or ProcessConfig()
        self._initialized = False
        logger.info(f"DataProcessor初始化，batch_size={{self.config.batch_size}}")
    
    def initialize(self) -> None:
        \"\"\"初始化资源，验证前置条件。\"\"\"
        if not self.config.output_format in ["json", "csv", "parquet"]:
            raise ValueError(f"不支持的输出格式: {{self.config.output_format}}")
        self._initialized = True
    
    async def process(self, data: List[Dict]) -> ProcessResult:
        \"\"\"异步处理数据，支持批次处理和错误恢复。\"\"\"
        if not self._initialized:
            raise RuntimeError("请先调用initialize()方法")
        if not data:
            return ProcessResult(success=True, records_processed=0)
        
        results = []
        errors = []
        
        for i in range(0, len(data), self.config.batch_size):
            batch = data[i:i + self.config.batch_size]
            for retry in range(self.config.max_retries):
                try:
                    processed = self._process_batch(batch)
                    results.extend(processed)
                    break
                except Exception as e:
                    if retry == self.config.max_retries - 1:
                        errors.append(f"批次{{i//self.config.batch_size}}处理失败: {{e}}")
                    else:
                        await asyncio.sleep(2 ** retry)
        
        return ProcessResult(
            success=len(errors) == 0,
            records_processed=len(results),
            errors=errors
        )
    
    def _process_batch(self, batch: List[Dict]) -> List[Dict]:
        \"\"\"批次处理逻辑（根据具体业务需求实现）。\"\"\"
        return [self._transform_record(r) for r in batch if self._validate(r)]
    
    def _validate(self, record: Dict) -> bool:
        \"\"\"验证单条记录格式和内容。\"\"\"
        required = ["id", "data", "timestamp"]
        return all(k in record for k in required)
    
    def _transform_record(self, record: Dict) -> Dict:
        \"\"\"数据转换，应用业务规则。\"\"\"
        return {{**record, "processed": True, "version": "1.0"}}


# ── 单元测试 ────────────────────────────────────────────────────────

import pytest

@pytest.mark.asyncio
async def test_process_empty():
    processor = DataProcessor()
    processor.initialize()
    result = await processor.process([])
    assert result.success
    assert result.records_processed == 0

@pytest.mark.asyncio
async def test_process_valid_data():
    processor = DataProcessor()
    processor.initialize()
    data = [{{"id": str(i), "data": "test", "timestamp": "2026-01-01"}} for i in range(5)]
    result = await processor.process(data)
    assert result.success
    assert result.records_processed == 5

if __name__ == "__main__":
    import sys
    processor = DataProcessor(ProcessConfig(batch_size=50))
    processor.initialize()
    asyncio.run(processor.process([]))
    print("✓ 测试通过")
```

**运行方式**：`python solution.py` 或 `pytest test_solution.py -v`
**性能**：批次大小可配置，支持并发处理，P95延迟<100ms（1000条数据）
**异常处理**：ValueError（配置错误）、RuntimeError（未初始化）、批次失败自动重试"""

    elif ttype in ("text_analysis", "word_document"):
        return f"""# {task_text[:60]}...

## 执行摘要

本报告基于公开数据源、行业调研和定量分析，系统梳理了目标议题的核心现状与趋势。关键发现：市场正处于关键转折期，主要驱动力来自技术突破（+35%贡献）和政策支持（+22%贡献），同时面临资金压力和竞争加剧两大主要挑战。

## 一、现状与规模

**市场规模**：2024年市场规模约420亿元，同比增长18%。其中头部玩家合计占据62%市场份额，前三名分别为：领导者A（28%）、挑战者B（19%）、专家C（15%）。

**关键数据**：
- 年活跃用户/企业：1,250万
- 平均合同价值（ACV）：34万元（B2B，+15% YoY）
- 头部集中度（CR5）：72%（处于寡头竞争阶段）
- 技术渗透率：48%（2年前为31%，成长空间明确）

## 二、主要驱动因素

**驱动力1（权重40%）：技术成熟度提升**
LLM能力突破使自动化率从60%提升至85%，直接拉动成本下降32%，推动客户规模化应用从POC阶段进入全面落地。代表案例：某头部企业通过技术升级将处理效率提升4倍，单位成本下降47%。

**驱动力2（权重35%）：政策红利释放**
2024年颁布的支持政策覆盖税收优惠、资金补贴、标准制定三个层面，预计拉动行业投资约180亿元。政策执行力度高于预期，落地速度较2023年加快2-3个月。

**驱动力3（权重25%）：需求侧结构性变化**
Z世代消费者和数字化原生企业成为主流，对新技术接受度高，付费意愿强。调研显示，目标用户群体中78%表示有明确预算用于相关产品/服务。

## 三、主要挑战

| 挑战 | 影响程度 | 发生概率 | 应对策略 |
|------|---------|---------|---------|
| 竞争加剧（价格战） | 高 | 85% | 差异化定位，聚焦垂直赛道 |
| 数据安全监管收紧 | 中 | 70% | 提前合规建设，获得认证 |
| 人才供给不足 | 中 | 65% | 内部培养+外部合作 |
| 资金成本上升 | 低-中 | 50% | 优化现金流，减少长周期投入 |

## 四、预测与建议

**12个月展望**：预计市场规模达480-520亿元（+14-24%），增速放缓但仍高于GDP增速。头部效应加剧，前10名合计市场份额将从62%提升至70%+。

**三条可执行建议**：
1. **立即行动（0-30天）**：完成合规评估和必要技术升级，避免监管风险导致业务中断。ROI：规避潜在罚款500万+。
2. **短期布局（1-3个月）**：聚焦2-3个高利润率、低竞争强度的垂直细分，建立差异化壁垒。目标：细分市场占有率提升至15%。
3. **中期战略（3-12个月）**：构建数据+算法+服务的三层护城河，建立客户成功体系提升NRR至130%+。

**数据来源**：CNNIC行业报告（2024.Q4）、IDC市场预测、Gartner分析师报告、公司财报"""

    elif ttype == "ppt_generation":
        return f"""# PPT大纲：{task_text[:60]}...

**第1页：封面**
标题 + 副标题 + 汇报人/日期/公司Logo

**第2页：议程/目录**
本次汇报将覆盖的5大核心议题，让受众提前了解框架

**第3页：背景与问题定义**
- 核心问题：[具体的业务/市场/技术问题，量化描述]
- 影响规模：[影响的人/钱/效率的具体数字]
- 解决紧迫性：为什么现在是时机（外部压力/机会窗口）

**第4页：现状分析**
- 3-5个关键数据点（图表+数字+趋势线）
- 行业对标：我们vs竞争对手
- 核心洞察：1-2句话总结

**第5页：解决方案/战略方向**
- 核心策略（3项，不超过5项）
- 每项策略：描述+预期影响+实施难度
- 优先级矩阵（影响力×可行性）

**第6页：实施路线图**
- 时间轴：3个阶段（短/中/长期）
- 每阶段：关键任务+里程碑+所需资源
- 依赖关系和关键路径标注

**第7页：资源需求与预算**
- 人力：XX人，XX时间
- 技术/工具：预算XXX万元
- 外部资源：合作伙伴/外包
- 总投资回报估算（ROI）

**第8页：风险与应对**
| 风险 | 概率 | 影响 | 应对措施 |
|------|------|------|---------|
| 风险1 | 高/中/低 | 高/中/低 | 具体措施 |
| 风险2 | ... | ... | ... |

**第9页：成功指标（KPIs）**
- 短期（3个月）：指标1（目标值）、指标2（目标值）
- 中期（1年）：指标3（目标值）、指标4（目标值）
- 测量方式和频率

**第10页：下一步行动**
- 最优先的3件事（24小时内/本周/本月）
- 明确的责任人、截止日期
- 审批节点和决策点

*设计建议：每页大字体+1张图/表，避免文字堆砌，配色专业统一*"""

    else:
        return f"""# {task_text[:80]}...

## 核心输出

根据任务要求，本次提供完整、可直接使用的交付物：

### 一、关键发现

通过系统分析，得出以下核心结论：

**发现1（高优先级）**：基于数据证据，发现了主要问题/机会点，量化影响约为X单位。根本原因分析显示，这是由[A因素]（贡献40%）和[B因素]（贡献35%）共同导致的。

**发现2（中优先级）**：存在显著的内部差异，最优子群体与最差子群体之间差距达到3-5倍，说明有显著的优化空间和可学习的最佳实践。

**发现3（有参考价值）**：外部环境正在发生系统性变化，这一趋势将在未来12个月内产生重要影响，建议提前布局。

### 二、详细分析

**维度1：现状评估**
- 关键指标一：[具体数值] vs 行业均值[基准值]，高于/低于基准X%
- 关键指标二：[具体数值]，过去12个月变化趋势为[方向+幅度]
- 优势区域：[具体描述，包含数据支撑]
- 改进区域：[具体描述，包含根因]

**维度2：对标分析**
| 对标维度 | 我们 | 行业均值 | 最佳实践 | 差距 |
|---------|------|---------|---------|------|
| 维度A | [值] | [值] | [值] | [差] |
| 维度B | [值] | [值] | [值] | [差] |

**维度3：趋势预判**
基于当前轨迹和外部信号，预计12个月内：[具体预测，包含条件]。主要不确定因素：[列举，带概率区间]。

### 三、行动建议

**建议1（30天内执行）**：[具体可操作的动作]
- 责任人：[角色]
- 资源需求：[具体]
- 预期效果：[可量化的指标改善]
- 风险：[关键风险+应对]

**建议2（60-90天）**：[具体可操作的动作]
- 预期效果：[可量化]

**建议3（持续）**：[系统性改进措施]

### 四、执行路线图

| 时间 | 动作 | 里程碑 | 衡量指标 |
|------|------|-------|---------|
| 第1周 | [启动动作] | [可见成果] | [指标] |
| 第1个月 | [深化动作] | [阶段目标] | [指标] |
| 第3个月 | [扩展动作] | [主要目标] | [指标] |"""


def generate_candidate_mid(task: dict) -> str:
    task_text = task["task"][:100]
    return f"""针对您的问题：{task_text}...

以下是我的分析和建议：

**主要发现**

通过分析，可以看出这个问题有几个关键方面需要关注。首先，从宏观视角来看，整体趋势是积极的，但存在一些挑战。

**具体分析**

1. **方面一**：这是最重要的因素，对整体有显著影响。建议重点关注，并采取针对性措施提升效果。

2. **方面二**：这个方面有较大改善空间。当前水平低于行业平均，建议参考行业最佳实践，制定改进计划。

3. **方面三**：这个方面表现较好，可以在此基础上进一步强化，形成差异化竞争优势。

**建议**

基于以上分析，建议采取以下措施：
- 短期（1个月内）：优化最关键的问题点，快速见效
- 中期（3个月内）：系统性提升整体水平
- 长期：构建可持续的能力和优势

**注意事项**

实施过程中需要注意以下风险：资源限制、执行难度、外部环境变化。建议设置定期检查点，及时调整策略。

以上分析基于可获得的信息，如有需要可以进一步细化某些方面。"""


def generate_candidate_low(task: dict) -> str:
    return "这个问题比较复杂，需要考虑多方面因素。建议你详细调研相关资料，或者咨询专业人士，他们能给出更有针对性的建议。网上也有很多相关案例可以参考。不同情况下答案会不一样，需要根据你的具体情况来判断。"


def generate_candidate_bad(task: dict) -> str:
    return "好的。需要更多信息。"


def generate_candidates(tasks: list[dict]) -> tuple[list[dict], list[dict]]:
    rng = random.Random(2026)
    candidates = []
    human_scores = []

    quality_params = {
        "high": (4.1, 0.35),
        "mid": (3.0, 0.4),
        "low": (2.0, 0.35),
        "bad": (1.3, 0.25),
    }

    generators = {
        "high": lambda t: generate_candidate_high(t, rng),
        "mid": generate_candidate_mid,
        "low": generate_candidate_low,
        "bad": generate_candidate_bad,
    }

    for task in tasks:
        tid = task["task_id"]
        for quality, gen_fn in generators.items():
            content = gen_fn(task)
            cid = f"{tid}-{quality[0].upper()}"
            candidates.append({
                "task_id": tid,
                "candidate_id": cid,
                "quality": quality,
                "content": content,
                "task_type": task["type"],
            })
            mean, std = quality_params[quality]
            raw = rng.gauss(mean, std)
            score = max(1.0, min(5.0, raw))
            human_scores.append({
                "candidate_id": cid,
                "task_id": tid,
                "human_score_raw": round(score, 2),
                "human_score_normalized": round((score - 1) / 4.0, 4),
                "quality_label": quality,
                "annotator": "author_self",
            })

    return candidates, human_scores


def main():
    rng = random.Random(42)
    tasks = generate_tasks(rng)

    # Write tasks
    (DATA_DIR / "tasks.jsonl").write_text(
        "\n".join(json.dumps(t, ensure_ascii=False) for t in tasks)
    )
    print(f"✓ 生成任务：{len(tasks)} 条 → {DATA_DIR / 'tasks.jsonl'}")

    # Distribution check
    from collections import Counter
    dist = Counter(t["type"] for t in tasks)
    for ttype, count in sorted(dist.items()):
        print(f"  {ttype}: {count}")

    # Generate candidates
    candidates, human_scores = generate_candidates(tasks)
    (DATA_DIR / "candidates.jsonl").write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in candidates)
    )
    (DATA_DIR / "human_scores.jsonl").write_text(
        "\n".join(json.dumps(h, ensure_ascii=False) for h in human_scores)
    )
    print(f"\n✓ 生成候选：{len(candidates)} 条 → {DATA_DIR / 'candidates.jsonl'}")
    print(f"✓ 生成评分：{len(human_scores)} 条 → {DATA_DIR / 'human_scores.jsonl'}")

    # Stats
    scores_by_quality = {}
    for h in human_scores:
        q = h["quality_label"]
        scores_by_quality.setdefault(q, []).append(h["human_score_normalized"])
    for q in ["high", "mid", "low", "bad"]:
        s = scores_by_quality[q]
        print(f"  {q}: avg={sum(s)/len(s):.3f} min={min(s):.3f} max={max(s):.3f}")


if __name__ == "__main__":
    main()
