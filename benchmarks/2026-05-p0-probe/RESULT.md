# P0 探针结果

> 日期：2026-05-08 15:10  
> 样本：5 tasks × 4 candidates = 20  
> 模型：gpt-4o-mini (yunwu.ai proxy)  

## Go/No-Go 检查

| 检查项 | 结果 |
|--------|------|
| 零崩溃 | ✅ PASS |
| 格式正确 | ✅ PASS |
| 方向性正确 (avg_high > avg_bad) | ✅ PASS avg_high=0.884 avg_bad=0.372 |
| 成本≤¥30 | ✅ PASS ¥0.05 |
| **综合结论** | **✅ P0 PASS → 进入 P1** |

## 分数分布

| 候选ID | 质量 | Score | Phase | Depth | 用时(s) |
|--------|------|-------|-------|-------|---------|
| T001-H | high | 0.915 | executing | standard | 9.35 |
| T001-M | mid | 0.773 | executing | standard | 6.09 |
| T001-L | low | 0.365 | executing | standard | 6.61 |
| T001-B | bad | 0.280 | executing | standard | 7.58 |
| T002-H | high | 0.727 | executing | standard | 7.67 |
| T002-M | mid | 0.709 | executing | standard | 6.08 |
| T002-L | low | 0.472 | executing | standard | 6.76 |
| T002-B | bad | 0.083 | executing | standard | 9.66 |
| T003-H | high | 0.917 | executing | standard | 5.47 |
| T003-M | mid | 0.778 | executing | standard | 5.78 |
| T003-L | low | 0.472 | executing | standard | 6.45 |
| T003-B | bad | 0.333 | executing | standard | 5.54 |
| T004-H | high | 0.860 | executing | standard | 5.44 |
| T004-M | mid | 0.918 | executing | standard | 7.23 |
| T004-L | low | 0.553 | executing | standard | 7.65 |
| T004-B | bad | 0.603 | executing | standard | 6.59 |
| T005-H | high | 1.000 | executing | standard | 6.23 |
| T005-M | mid | 1.000 | executing | standard | 6.38 |
| T005-L | low | 0.478 | executing | standard | 6.35 |
| T005-B | bad | 0.561 | executing | standard | 6.84 |
