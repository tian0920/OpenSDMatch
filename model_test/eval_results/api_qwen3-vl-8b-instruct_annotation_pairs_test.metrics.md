# Prediction Evaluation

## Metadata
- Gold rows: 2805
- Prediction rows: 2805
- Evaluated rows: 2776
- Missing predictions: 0
- Invalid predictions: 29

## Task 1 Opportunity Detection
- Macro-F1: 0.4469

| gold \ pred | No | Yes |
|---|---|---|
| No | 368 | 1446 |
| Yes | 25 | 937 |

## Task 2 Binary Opportunity Detection
- F1: 0.5602
- MCC: 0.2414
- Precision: 0.3932
- Recall: 0.9740
- TP/TN/FP/FN: 937/368/1446/25

## Task 3 Opportunity Score
- Condition: gold has_opportunity == Yes
- Support: 962
- Conditional Score Accuracy: 0.6123
- Score Macro-F1: 0.4196

## Task 4 Role Direction
- Condition: gold has_opportunity == Yes
- Support: 962
- Conditional Direction Accuracy: 0.6850
- Direction Macro-F1: 0.4111

## Task 5 Cooperation Type
- Condition: gold has_opportunity == Yes
- Support: 962
- Conditional Type Macro-F1: 0.2869

| class | F1 |
|---|---:|
| 供应与生产合作 | 0.7948 |
| 营销与分销合作 | 0.4632 |
| 许可与技术转移合作 | 0.0440 |
| 研发与共同开发合作 | 0.2517 |
| 资本与股权合作 | 0.4545 |
| 其他 | 0.0000 |
| None | 0.0000 |

## Task 6 Joint Prediction
- Opportunity + Score + Direction + Type Exact Match: 0.2644
- Exact Match on Gold Positive: 0.3805

## Task 7 Reliability
- Confidence-Accuracy Target: match
- High-confidence Threshold: >= 2
- High-confidence Count: 2775
- High-confidence Opportunity Error Rate: 0.5301
- High-confidence Joint Error Rate: 0.7359

| confidence | n | accuracy | errors |
|---:|---:|---:|---:|
| 1 | 1 | 1.0000 | 0 |
| 2 | 2775 | 0.4699 | 1471 |
