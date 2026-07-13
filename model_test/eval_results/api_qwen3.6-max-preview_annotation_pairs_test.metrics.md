# Prediction Evaluation

## Metadata
- Gold rows: 2805
- Prediction rows: 2805
- Evaluated rows: 2805
- Missing predictions: 0
- Invalid predictions: 0

## Task 1 Opportunity Detection
- Macro-F1: 0.7025

| gold \ pred | No | Yes |
|---|---|---|
| No | 1111 | 726 |
| Yes | 102 | 866 |

## Task 2 Binary Opportunity Detection
- F1: 0.6766
- MCC: 0.4792
- Precision: 0.5440
- Recall: 0.8946
- TP/TN/FP/FN: 866/1111/726/102

## Task 3 Opportunity Score
- Condition: gold has_opportunity == Yes
- Support: 968
- Conditional Score Accuracy: 0.7634
- Score Macro-F1: 0.4987

## Task 4 Role Direction
- Condition: gold has_opportunity == Yes
- Support: 968
- Conditional Direction Accuracy: 0.6839
- Direction Macro-F1: 0.4396

## Task 5 Cooperation Type
- Condition: gold has_opportunity == Yes
- Support: 968
- Conditional Type Macro-F1: 0.3712

| class | F1 |
|---|---:|
| 供应与生产合作 | 0.8388 |
| 营销与分销合作 | 0.5546 |
| 许可与技术转移合作 | 0.1429 |
| 研发与共同开发合作 | 0.4535 |
| 资本与股权合作 | 0.6087 |
| 其他 | 0.0000 |
| None | 0.0000 |

## Task 6 Joint Prediction
- Opportunity + Score + Direction + Type Exact Match: 0.5765
- Exact Match on Gold Positive: 0.5227

## Task 7 Reliability
- Confidence-Accuracy Target: match
- High-confidence Threshold: >= 2
- High-confidence Count: 2420
- High-confidence Opportunity Error Rate: 0.2364
- High-confidence Joint Error Rate: 0.3459

| confidence | n | accuracy | errors |
|---:|---:|---:|---:|
| 1 | 385 | 0.3351 | 256 |
| 2 | 2420 | 0.7636 | 572 |
