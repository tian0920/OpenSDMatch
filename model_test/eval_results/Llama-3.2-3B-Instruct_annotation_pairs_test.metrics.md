# Prediction Evaluation

## Metadata
- Gold rows: 2805
- Prediction rows: 2805
- Evaluated rows: 2792
- Missing predictions: 0
- Invalid predictions: 13

## Task 1 Opportunity Detection
- Macro-F1: 0.2573

| gold \ pred | No | Yes |
|---|---|---|
| No | 1 | 1827 |
| Yes | 0 | 964 |

## Task 2 Binary Opportunity Detection
- F1: 0.5134
- MCC: 0.0137
- Precision: 0.3454
- Recall: 1.0000
- TP/TN/FP/FN: 964/1/1827/0

## Task 3 Opportunity Score
- Condition: gold has_opportunity == Yes
- Support: 964
- Conditional Score Accuracy: 0.5363
- Score Macro-F1: 0.3792

## Task 4 Role Direction
- Condition: gold has_opportunity == Yes
- Support: 964
- Conditional Direction Accuracy: 0.3807
- Direction Macro-F1: 0.1914

## Task 5 Cooperation Type
- Condition: gold has_opportunity == Yes
- Support: 964
- Conditional Type Macro-F1: 0.1033

| class | F1 |
|---|---:|
| 供应与生产合作 | 0.7231 |
| 营销与分销合作 | 0.0000 |
| 许可与技术转移合作 | 0.0000 |
| 研发与共同开发合作 | 0.0000 |
| 资本与股权合作 | 0.0000 |
| 其他 | 0.0000 |
| None | 0.0000 |

## Task 6 Joint Prediction
- Opportunity + Score + Direction + Type Exact Match: 0.0602
- Exact Match on Gold Positive: 0.1732

## Task 7 Reliability
- Confidence-Accuracy Target: match
- High-confidence Threshold: >= 2
- High-confidence Count: 2384
- High-confidence Opportunity Error Rate: 0.6174
- High-confidence Joint Error Rate: 0.9299

| confidence | n | accuracy | errors |
|---:|---:|---:|---:|
| 1 | 408 | 0.1299 | 355 |
| 2 | 2384 | 0.3826 | 1472 |
