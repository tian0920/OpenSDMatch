# Prediction Evaluation

## Metadata
- Gold rows: 2805
- Prediction rows: 2805
- Evaluated rows: 2779
- Missing predictions: 0
- Invalid predictions: 26

## Task 1 Opportunity Detection
- Macro-F1: 0.3780

| gold \ pred | No | Yes |
|---|---|---|
| No | 237 | 1582 |
| Yes | 43 | 917 |

## Task 2 Binary Opportunity Detection
- F1: 0.5302
- MCC: 0.1351
- Precision: 0.3669
- Recall: 0.9552
- TP/TN/FP/FN: 917/237/1582/43

## Task 3 Opportunity Score
- Condition: gold has_opportunity == Yes
- Support: 960
- Conditional Score Accuracy: 0.7917
- Score Macro-F1: 0.4662

## Task 4 Role Direction
- Condition: gold has_opportunity == Yes
- Support: 960
- Conditional Direction Accuracy: 0.3927
- Direction Macro-F1: 0.2734

## Task 5 Cooperation Type
- Condition: gold has_opportunity == Yes
- Support: 960
- Conditional Type Macro-F1: 0.2273

| class | F1 |
|---|---:|
| 供应与生产合作 | 0.4015 |
| 营销与分销合作 | 0.2993 |
| 许可与技术转移合作 | 0.0385 |
| 研发与共同开发合作 | 0.3522 |
| 资本与股权合作 | 0.5000 |
| 其他 | 0.0000 |
| None | 0.0000 |

## Task 6 Joint Prediction
- Opportunity + Score + Direction + Type Exact Match: 0.1310
- Exact Match on Gold Positive: 0.1323

## Task 7 Reliability
- Confidence-Accuracy Target: match
- High-confidence Threshold: >= 2
- High-confidence Count: 2184
- High-confidence Opportunity Error Rate: 0.6168
- High-confidence Joint Error Rate: 0.9418

| confidence | n | accuracy | errors |
|---:|---:|---:|---:|
| 1 | 493 | 0.4726 | 260 |
| 2 | 2184 | 0.3832 | 1347 |
