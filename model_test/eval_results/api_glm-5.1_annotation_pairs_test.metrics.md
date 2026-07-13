# Prediction Evaluation

## Metadata
- Gold rows: 2805
- Prediction rows: 2805
- Evaluated rows: 2805
- Missing predictions: 0
- Invalid predictions: 0

## Task 1 Opportunity Detection
- Macro-F1: 0.4322

| gold \ pred | No | Yes |
|---|---|---|
| No | 334 | 1503 |
| Yes | 11 | 957 |

## Task 2 Binary Opportunity Detection
- F1: 0.5583
- MCC: 0.2467
- Precision: 0.3890
- Recall: 0.9886
- TP/TN/FP/FN: 957/334/1503/11

## Task 3 Opportunity Score
- Condition: gold has_opportunity == Yes
- Support: 968
- Conditional Score Accuracy: 0.5816
- Score Macro-F1: 0.4232

## Task 4 Role Direction
- Condition: gold has_opportunity == Yes
- Support: 968
- Conditional Direction Accuracy: 0.7180
- Direction Macro-F1: 0.4779

## Task 5 Cooperation Type
- Condition: gold has_opportunity == Yes
- Support: 968
- Conditional Type Macro-F1: 0.4020

| class | F1 |
|---|---:|
| 供应与生产合作 | 0.7906 |
| 营销与分销合作 | 0.5622 |
| 许可与技术转移合作 | 0.1967 |
| 研发与共同开发合作 | 0.5980 |
| 资本与股权合作 | 0.6667 |
| 其他 | 0.0000 |
| None | 0.0000 |

## Task 6 Joint Prediction
- Opportunity + Score + Direction + Type Exact Match: 0.2535
- Exact Match on Gold Positive: 0.3895

## Task 7 Reliability
- Confidence-Accuracy Target: match
- High-confidence Threshold: >= 2
- High-confidence Count: 793
- High-confidence Opportunity Error Rate: 0.2623
- High-confidence Joint Error Rate: 0.4855

| confidence | n | accuracy | errors |
|---:|---:|---:|---:|
| 1 | 2012 | 0.3509 | 1306 |
| 2 | 793 | 0.7377 | 208 |
