# APP 导出数据初步清洗与分析报告

## 总览
- 文件表数量：475
- 分析范围：全量
- 总业务行数（按各导出表累加）：4,740,199
- 处理建议：drop_duplicate_export=5；drop_empty=225；drop_irrelevant=19；keep=215；review_duplicate_export=5；review_irrelevant=6

## 主要信息和维度
- 企业/机构：约 2,498,541 行
- 其他：约 1,227,372 行
- 用户/联系人：约 821,913 行
- 商机/供需/业务：约 502,527 行
- 系统/权限/配置：约 235,991 行
- AI标签：约 200,806 行
- 内容/互动：约 155,811 行

## 最大的 20 张表
- t_company：1,048,575 行，4 列，来源 prod_all_tables_export_20260606_205622.zip
- t_id_generator：1,048,575 行，1 列，来源 prod_all_tables_export_20260606_205622.zip
- t_company：1,048,575 行，4 列，来源 prod_extra_tables_export_20260606_195530.zip
- t_user_stat：332,095 行，7 列，来源 prod_all_tables_export_20260606_205622.zip
- t_enterprise：115,940 行，23 列，来源 prod_all_tables_export_20260606_205622.zip
- t_enterprise：115,940 行，23 列，来源 prod_extra_tables_export_20260606_195530.zip
- t_department：88,156 行，3 列，来源 prod_all_tables_export_20260606_205622.zip
- t_ai_tag_index：79,172 行，12 列，来源 prod_all_tables_export_20260606_205622.zip
- t_ai_tag_index：79,172 行，12 列，来源 t_ai_tag_result_20260606_172444.zip
- t_supply_chain_relation：71,050 行，7 列，来源 prod_all_tables_export_20260606_205622.zip
- t_unit_entity_name_map：55,631 行，6 列，来源 prod_all_tables_export_20260606_205622.zip
- t_friend：51,611 行，19 列，来源 prod_all_tables_export_20260606_205622.zip
- t_user_messages_79：43,620 行，10 列，来源 prod_all_tables_export_20260606_205622.zip
- t_friend_request：35,905 行，9 列，来源 prod_all_tables_export_20260606_205622.zip
- t_user：33,662 行，20 列，来源 prod_all_tables_export_20260606_205622.zip
- t_unit_mention：27,934 行，7 列，来源 prod_all_tables_export_20260606_205622.zip
- t_user_phone：25,643 行，7 列，来源 prod_all_tables_export_20260606_205622.zip
- t_user_external：25,625 行，57 列，来源 prod_all_tables_export_20260606_205622.zip
- t_user_external：25,625 行，57 列，来源 prod_extra_tables_export_20260606_195530.zip
- t_user_external_backup：24,085 行，57 列，来源 prod_all_tables_export_20260606_205622.zip

## 建议删除或复核的数据
- drop_empty：225 张表
- keep：215 张表
- drop_irrelevant：19 张表
- review_irrelevant：6 张表
- drop_duplicate_export：5 张表
- review_duplicate_export：5 张表

详见 `cleanup_recommendations.csv`。

## 重复数据提示
- t_ai_tag_index / prod_all_tables_export_20260606_205622.zip：表内完全重复 0 行，业务键重复 3769 行，建议=keep
- t_company / prod_all_tables_export_20260606_205622.zip：表内完全重复 0 行，业务键重复 1 行，建议=keep
- t_user_external_backup / prod_all_tables_export_20260606_205622.zip：表内完全重复 0 行，业务键重复 8 行，建议=keep
- t_company / prod_extra_tables_export_20260606_195530.zip：表内完全重复 0 行，业务键重复 1 行，建议=drop_duplicate_export
- t_user_accessory / prod_extra_tables_export_20260606_195530.zip：表内完全重复 0 行，业务键重复 0 行，建议=review_duplicate_export
- t_user_external / prod_extra_tables_export_20260606_195530.zip：表内完全重复 0 行，业务键重复 0 行，建议=review_duplicate_export
- t_user_info_setting / prod_extra_tables_export_20260606_195530.zip：表内完全重复 0 行，业务键重复 0 行，建议=drop_duplicate_export
- t_user_jobs / prod_extra_tables_export_20260606_195530.zip：表内完全重复 0 行，业务键重复 0 行，建议=review_duplicate_export
- t_enterprise / prod_extra_tables_export_20260606_195530.zip：表内完全重复 0 行，业务键重复 0 行，建议=review_duplicate_export
- t_ai_tag_candidate / t_ai_tag_result_20260606_172444.zip：表内完全重复 0 行，业务键重复 0 行，建议=drop_duplicate_export
- t_ai_tag_index / t_ai_tag_result_20260606_172444.zip：表内完全重复 0 行，业务键重复 3769 行，建议=drop_duplicate_export
- t_ai_tag_result / t_ai_tag_result_20260606_172444.zip：表内完全重复 0 行，业务键重复 0 行，建议=drop_duplicate_export
- t_unit_entity / t_ai_tag_result_20260606_172444.zip：表内完全重复 0 行，业务键重复 0 行，建议=review_duplicate_export

## 敏感字段提示
- conference：password
- pc_session：token
- phone_code_record：mobile
- shiro_session：session_id, session_data
- sys_dept：phone, email, user_mobile
- sys_user：password, salt, email, mobile
- sys_user_token：token
- t_corporation_info：wechat_no, wechat_qr_code, contact_mobile
- t_device：_token
- t_domain：_email, _tel
- t_enterprise：tel, email
- t_mobile_record：mobile
- t_openinstall_statistic_info：inviter_mobile
- t_order_address：phone_encrypted
- t_org_application：mobile
- t_sidonghui：phone
- t_unit_entity：contact_phone
- t_user：_mobile, _email, _salt
- t_user_address：phone_encrypted
- t_user_external：is_add_mobile, is_add_qr_code, is_show_mobile, email, user_mobile, id_card
- t_user_external_backup：is_add_mobile, is_add_qr_code, is_show_mobile, email, user_mobile, id_card
- t_user_patch：is_add_mobile, is_add_qr_code, is_show_mobile, email, dial_mobile
- t_user_phone：phone_encrypted
- t_user_session：_token, _voip_token, _phone_name
- user_password：password, salt
- wx_account：token
- wx_user：phone, qr_scene_str
- es_contacts：email, mobile, phone, wechat
- t_corporation_info：wechat_no, wechat_qr_code, contact_mobile
- t_user_external：is_add_mobile, is_add_qr_code, is_show_mobile, email, user_mobile, id_card
- t_enterprise：tel, email
- t_unit_entity：contact_phone

## 使用建议
- 原始 zip 不会被修改。
- 先查看 `table_inventory.csv` 和 `cleanup_recommendations.csv`，确认 drop/review 规则是否符合你的业务目标。
- 如需导出清洗后的 CSV，重新运行脚本并加上 `--export-cleaned`。
