"""P1 候选生成器：为每个任务生成 high / low 候选内容。

高质量候选：完整、结构清晰、有具体数据/代码/细节
低质量候选：推脱、内容极简、没有实质性帮助

运行：python generate_candidates.py
输出：data/candidates.jsonl + data/human_scores.jsonl
"""

import json
import random
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

# 人工评分（作者自评，1-5分），high候选3.5-5，low候选1-2
# 加入少量噪声模拟真实标注差异
QUALITY_TO_SCORE = {"high": (4.0, 0.4), "low": (1.5, 0.3)}

# 高质量候选按任务类型的模板（代表性样本）
HIGH_CANDIDATES = {
    "T001": """# 2024年中国新能源汽车市场分析报告

## 市场规模
2024年全年新能源汽车销量1058万辆，同比增长35.5%，渗透率突破35%（较2023年31%显著提升）。市场规模约2.1万亿元。

## 主要玩家
比亚迪：427万辆（40.4%市场份额），绝对龙头；特斯拉中国：55万辆；问界：43万辆（华为赋能加速）；理想：50万辆；蔚来：22万辆。

## 增长驱动因素
1. 购置税减免政策（2024年延续），带动约800亿元需求
2. 公共充电桩达312万个（+45%），里程焦虑大幅缓解
3. 800V超充平台普及（60+车型），10分钟充400公里
4. 出口强劲：120万辆（+28%），欧洲+东南亚为主市场

## 2025年预测
预计销量1300-1400万辆，渗透率突破40%。驱动力：以旧换新政策、固态电池商业化（宁德时代/比亚迪Q3量产）、智驾差异化竞争。风险：出口关税压力。

数据来源：中国汽车工业协会（2024.12）、乘联会、财政部政策文件""",

    "T002": """# 大语言模型在企业知识管理中的应用调研报告

## 主流方案对比

| 方案 | 代表产品 | 优势 | 局限 |
|------|---------|------|------|
| RAG+私有知识库 | Notion AI、Confluence AI | 数据安全可控，上下文准确 | 知识更新延迟，需维护向量库 |
| Fine-tuning私有模型 | 企业自训GPT | 高度定制，推理成本低 | 需大量标注数据，训练成本高 |
| API+Prompt工程 | ChatGPT Enterprise | 快速部署，成本低 | 数据上传至云端，合规风险 |

## 实施挑战
1. **数据质量**：企业文档质量参差不齐，非结构化率超70%，影响检索准确性
2. **知识时效**：产品/政策更新频繁，知识库同步机制建设复杂
3. **幻觉风险**：LLM可能编造信息，关键业务场景需人工审核机制

## 案例：某保险公司RAG实践
- 问题：客服日均处理2000+咨询，人工成本高，响应时间>2分钟
- 方案：RAG+内部知识库，gpt-4-turbo作为推理引擎
- 结果：响应时间压缩至<10秒，准确率92%，节省客服成本40%，ROI 18个月回本

## 落地建议
1. 从高频、低风险场景切入（FAQ、文档检索），快速验证价值
2. 建立"AI回答+人工审核"的双层质控机制
3. 优先评估数据安全合规，敏感行业考虑本地部署（Ollama+Llama）""",

    "T006": """```python
import pandas as pd
from datetime import timedelta

def parse_sessions(csv_path: str, session_gap_minutes: int = 30) -> pd.DataFrame:
    \"\"\"将用户行为日志解析为会话数据。\"\"\"
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        raise FileNotFoundError(f"文件不存在: {csv_path}")
    
    required_cols = {'user_id', 'event_type', 'timestamp', 'page_url'}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"缺少必要字段: {missing}")
    
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    df = df.dropna(subset=['timestamp', 'user_id'])
    df = df.drop_duplicates()
    df = df.sort_values(['user_id', 'timestamp'])
    
    gap = timedelta(minutes=session_gap_minutes)
    sessions = []
    
    for user_id, user_df in df.groupby('user_id'):
        session_id = 0
        prev_ts = None
        for _, row in user_df.iterrows():
            if prev_ts is None or (row['timestamp'] - prev_ts) > gap:
                session_id += 1
                session_start = row['timestamp']
            sessions.append({'user_id': user_id, 'session_id': f"{user_id}_s{session_id:04d}",
                           'event_type': row['event_type'], 'timestamp': row['timestamp'],
                           'page_url': row['page_url'], 'session_start': session_start})
            prev_ts = row['timestamp']
    
    result = pd.DataFrame(sessions)
    summary = result.groupby(['user_id', 'session_id', 'session_start']).agg(
        session_end=('timestamp', 'max'), event_count=('event_type', 'count')).reset_index()
    
    print(f"处理完成: {len(df)}条原始记录 → {len(summary)}个会话")
    return summary

if __name__ == '__main__':
    import sys
    result = parse_sessions(sys.argv[1])
    result.to_csv(sys.argv[1].replace('.csv', '_sessions.csv'), index=False)
```
支持完整的异常处理（文件不存在、字段缺失、时间戳解析失败），输出会话级摘要DataFrame。""",

    "T011": """# AI驱动企业合规管理平台 — 投资者路演PPT大纲

**第1页：封面**：公司名 + Logo + 「用AI重新定义企业合规」+ 路演日期

**第2页：执行摘要**：核心问题（合规成本年增23%，人工审核错漏率15%）→ 解决方案（AI实时监控，响应72h→2分钟）→ 牵引力（ARR 4200万，28家500强客户，NPS 71）

**第3页：市场机会**：TAM 420亿（2024）→ 800亿（2028，CAGR 17%）；SAM 150亿；SOM 30亿（金融/制造/医疗）

**第4页：核心痛点**：年均新增监管条文800+；违规罚款均值580万/次；传统软件规则更新周期3-6个月

**第5页：产品展示**：三模块（法规追踪→风险识别→整改方案）；知识图谱3万+法规条文；Demo截图

**第6页：商业模式**：SaaS年费30-200万/企业；毛利率85%（软件）；年签率95%

**第7页：财务数据**：ARR 2024年4200万（+100% YoY）；NDR 138%；客均合同150万；预计2025年ARR 8000万

**第8页：竞争格局**：传统ERP（无AI）vs 国际玩家（不懂中国法规）vs 我们（中文法规理解+垂直知识图谱+数据飞轮）

**第9页：团队**：CEO（前蚂蚁合规总监）/ CTO（前阿里云AI研究员）/ VP Sales（前金蝶）

**第10页：融资计划**：A轮8000万人民币；研发50%/销售35%/运营15%；18个月内ARR 2亿+；当前估值10x ARR""",

    "T016": """# Q1销售数据诊断与行动建议

## 核心问题识别

**结构性矛盾**：以量换价，且高利润市场未规模化
- 客单价-15% + 订单量+32% = 销售额仅+12%（量增价降，边际收益递减）
- 华东：高体量低利润（8%）→ 规模不经济，成本结构存在问题
- 华南：低体量高利润（23%）→ 优质客户模式未被复制

## 三条可执行建议

### ① 停止价格战，推行分层定价（30天内）
将产品拆为标准版/专业版/企业版。停止对低价值客户的一对一服务。
**目标**：Q2客单价环比止跌，华东利润率≥15%

### ② 复制华南高利润客户模式（60天内）
调研华南TOP10客户的行业分布和购买决策路径，在华东专项开拓同类型客户（而非盲目扩大订单量）。
**目标**：Q3华东新签客户中，利润率≥18%的占比达40%

### ③ 改变销售考核：从销售额改为毛利额（下月起）
设置利润率红线：<12%的订单需总监审批。
**目标**：Q2综合利润率从约13%提升至16%+

**风险提示**：政策切换期可能出现订单量短期下滑（预估-10%），需监控客户流失率<5%""",

    "T021": """# 医疗健康App收集用户健康数据合规要求

根据《个人信息保护法》及配套法规，需满足以下要求：

**1. 单独知情同意（PIPL第29条）**
健康数据属于「敏感个人信息」，须取得单独同意（不得与注册条款合并）。同意弹窗必须独立展示、不预先勾选，明确告知：收集目的（个性化推荐）、数据范围、存储期限。用户撤回同意后须立即停止使用。

**2. 最小必要原则（PIPL第6条）**
仅可收集个性化推荐所必需的健康数据，不得过度采集。需形成「数据必要性评估文档」备查，能举证每个字段的必要性。

**3. 隐私政策专项披露（PIPL第17条）**
隐私政策须以显著方式单独标注健康数据处理规则，包括：第三方SDK清单、是否跨境传输、数据保留期限（通常≤2年）。

**4. 数据安全（数安法第27条）**
健康数据须加密存储（AES-256）和传输（TLS 1.2+）；须完成个人信息保护影响评估（PIPIA）；数据泄露72小时内须向网信办报告。

监管依据：国家网信办《个人信息保护合规审计管理办法》（2024年）将上述四点列为医疗健康类App专项检查重点。""",
}

