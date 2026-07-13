# Prediction Evaluation

## Metadata
- Gold rows: 2805
- Prediction rows: 2805
- Evaluated rows: 2804
- Missing predictions: 0
- Invalid predictions: 1

## Task 1 Opportunity Detection
- Macro-F1: 0.5605

| gold \ pred | No | Yes |
|---|---|---|
| No | 641 | 1195 |
| Yes | 23 | 945 |

## Task 2 Binary Opportunity Detection
- F1: 0.6081
- MCC: 0.3639
- Precision: 0.4416
- Recall: 0.9762
- TP/TN/FP/FN: 945/641/1195/23

## Task 3 Opportunity Score
- Condition: gold has_opportunity == Yes
- Support: 968
- Conditional Score Accuracy: 0.7562
- Score Macro-F1: 0.4804

## Task 4 Role Direction
- Condition: gold has_opportunity == Yes
- Support: 968
- Conditional Direction Accuracy: 0.6890
- Direction Macro-F1: 0.4754

## Task 5 Cooperation Type
- Condition: gold has_opportunity == Yes
- Support: 968
- Conditional Type Macro-F1: 0.3895

| class | F1 |
|---|---:|
| 供应与生产合作 | 0.8331 |
| 营销与分销合作 | 0.5455 |
| 许可与技术转移合作 | 0.0000 |
| 研发与共同开发合作 | 0.6555 |
| 资本与股权合作 | 0.6923 |
| 其他 | 0.0000 |
| None | 0.0000 |

## Task 6 Joint Prediction
- Opportunity + Score + Direction + Type Exact Match: 0.4023
- Exact Match on Gold Positive: 0.5031

## Task 7 Reliability
- Confidence-Accuracy Target: match
- High-confidence Threshold: >= 2
- High-confidence Count: 2736
- High-confidence Opportunity Error Rate: 0.4269
- High-confidence Joint Error Rate: 0.5906

| confidence | n | accuracy | errors |
|---:|---:|---:|---:|
| 1 | 68 | 0.2647 | 50 |
| 2 | 2736 | 0.5731 | 1168 |
