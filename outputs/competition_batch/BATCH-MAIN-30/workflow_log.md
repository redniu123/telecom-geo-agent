# 片区通信设施批量接入设计运行日志

- batch_id: `BATCH-MAIN-30`
- dataset_id: `osm_shanghai_public_background_synthetic_batch_v1`
- parameter_fingerprint: `5dd5fa22c9e3bf73c83344d444eed98fee59fa470f5692decdf459ceec91b9dd`
- sorting_rule: `priority(high>medium>low),task_id(ascending)`
- terminal_counts: `{"completed_direct": 19, "completed_rerouted": 9, "failed": 1, "needs_review": 1}`
- boundary: 真实公开 GIS 背景；候选通道身份、设施、子管资源与成本为合成竞赛属性。
- output: 竞赛样例/非正式施工图，不用于施工、签章、概预算或现实资产判断。

## 任务终态

- T001: completed_direct / repair_count=0 / caused_by=-
- T002: completed_rerouted / repair_count=1 / caused_by=T001
- T003: completed_rerouted / repair_count=1 / caused_by=-
- T004: completed_rerouted / repair_count=1 / caused_by=T001
- T005: completed_rerouted / repair_count=1 / caused_by=-
- T006: completed_rerouted / repair_count=1 / caused_by=-
- T007: completed_rerouted / repair_count=1 / caused_by=T001
- T008: completed_direct / repair_count=0 / caused_by=-
- T009: completed_direct / repair_count=0 / caused_by=-
- T010: completed_direct / repair_count=0 / caused_by=-
- T011: completed_direct / repair_count=0 / caused_by=-
- T012: completed_direct / repair_count=0 / caused_by=-
- T013: completed_direct / repair_count=0 / caused_by=-
- T014: completed_direct / repair_count=0 / caused_by=-
- T015: completed_direct / repair_count=0 / caused_by=-
- T016: completed_direct / repair_count=0 / caused_by=-
- T017: completed_direct / repair_count=0 / caused_by=-
- T018: completed_direct / repair_count=0 / caused_by=-
- T019: completed_direct / repair_count=0 / caused_by=-
- T020: completed_direct / repair_count=0 / caused_by=-
- T021: completed_direct / repair_count=0 / caused_by=-
- T022: completed_rerouted / repair_count=1 / caused_by=-
- T023: completed_direct / repair_count=0 / caused_by=-
- T024: completed_direct / repair_count=0 / caused_by=-
- T025: completed_direct / repair_count=0 / caused_by=-
- T026: completed_rerouted / repair_count=1 / caused_by=-
- T027: completed_rerouted / repair_count=1 / caused_by=-
- T028: completed_direct / repair_count=0 / caused_by=-
- T029: needs_review / repair_count=0 / caused_by=-
- T030: failed / repair_count=1 / caused_by=-
