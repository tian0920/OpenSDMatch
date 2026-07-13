# 供需合作匹配主题表

这些表由清洗后的 CSV 二次合并生成，用于集中分析供给、需求、合作对象和匹配关系。

## 输出文件
- `sd_objects.csv`：20,706 行。一行一个被 AI 解析过的对象，含供给标签、需求标签、合作对象标签、关键词。
- `sd_tags_long.csv`：75,403 行。一行一个标签，适合做标签频次、供需侧对比、透视表。
- `user_sd_profiles.csv`：31,680 行。一行一个用户，聚合用户供给/需求标签，并补充基础画像字段。
- `opportunities_enriched.csv`：7,400 行。一行一个商机，补充发布者画像和 AI 解析出的供需标签。
- `company_sd_profiles.csv`：3,230 行。一行一个公司/机构，含主营业务、行业、供给词、需求词。
- `cooperation_edges.csv`：71,548 行。统一的合作/匹配边表，整合公司供应链匹配、用户匹配报告、合作邀请。

## 建议用法
- 看标签供需结构：从 `sd_tags_long.csv` 按 `tag_side/primary_tag/secondary_tag/normalized_tag` 透视。
- 看单个用户供需画像：查 `user_sd_profiles.csv`。
- 看商机质量和方向：查 `opportunities_enriched.csv` 的 `validity/direction/cooperation_method`。
- 看公司间潜在合作：按 `cooperation_edges.csv` 中 `edge_type=company_supply_chain_match` 和 `score` 排序。
- 看系统已有匹配结果：按 `edge_type=user_match_report` 查看 `raw_json` 和 `reason/action_plan`。
