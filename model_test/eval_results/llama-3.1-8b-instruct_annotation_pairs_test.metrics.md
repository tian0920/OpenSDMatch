# Prediction Evaluation

## Metadata
- Gold rows: 2805
- Prediction rows: 2805
- Evaluated rows: 2805
- Missing predictions: 0
- Invalid predictions: 0

## Task 1 Opportunity Detection
- Macro-F1: 0.3650

| gold \ pred | No | Yes |
|---|---|---|
| No | 197 | 1640 |
| Yes | 10 | 958 |

## Task 2 Binary Opportunity Detection
- F1: 0.5373
- MCC: 0.1762
- Precision: 0.3687
- Recall: 0.9897
- TP/TN/FP/FN: 958/197/1640/10

## Task 3 Opportunity Score
- Condition: gold has_opportunity == Yes
- Support: 968
- Conditional Score Accuracy: 0.7748
- Score Macro-F1: 0.4593

## Task 4 Role Direction
- Condition: gold has_opportunity == Yes
- Support: 968
- Conditional Direction Accuracy: 0.6756
- Direction Macro-F1: 0.3918

## Task 5 Cooperation Type
- Condition: gold has_opportunity == Yes
- Support: 968
- Conditional Type Macro-F1: 0.3055

| class | F1 |
|---|---:|
| 供应与生产合作 | 0.7519 |
| 营销与分销合作 | 0.3601 |
| 许可与技术转移合作 | 0.0992 |
| 研发与共同开发合作 | 0.5464 |
| 资本与股权合作 | 0.3810 |
| 其他 | 0.0000 |
| None | 0.0000 |

## Task 6 Joint Prediction
- Opportunity + Score + Direction + Type Exact Match: 0.2225
- Exact Match on Gold Positive: 0.4411

## Task 7 Reliability
- Confidence-Accuracy Target: match
- High-confidence Threshold: >= 2
- High-confidence Count: 2598
- High-confidence Opportunity Error Rate: 0.6313
- High-confidence Joint Error Rate: 0.8356

| confidence | n | accuracy | errors |
|---:|---:|---:|---:|
| 1 | 205 | 0.9512 | 10 |
| 2 | 2598 | 0.3687 | 1640 |
