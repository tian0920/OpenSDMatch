# Prediction Evaluation

## Metadata
- Gold rows: 2805
- Prediction rows: 2805
- Evaluated rows: 2805
- Missing predictions: 0
- Invalid predictions: 0

## Task 1 Opportunity Detection
- Macro-F1: 0.6964

| gold \ pred | No | Yes |
|---|---|---|
| No | 1068 | 769 |
| Yes | 79 | 889 |

## Task 2 Binary Opportunity Detection
- F1: 0.6771
- MCC: 0.4833
- Precision: 0.5362
- Recall: 0.9184
- TP/TN/FP/FN: 889/1068/769/79

## Task 3 Opportunity Score
- Condition: gold has_opportunity == Yes
- Support: 968
- Conditional Score Accuracy: 0.7242
- Score Macro-F1: 0.4674

## Task 4 Role Direction
- Condition: gold has_opportunity == Yes
- Support: 968
- Conditional Direction Accuracy: 0.7273
- Direction Macro-F1: 0.5028

## Task 5 Cooperation Type
- Condition: gold has_opportunity == Yes
- Support: 968
- Conditional Type Macro-F1: 0.4150

| class | F1 |
|---|---:|
| 供应与生产合作 | 0.8307 |
| 营销与分销合作 | 0.5766 |
| 许可与技术转移合作 | 0.0440 |
| 研发与共同开发合作 | 0.6847 |
| 资本与股权合作 | 0.7692 |
| 其他 | 0.0000 |
| None | 0.0000 |

## Task 6 Joint Prediction
- Opportunity + Score + Direction + Type Exact Match: 0.5590
- Exact Match on Gold Positive: 0.5165

## Task 7 Reliability
- Confidence-Accuracy Target: match
- High-confidence Threshold: >= 2
- High-confidence Count: 2596
- High-confidence Opportunity Error Rate: 0.2658
- High-confidence Joint Error Rate: 0.3964

| confidence | n | accuracy | errors |
|---:|---:|---:|---:|
| 1 | 209 | 0.2440 | 158 |
| 2 | 2596 | 0.7342 | 690 |