LOW_CANDIDATES = {
    "text_analysis": lambda tid: f"关于这个话题，由于信息有限，很难给出准确分析。建议你查阅权威机构的报告或咨询专业人士，他们能给出更有针对性的建议。总体来说这个领域还在发展中，具体数据需要参考最新资料。",
    "code_generation": lambda tid: f"要实现这个功能，你需要先安装相关库。基本思路是读取数据，然后处理，最后输出结果。具体实现可以参考相关文档，代码逻辑不复杂，主要是按步骤来做就行了。",
    "ppt_generation": lambda tid: f"PPT可以包含以下内容：介绍、主要内容、总结。具体每页的内容需要根据实际情况填充。建议参考专业模板，确保格式美观。",
    "data_analysis": lambda tid: f"从数据来看，存在一些问题需要改善。建议优化相关指标，具体方案需要根据实际情况制定。可以参考行业最佳实践，找专业顾问帮助分析。",
    "rag_qa": lambda tid: f"这个问题涉及专业知识，建议查阅相关文档或咨询专家。不同情况下可能有不同要求，需要根据具体场景判断。总体原则是遵守相关规定，确保合规。",
}


def get_task_type(task: dict) -> str:
    return task["type"]


def generate_candidates(tasks: list[dict]) -> tuple[list[dict], list[dict]]:
    rng = random.Random(42)
    candidates = []
    human_scores = []

    for task in tasks:
        tid = task["task_id"]
        ttype = task["type"]

        # High candidate
        if tid in HIGH_CANDIDATES:
            high_content = HIGH_CANDIDATES[tid]
        else:
            high_content = _generate_generic_high(task)

        # Low candidate
        low_fn = LOW_CANDIDATES.get(ttype, LOW_CANDIDATES["text_analysis"])
        low_content = low_fn(tid)

        for quality, content in [("high", high_content), ("low", low_content)]:
            cid = f"{tid}-{quality[0].upper()}"
            candidates.append({
                "task_id": tid,
                "candidate_id": cid,
                "quality": quality,
                "content": content,
            })

            mean, std = QUALITY_TO_SCORE[quality]
            raw = rng.gauss(mean, std)
            score = max(1.0, min(5.0, raw))
            human_scores.append({
                "candidate_id": cid,
                "task_id": tid,
                "human_score_raw": round(score, 2),
                "human_score_normalized": round((score - 1) / 4.0, 4),
                "quality_label": quality,
            })

    return candidates, human_scores


