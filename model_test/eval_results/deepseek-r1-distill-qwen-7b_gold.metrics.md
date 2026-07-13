# Prediction Evaluation

## Metadata
- Gold rows: 148
- Prediction rows: 148
- Evaluated rows: 0
- Missing predictions: 0
- Invalid predictions: 148

## Task 1 Match Classification
- Macro-F1: 0.0000
- Quadratic Weighted Kappa: 0.0000

| gold \ pred | 0 | 1 | 2 |
|---|---|---|---|
| 0 | 0 | 0 | 0 |
| 1 | 0 | 0 | 0 |
| 2 | 0 | 0 | 0 |

## Task 2 Binary Match Detection
- F1: 0.0000
- MCC: 0.0000
- Precision: 0.0000
- Recall: 0.0000
- TP/TN/FP/FN: 0/0/0/0

## Task 3 Direction Reasoning
- Condition: gold label_match in {1, 2}
- Support: 0
- Conditional Direction Accuracy: 0.0000
- Direction Macro-F1: 0.0000

## Task 4 Cooperation Type Prediction
- Condition: gold label_match in {1, 2}
- Support: 0
- Conditional Type Macro-F1: 0.0000

| class | F1 |
|---|---:|
| 采购/销售 | 0.0000 |
| 渠道合作 | 0.0000 |
| 技术服务 | 0.0000 |
| 联合研发 | 0.0000 |
| 资源对接 | 0.0000 |
| 投融资 | 0.0000 |
| 招商合作 | 0.0000 |
| 其他 | 0.0000 |
| 不匹配 | 0.0000 |

## Task 5 Joint Prediction
- Match + Direction + Type Exact Match: 0.0000
- Exact Match on Gold Positive: 0.0000

## Task 6 Reliability
- Confidence-Accuracy Target: match
- High-confidence Threshold: >= 4
- High-confidence Count: 0
- High-confidence Match Error Rate: 0.0000
- High-confidence Joint Error Rate: 0.0000

| confidence | n | accuracy | errors |
|---:|---:|---:|---:|
| 1 | 0 | 0.0000 | 0 |
| 2 | 0 | 0.0000 | 0 |
| 3 | 0 | 0.0000 | 0 |
| 4 | 0 | 0.0000 | 0 |
| 5 | 0 | 0.0000 | 0 |
