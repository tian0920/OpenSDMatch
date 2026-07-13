# Prediction Evaluation

## Metadata
- Gold rows: 2805
- Prediction rows: 2805
- Evaluated rows: 2805
- Missing predictions: 0
- Invalid predictions: 0

## Task 1 Opportunity Detection
- Macro-F1: 0.5378

| gold \ pred | No | Yes |
|---|---|---|
| No | 588 | 1249 |
| Yes | 27 | 941 |

## Task 2 Binary Opportunity Detection
- F1: 0.5959
- MCC: 0.3357
- Precision: 0.4297
- Recall: 0.9721
- TP/TN/FP/FN: 941/588/1249/27

## Task 3 Opportunity Score
- Condition: gold has_opportunity == Yes
- Support: 968
- Conditional Score Accuracy: 0.7521
- Score Macro-F1: 0.5000

## Task 4 Role Direction
- Condition: gold has_opportunity == Yes
- Support: 968
- Conditional Direction Accuracy: 0.6787
- Direction Macro-F1: 0.4490

## Task 5 Cooperation Type
- Condition: gold has_opportunity == Yes
- Support: 968
- Conditional Type Macro-F1: 0.3875

| class | F1 |
|---|---:|
| 供应与生产合作 | 0.8191 |
| 营销与分销合作 | 0.5571 |
| 许可与技术转移合作 | 0.0222 |
| 研发与共同开发合作 | 0.6000 |
| 资本与股权合作 | 0.7143 |
| 其他 | 0.0000 |
| None | 0.0000 |

## Task 6 Joint Prediction
- Opportunity + Score + Direction + Type Exact Match: 0.3722
- Exact Match on Gold Positive: 0.4711

## Task 7 Reliability
- Confidence-Accuracy Target: match
- High-confidence Threshold: >= 2
- High-confidence Count: 1705
- High-confidence Opportunity Error Rate: 0.2686
- High-confidence Joint Error Rate: 0.4328

| confidence | n | accuracy | errors |
|---:|---:|---:|---:|
| 1 | 1100 | 0.2564 | 818 |
| 2 | 1705 | 0.7314 | 458 |