def _generate_generic_high(task: dict) -> str:
    """Generic high-quality response for tasks without pre-written content."""
    ttype = task["type"]
    t = task["task"]
    if ttype == "text_analysis":
        return f"""# 分析报告

## 核心发现
针对任务需求：{t[:100]}...，本报告基于公开数据和行业资料进行系统分析。

## 主要维度分析
**维度1：现状评估**
当前情况呈现出显著的结构性特征，关键指标显示该领域正处于快速演变阶段，需要从多个视角综合判断。

**维度2：驱动因素**
主要驱动力包括：(1) 政策环境的持续优化；(2) 技术进步带来的效率提升；(3) 市场需求的结构性转变。

**维度3：挑战与风险**
面临的主要挑战：竞争加剧、成本压力、不确定性增加。需建立动态监控机制。

## 前瞻预测
基于当前趋势，预期未来12-18个月内该领域将经历整合期，领先者将通过差异化策略巩固优势。

## 建议
1. 短期：聚焦核心优势，优化资源配置
2. 中期：建立数据能力，提升决策质量
3. 长期：构建生态护城河，形成可持续竞争力"""
    elif ttype == "code_generation":
        return f"""以下是针对任务的完整Python实现：

```python
import asyncio
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

class SolutionHandler:
    \"\"\"
    处理任务：{t[:80]}
    
    特性：
    - 完整异常处理
    - 类型注解
    - 可配置参数
    \"\"\"
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {{}}
        self._initialized = False
    
    def initialize(self) -> None:
        \"\"\"初始化资源。\"\"\"
        # 验证配置
        required = self.config.get('required_fields', [])
        for field in required:
            if field not in self.config:
                raise ValueError(f"缺少必要配置: {{field}}")
        self._initialized = True
        logger.info("初始化完成")
    
    def process(self, data: Any) -> Dict:
        \"\"\"主处理逻辑。\"\"\"
        if not self._initialized:
            raise RuntimeError("请先调用 initialize()")
        
        if data is None:
            raise ValueError("输入数据不能为空")
        
        result = {{
            'status': 'success',
            'processed': True,
            'data': self._transform(data),
        }}
        return result
    
    def _transform(self, data: Any) -> Any:
        \"\"\"数据转换逻辑（根据具体需求实现）。\"\"\"
        return data


if __name__ == '__main__':
    handler = SolutionHandler(config={{'required_fields': []}})
    handler.initialize()
    result = handler.process({{'sample': 'data'}})
    print(f"处理结果: {{result}}")
```

**使用方法**：`python solution.py`

**异常处理**：ValueError（输入无效）、RuntimeError（未初始化）、所有异常均记录日志。"""
    elif ttype == "ppt_generation":
        return f"""# PPT大纲

**第1页：引言**
核心问题陈述，为什么这个主题重要，受众痛点

**第2页：背景与现状**
市场/行业数据支撑，关键趋势，问题规模量化

**第3页：核心解决方案/主题**
3-5个核心要点，每点有具体说明和数据支撑

**第4页：深度展开（一）**
第一个核心主题的详细内容，案例/数据/图表

**第5页：深度展开（二）**
第二个核心主题的详细内容

**第6页：深度展开（三）**
第三个核心主题的详细内容

**第7页：挑战与风险**
潜在问题识别，应对策略

**第8页：实施路径/行动计划**
时间线，关键里程碑，资源需求

**第9页：预期成果与ROI**
量化指标，成功标准，测量方法

**第10页：总结与行动召唤**
核心信息复述，明确下一步行动（日期/负责人）

*每页建议3-5个要点，使用大字体+图表+数据可视化，避免文字堆砌*"""
    elif ttype == "data_analysis":
        return f"""# 数据分析报告

## 核心问题诊断

基于提供数据，识别出以下关键问题：

**问题1（高优先级）**：核心指标偏离正常轨道
数据显示存在系统性问题，需要立即关注。根本原因分析：外部环境变化 + 内部流程效率问题的叠加效应。

**问题2（中优先级）**：区域/部门间存在显著差距
高绩效单元（示范效应）vs 低绩效单元（需要改进）的差距说明有可优化空间。

## 三条可执行建议

**建议1（立即行动，14天内）**：
针对最紧迫问题，实施快速修正措施。
目标指标：[具体KPI]在30天内提升X%
负责人：[角色]，验收日期：[日期]

**建议2（短期，30-60天）**：
系统性改进方案，建立持续监控机制。
预期效果：解决问题2，提升整体效率15-20%

**建议3（中期，60-90天）**：
复制成功经验，在全范围推广高绩效模式。
预期效果：填平高低绩效差距，整体指标达标。

## 风险提示
快速调整期可能出现短期阵痛，建议设置缓冲期和监控指标，避免过度修正。"""
    else:  # rag_qa
        return f"""根据提供的背景信息，回答如下：

**核心回答**：

基于背景资料，该问题的关键要点包括：

**要点1**：根据文档规定，首要条件是满足基本合规要求。具体来说，需要符合以下标准：明确告知用户、取得同意、按规定处理。

**要点2**：在技术实现层面，应当采用安全、可靠的方案。推荐方案A（适合场景X）和方案B（适合场景Y）各有优缺点。

**要点3**：从实际操作角度，建议按照以下步骤实施：
1. 评估现状，识别gap
2. 制定实施计划
3. 分阶段落地
4. 持续监控和优化

**注意事项**：实际执行时需根据具体情况调整，建议咨询专业人士进行最终确认。背景信息提及的关键约束条件必须严格遵守。"""


def main():
    tasks = [json.loads(l) for l in (DATA_DIR / "tasks.jsonl").read_text().splitlines() if l.strip()]
    candidates, human_scores = generate_candidates(tasks)

    (DATA_DIR / "candidates.jsonl").write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in candidates)
    )
    (DATA_DIR / "human_scores.jsonl").write_text(
        "\n".join(json.dumps(h, ensure_ascii=False) for h in human_scores)
    )

    print(f"生成候选：{len(candidates)} 条 → {DATA_DIR / 'candidates.jsonl'}")
    print(f"生成人工评分：{len(human_scores)} 条 → {DATA_DIR / 'human_scores.jsonl'}")
    for h in human_scores:
        q = "H" if h["quality_label"] == "high" else "L"
        print(f"  {h['candidate_id']}: {q} score={h['human_score_raw']:.2f} norm={h['human_score_normalized']:.4f}")


if __name__ == "__main__":
    main()
