# 用户合并结果说明

- 合并用户数：34,085
- 涉及来源表数量：13

## 来源表覆盖
- t_user：33,662 个用户
- t_user_stat：25,627 个用户
- t_user_external：25,625 个用户
- t_user_jobs：19,585 个用户
- t_user_city：19,487 个用户
- t_user_city_wx：18,593 个用户
- t_ai_tag_index：7,366 个用户
- es_opportunities：6,842 个用户
- t_user_accessory：1,652 个用户
- t_user_info_setting：1,216 个用户
- es_contacts：174 个用户
- t_user_education：13 个用户
- es_business_match_reports：12 个用户

## 合并策略
- `t_user`、`t_user_external`、城市表取同一用户最新/非空信息作为主列。
- `t_user_jobs`、教育、ES 联系人、商机、匹配报告等一对多信息写入 JSON 列，并保留 count。
- `t_user_accessory`、`t_user_info_setting`、`t_user_stat` 按 key-value 透视成若干列，同时保留完整 JSON。
- AI 标签从 `t_ai_tag_index` 聚合为热门标签、标签计数和供需侧统计。
