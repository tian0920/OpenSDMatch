# Prediction Evaluation

## Metadata
- Gold rows: 2805
- Prediction rows: 2805
- Evaluated rows: 2778
- Missing predictions: 0
- Invalid predictions: 27

## Task 1 Opportunity Detection
- Macro-F1: 0.3462

| gold \ pred | No | Yes |
|---|---|---|
| No | 160 | 1661 |
| Yes | 9 | 948 |

## Task 2 Binary Opportunity Detection
- F1: 0.5317
- MCC: 0.1560
- Precision: 0.3634
- Recall: 0.9906
- TP/TN/FP/FN: 948/160/1661/9

## Task 3 Opportunity Score
- Condition: gold has_opportunity == Yes
- Support: 957
- Conditional Score Accuracy: 0.8788
- Score Macro-F1: 0.5102

## Task 4 Role Direction
- Condition: gold has_opportunity == Yes
- Support: 957
- Conditional Direction Accuracy: 0.6040
- Direction Macro-F1: 0.4134

## Task 5 Cooperation Type
- Condition: gold has_opportunity == Yes
- Support: 957
- Conditional Type Macro-F1: 0.4097

| class | F1 |
|---|---:|
| 供应与生产合作 | 0.8173 |
| 营销与分销合作 | 0.5000 |
| 许可与技术转移合作 | 0.3377 |
| 研发与共同开发合作 | 0.6042 |
| 资本与股权合作 | 0.6087 |
| 其他 | 0.0000 |
| None | 0.0000 |

## Task 6 Joint Prediction
- Opportunity + Score + Direction + Type Exact Match: 0.2091
- Exact Match on Gold Positive: 0.4399

## Task 7 Reliability
- Confidence-Accuracy Target: match
- High-confidence Threshold: >= 2
- High-confidence Count: 2681
- High-confidence Opportunity Error Rate: 0.5886
- High-confidence Joint Error Rate: 0.7833

| confidence | n | accuracy | errors |
|---:|---:|---:|---:|
| 1 | 97 | 0.0515 | 92 |
| 2 | 2681 | 0.4114 | 1578 |
