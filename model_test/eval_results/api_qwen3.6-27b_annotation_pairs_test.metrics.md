# Prediction Evaluation

## Metadata
- Gold rows: 2805
- Prediction rows: 2805
- Evaluated rows: 2805
- Missing predictions: 0
- Invalid predictions: 0

## Task 1 Opportunity Detection
- Macro-F1: 0.7451

| gold \ pred | No | Yes |
|---|---|---|
| No | 1290 | 547 |
| Yes | 148 | 820 |

## Task 2 Binary Opportunity Detection
- F1: 0.7024
- MCC: 0.5225
- Precision: 0.5999
- Recall: 0.8471
- TP/TN/FP/FN: 820/1290/547/148

## Task 3 Opportunity Score
- Condition: gold has_opportunity == Yes
- Support: 968
- Conditional Score Accuracy: 0.6467
- Score Macro-F1: 0.4462

## Task 4 Role Direction
- Condition: gold has_opportunity == Yes
- Support: 968
- Conditional Direction Accuracy: 0.6395
- Direction Macro-F1: 0.4208

## Task 5 Cooperation Type
- Condition: gold has_opportunity == Yes
- Support: 968
- Conditional Type Macro-F1: 0.3646

| class | F1 |
|---|---:|
| 供应与生产合作 | 0.8078 |
| 营销与分销合作 | 0.5427 |
| 许可与技术转移合作 | 0.0227 |
| 研发与共同开发合作 | 0.4098 |
| 资本与股权合作 | 0.7692 |
| 其他 | 0.0000 |
| None | 0.0000 |

## Task 6 Joint Prediction
- Opportunity + Score + Direction + Type Exact Match: 0.6157
- Exact Match on Gold Positive: 0.4514

## Task 7 Reliability
- Confidence-Accuracy Target: match
- High-confidence Threshold: >= 2
- High-confidence Count: 2530
- High-confidence Opportunity Error Rate: 0.2087
- High-confidence Joint Error Rate: 0.3186

| confidence | n | accuracy | errors |
|---:|---:|---:|---:|
| 1 | 275 | 0.3927 | 167 |
| 2 | 2530 | 0.7913 | 528 |
