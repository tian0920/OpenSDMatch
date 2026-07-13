# Prediction Evaluation

## Metadata
- Gold rows: 2805
- Prediction rows: 2805
- Evaluated rows: 27
- Missing predictions: 0
- Invalid predictions: 2778

## Task 1 Opportunity Detection
- Macro-F1: 0.3910

| gold \ pred | No | Yes |
|---|---|---|
| No | 2 | 15 |
| Yes | 0 | 10 |

## Task 2 Binary Opportunity Detection
- F1: 0.5714
- MCC: 0.2169
- Precision: 0.4000
- Recall: 1.0000
- TP/TN/FP/FN: 10/2/15/0

## Task 3 Opportunity Score
- Condition: gold has_opportunity == Yes
- Support: 10
- Conditional Score Accuracy: 0.7000
- Score Macro-F1: 0.4118

## Task 4 Role Direction
- Condition: gold has_opportunity == Yes
- Support: 10
- Conditional Direction Accuracy: 0.6000
- Direction Macro-F1: 0.3590

## Task 5 Cooperation Type
- Condition: gold has_opportunity == Yes
- Support: 10
- Conditional Type Macro-F1: 0.1319

| class | F1 |
|---|---:|
| 供应与生产合作 | 0.9231 |
| 营销与分销合作 | 0.0000 |
| 许可与技术转移合作 | 0.0000 |
| 研发与共同开发合作 | 0.0000 |
| 资本与股权合作 | 0.0000 |
| 其他 | 0.0000 |
| None | 0.0000 |

## Task 6 Joint Prediction
- Opportunity + Score + Direction + Type Exact Match: 0.2222
- Exact Match on Gold Positive: 0.4000

## Task 7 Reliability
- Confidence-Accuracy Target: match
- High-confidence Threshold: >= 2
- High-confidence Count: 17
- High-confidence Opportunity Error Rate: 0.4706
- High-confidence Joint Error Rate: 0.6471

| confidence | n | accuracy | errors |
|---:|---:|---:|---:|
| 1 | 10 | 0.3000 | 7 |
| 2 | 17 | 0.5294 | 8 |
