# Prediction Evaluation

## Metadata
- Gold rows: 2805
- Prediction rows: 2805
- Evaluated rows: 2708
- Missing predictions: 0
- Invalid predictions: 97

## Task 1 Opportunity Detection
- Macro-F1: 0.5234

| gold \ pred | No | Yes |
|---|---|---|
| No | 534 | 1229 |
| Yes | 37 | 908 |

## Task 2 Binary Opportunity Detection
- F1: 0.5892
- MCC: 0.3082
- Precision: 0.4249
- Recall: 0.9608
- TP/TN/FP/FN: 908/534/1229/37

## Task 3 Opportunity Score
- Condition: gold has_opportunity == Yes
- Support: 945
- Conditional Score Accuracy: 0.7164
- Score Macro-F1: 0.4701

## Task 4 Role Direction
- Condition: gold has_opportunity == Yes
- Support: 945
- Conditional Direction Accuracy: 0.7079
- Direction Macro-F1: 0.3967

## Task 5 Cooperation Type
- Condition: gold has_opportunity == Yes
- Support: 945
- Conditional Type Macro-F1: 0.3457

| class | F1 |
|---|---:|
| 供应与生产合作 | 0.8537 |
| 营销与分销合作 | 0.5841 |
| 许可与技术转移合作 | 0.1031 |
| 研发与共同开发合作 | 0.2424 |
| 资本与股权合作 | 0.6364 |
| 其他 | 0.0000 |
| None | 0.0000 |

## Task 6 Joint Prediction
- Opportunity + Score + Direction + Type Exact Match: 0.3674
- Exact Match on Gold Positive: 0.4878

## Task 7 Reliability
- Confidence-Accuracy Target: match
- High-confidence Threshold: >= 2
- High-confidence Count: 1956
- High-confidence Opportunity Error Rate: 0.4657
- High-confidence Joint Error Rate: 0.6687

| confidence | n | accuracy | errors |
|---:|---:|---:|---:|
| 1 | 752 | 0.5279 | 355 |
| 2 | 1956 | 0.5343 | 911 |
