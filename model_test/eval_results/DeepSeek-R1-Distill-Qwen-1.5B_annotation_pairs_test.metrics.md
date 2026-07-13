# Prediction Evaluation

## Metadata
- Gold rows: 2805
- Prediction rows: 2805
- Evaluated rows: 2736
- Missing predictions: 0
- Invalid predictions: 69

## Task 1 Opportunity Detection
- Macro-F1: 0.4482

| gold \ pred | No | Yes |
|---|---|---|
| No | 721 | 1071 |
| Yes | 430 | 514 |

## Task 2 Binary Opportunity Detection
- F1: 0.4065
- MCC: -0.0512
- Precision: 0.3243
- Recall: 0.5445
- TP/TN/FP/FN: 514/721/1071/430

## Task 3 Opportunity Score
- Condition: gold has_opportunity == Yes
- Support: 944
- Conditional Score Accuracy: 0.5106
- Score Macro-F1: 0.3409

## Task 4 Role Direction
- Condition: gold has_opportunity == Yes
- Support: 944
- Conditional Direction Accuracy: 0.1218
- Direction Macro-F1: 0.1055

## Task 5 Cooperation Type
- Condition: gold has_opportunity == Yes
- Support: 944
- Conditional Type Macro-F1: 0.1013

| class | F1 |
|---|---:|
| 供应与生产合作 | 0.1560 |
| 营销与分销合作 | 0.1756 |
| 许可与技术转移合作 | 0.1220 |
| 研发与共同开发合作 | 0.2558 |
| 资本与股权合作 | 0.0000 |
| 其他 | 0.0000 |
| None | 0.0000 |

## Task 6 Joint Prediction
- Opportunity + Score + Direction + Type Exact Match: 0.2712
- Exact Match on Gold Positive: 0.0222

## Task 7 Reliability
- Confidence-Accuracy Target: match
- High-confidence Threshold: >= 2
- High-confidence Count: 1577
- High-confidence Opportunity Error Rate: 0.6753
- High-confidence Joint Error Rate: 0.9816

| confidence | n | accuracy | errors |
|---:|---:|---:|---:|
| 1 | 263 | 0.5437 | 120 |
| 2 | 1577 | 0.3247 | 1065 |
