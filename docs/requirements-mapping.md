# 需求与实现对应

| 要求 | 实现位置 | 已验证范围 |
|---|---|---|
| 光照分析、直方图、质量 | backend/app/algorithms/light_analysis.py | 极端图、场景统计、实际增强 UI |
| Gamma/CLAHE/Retinex/曝光/归一化/自适应 | backend/app/algorithms/enhancement.py | 独立算法测试和真实输入 |
| 检测、多脸、关键点、对齐 | backend/app/algorithms/face_detector.py | 官方权重、双人脸、裁剪 UI |
| 多图注册、身份编辑、删除 | backend/app/services/persons.py、api/routes.py | 事务、非法照片、删除、浏览器注册 |
| 1:1、1:N、未知拒识 | backend/app/algorithms/face_recognizer.py、api/routes.py | 实际已知验证、实际未知拒识 |
| 数据集与批量消融 | backend/app/services/datasets.py、experiments.py | 真实推理、进度、逐图结果、预览 |
| 指标定义、固定阈值、分组统计 | backend/app/algorithms/metrics.py、docs/experiments.md | 计数、空分母、校准冻结、泄漏检查 |
| SQLite ORM、样本访问限制 | backend/app/database、models、core | API 集成、私有路径与删除 |
| 五个中文页面 | frontend/src/views | 全部页面真实后端浏览器流程 |
| 安装、启动、部署、自动检查 | scripts、docs/deployment.md | WSL CPU 环境实测 |
| 报告与复现信息 | docs/project-report.md、environment.json、experiments/results | 保留真实执行范围与限制 |
| 真实公开数据研究 | experiments/scripts/benchmark_public.py、docs/real-data-evaluation.md | CBSR 实际 NIR、Yale B 实际受控光照，冻结协议与逐样本预测 |
| 真实红外/逆光/综合性能目标 | algorithms/evidence.py、docs/field-study-protocol.md | 逐项核对场景证据、计数和区间；公开研究不替代现场验收 |
| 自采实景数据准备 | scripts/audit_field_data.py | 会话/身份泄漏、重复图、真实场景证据、数量缺口和导入包 |

原始需求文档保留于 requirements-original.md。完整验证证据与当前服务状态见 verification.md。
