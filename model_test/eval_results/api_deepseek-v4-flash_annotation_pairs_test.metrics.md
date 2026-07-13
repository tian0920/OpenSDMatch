# Prediction Evaluation

## Metadata
- Gold rows: 2805
- Prediction rows: 2805
- Evaluated rows: 2805
- Missing predictions: 0
- Invalid predictions: 0

## Task 1 Opportunity Detection
- Macro-F1: 0.5081

| gold \ pred | No | Yes |
|---|---|---|
| No | 521 | 1316 |
| Yes | 34 | 934 |

## Task 2 Binary Opportunity Detection
- F1: 0.5805
- MCC: 0.2965
- Precision: 0.4151
- Recall: 0.9649
- TP/TN/FP/FN: 934/521/1316/34

## Task 3 Opportunity Score
- Condition: gold has_opportunity == Yes
- Support: 968
- Conditional Score Accuracy: 0.7448
- Score Macro-F1: 0.4802

## Task 4 Role Direction
- Condition: gold has_opportunity == Yes
- Support: 968
- Conditional Direction Accuracy: 0.7097
- Direction Macro-F1: 0.4798

## Task 5 Cooperation Type
- Condition: gold has_opportunity == Yes
- Support: 968
- Conditional Type Macro-F1: 0.3593

| class | F1 |
|---|---:|
| 供应与生产合作 | 0.8108 |
| 营销与分销合作 | 0.5503 |
| 许可与技术转移合作 | 0.0000 |
| 研发与共同开发合作 | 0.6320 |
| 资本与股权合作 | 0.5217 |
| 其他 | 0.0000 |
| None | 0.0000 |

## Task 6 Joint Prediction
- Opportunity + Score + Direction + Type Exact Match: 0.3561
- Exact Match on Gold Positive: 0.4938

## Task 7 Reliability
- Confidence-Accuracy Target: match
- High-confidence Threshold: >= 2
- High-confidence Count: 1872
- High-confidence Opportunity Error Rate: 0.4263
- High-confidence Joint Error Rate: 0.5641

| confidence | n | accuracy | errors |
|---:|---:|---:|---:|
| 1 | 933 | 0.4084 | 552 |
| 2 | 1872 | 0.5737 | 798 |
