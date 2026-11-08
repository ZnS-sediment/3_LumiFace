# REST API

开发地址 `http://127.0.0.1:8000`，Swagger `/docs`，OpenAPI `/openapi.json`。前端 `/api` 请求经 Vite 代理到此地址。默认仅本机访问。

## 统一响应

成功：`{"data": ..., "message":"ok"}`。失败：`{"data":null,"message":"原因"}`。HTTP 400 格式错误、404 不存在、409 重复/关联冲突、413 太大、415 格式不支持、422 参数/人脸数量无效、503 模型缺失或不可加载。CSV、PNG 接口直接返回对应媒体。

JSON 请求使用 Pydantic；图片接口 multipart/form-data。增强 options 是 JSON 字符串，例如 `{"method":"gamma","auto_parameters":true}`。支持 `original/gamma/clahe/retinex/exposure/normalize/adaptive`；参数详见算法说明。

## 路由

| 方法与路径 | 输入 | 输出核心字段 |
|---|---|---|
| GET /api/system/overview | 无 | persons,samples,detections,recognitions,datasets,experiments,model,latest_experiment |
| GET /api/system/directory-picker | 无 | available，本机系统目录选择是否可用 |
| POST /api/system/directory-picker | 请求头 X-LumiFace-Picker: 1，无路径参数 | 系统窗口选中的完整 path、token、照片元数据 files（相对 path/type/size/url，不读图、不传 Base64），取消时 data=null；100 MB、500 人、每人 10 张限制 |
| GET /api/system/directory-picker/{token}/photos/{index} | 系统选择返回的凭证和编号；preview=true 可选 | 按需读取原图或最长边 96px 的 JPEG 缩略图；源文件变化时 409，凭证过期时 410 |
| DELETE /api/system/directory-picker/{token} | 系统选择凭证 | 释放本次选择的元数据，不删除源文件 |
| GET /api/system/model | 无 | 模型状态，不查询业务数据库 |
| POST /api/system/model/load | 无 | ready,model,providers,fingerprint,error |
| POST /api/enhance/analyze | file | mean_brightness,histogram,underexposed_ratio,overexposed_ratio,contrast,illumination_unevenness,sharpness,scene |
| POST /api/enhance/process | file,options | original/enhanced(data URL),before/after,steps,elapsed_ms,parameters（实际值）,parameter_mode |
| POST /api/face/detect | file,options | 单路 faces,count,elapsed_ms,image,enhancement_ms,total_ms；只推理一次 |
| POST /api/person/register | name,note,capture_id,files(可重复字段) | 人员与样本元信息 |
| GET /api/person | q 可选 | 人员列表，不含特征 |
| GET /api/person/lfw-dataset | 无 | 原 120 人 ZIP：240 张参考图、四类场景各 360 张查询图 |
| GET /api/person/lfw-new-dataset | 无 | 新 280 人独立 ZIP：560 张参考图、四类场景各 840 张查询图；与原包无重复身份 |
| GET /api/person/{id} | 路径 ID | 样本质量、维数、模型指纹、受控 image_url |
| PATCH /api/person/{id} | JSON name,note | 更新人员 |
| DELETE /api/person/{id} | 路径 ID | deleted 编号、cleanup 文件清理状态 |
| POST /api/person/batch-delete | JSON person_ids，1–1000 个正整数 | 去重后的 deleted 编号数组、count、cleanup |
| GET /api/person/{id}/samples/{sample_id} | 两个 ID | 私有样本 PNG，no-store |
| POST /api/recognition/verify | file,person_id,options,threshold | 决策、相似度、阈值、人脸与图像 |
| POST /api/recognition/identify | file,options,threshold | 同上，最多 5 个候选身份 |
| GET /api/recognition/records | 无 | 最近 50 条决策记录 |
| POST /api/dataset/import | file(ZIP) | 数据集 ID、划分、来源、场景数量 |
| GET /api/dataset | 无 | 数据集列表 |
| GET /api/dataset/{id} | ID | 元信息与标注清单 |
| DELETE /api/dataset/{id} | ID | 无实验引用时删除数据和图片 |
| POST /api/experiment/run | JSON dataset_id,methods,threshold,calibration_id，可选 name | 排队任务与冻结配置 |
| POST /api/experiment/images | multipart files（重复字段）、labels（JSON） | 多图测试任务，复用实验记录、进度与结果 |
| GET /api/experiment | 无 | 最近 100 个任务及汇总 |
| GET /api/experiment/{id} | ID | 名称 name、状态、进度、参数、环境、summary、error_summary、error |
| PATCH /api/experiment/{id} | JSON name，去除首尾空格后 1–100 字 | 更新测试显示名称；运行中返回 409，原始数据清单与结果不变 |
| GET /api/experiment/{id}/results | offset=0,limit=50 (≤100) | 逐样本真实预测、计数、耗时 |
| GET /api/experiment/{id}/preview/{result_id} | ID | 原图、按记录参数重建增强图和预测标注 |
| DELETE /api/experiment/{id} | ID | 删除已完成/失败实验，引用校准时保护 |
| POST /api/calibration | JSON experiment_id,target_far | 校准 ID、分方法阈值、样本数、观测 FAR |
| GET /api/calibration | 无 | 所有校准记录 |

## 示例

```bash
curl http://127.0.0.1:8000/api/system/overview
curl -X POST http://127.0.0.1:8000/api/enhance/process \
  -F 'file=@photo.jpg' -F 'options={"method":"gamma","auto_parameters":true}'
curl -X POST http://127.0.0.1:8000/api/person/register \
  -F 'name=测试人员' -F 'capture_id=enroll-session-01' \
  -F 'files=@reference1.jpg' -F 'files=@reference2.jpg'
curl -X POST http://127.0.0.1:8000/api/recognition/verify \
  -F 'file=@probe.jpg' -F 'person_id=1' -F 'threshold=0.45' \
  -F 'options={"method":"original"}'
curl -X POST http://127.0.0.1:8000/api/experiment/run \
  -H 'Content-Type: application/json' \
  -d '{"dataset_id":1,"methods":["original","gamma","clahe","retinex","adaptive"],"threshold":0.45}'
```

`confirmed=false` 时返回的 person_id 为 null，最高候选只在 candidates 中呈现。未检测到人脸时身份确认返回 422。多人脸逐一匹配，faces[].match、face_matches 保留每张脸的判定，person_ids 为已确认身份编号集合，name 为去重后的已确认姓名；多人脸的顶层 person_id 为 null，不表示所有脸属于同一人。注册验证所有输入后一次提交，不会因为第二张照片失败而留下半个身份。

实验 summary 各方法含 overall/scenes/targets。分母为零的指标为 null；前端显示“未评估”。queued/running 为未完成，failed 保存错误，不生成达标汇总。

多图测试的 `labels` 结构为 `{"methods":["original","gamma"],"threshold":0.45,"items":[{"filename":"query/人员/04.png","person_id":1,"scene":"normal"}]}`，items 与 files 数量、顺序和上传文件名一致，未知身份显式使用 null。每次 1–1500 图，合计不超过 100 MB；同批重复或注册重叠图拒绝。`config.kind=image_batch`，新任务使用 image_identity_presence，单脸按精确身份过阈值判定，多脸按任一已确认 person_id 命中判定；未知标签图片任一脸被接受即算误接受。历史 single_face_presence 不变。逐图结果新增 filename、expected_name、predicted_name、similarity、outcome；overall 新增 no_face、multiple_faces。已知正确率分母包括漏检、拒识和认错的图片，多脸不再自动算错误；predictions[].match 保留每张脸的判定。每轮生成独立任务，原有真实研究报告不被覆盖。删除该任务时清理其独占的自动生成测试数据副本。

## 真实研究结果与场景证据

- `GET /api/research/benchmarks`：只返回本机已经完成的 CBSR/Yale 真实公开评估摘要，无原始图片或特征向量。
- `GET /api/research/benchmarks/{dataset}/csv`：下载真实逐样本计数。
- `GET /api/research/benchmarks/{dataset}/protocol`：查看运行前冻结的源图清单、划分、参数、摘要和证据范围；dataset 仅接受 cbsr-nir / yale-b。

数据集清单新增可选 `localization_protocol`（iou、eye_containment、single_face_presence、image_identity_presence）和 `protocol` 场景证据。默认保持 IoU 协议；非 IoU 结果不能解释为 IoU 精度。眼点协议需 faces[].eyes 两个独立标注坐标。

protocol.capture_independence 为 session_disjoint / condition_disjoint / frame_disjoint / unknown；scene_evidence 中记录 source、annotation_basis、modality、active_illumination、night_confirmed、backlight_confirmed、low_light_confirmed。real_capture=true 本身不再足以判为现场目标达成。

实验汇总新增 known_subjects、unknown_subjects、confirmation_ci95、unknown_far_ci95、confirmation_subject_bootstrap_ci95。targets 同时给出 reasons、点估计、区间及证据状态。

`GET /` 为浏览器入口导航，返回 307 跳转到本地前端（默认 http://localhost:5173/；可使用已允许的 LUMIFACE_UI_ORIGIN）。不存在的 API 路径仍返回 404，API 文档仍在 /docs。

网页批量注册按人员顺序调用现有 `POST /api/person/register`，没有新增批量注册 API 或数据库旁路。同名跳过和逐人报告在网页端组织；单人照片事务、重复图/会话检查与真实推理由后端现有服务执行。

身份批量删除先校验整批编号；任一编号不存在返回 409，整批不删除。重复编号仅处理一次，非法/空/超限编号列表返回 422。成功后统一删除所选人员、参考照片、特征，以及在确认身份、候选或验证目标中涉及这些人员的查询记录；其他人员及历史实验标注不改动。

删除响应新增 `cleanup: {deleted_files: 3, pending_files: 0}`。`pending_files` 非零表示数据库身份已删除，但磁盘清理尚未全部完成；网页显示警告，下次删除或服务重启会重试。清理范围仅为系统生成的注册副本，下载的演示 ZIP、原始数据集和独立实验数据不受身份删除影响。

`GET /api/person/lfw-dataset` 下载原 `datasets/lfw_120_lighting.zip`；`GET /api/person/lfw-new-dataset` 下载 `datasets/lfw_280_new_lighting.zip`。缺失时分别提示运行 `scripts/prepare_lfw_lighting.py` 或 `scripts/prepare_lfw_disjoint.py`。图像检测接口改为单路输出；算法比较统一使用实验接口。

网页增强、检测和身份确认均传 `auto_parameters=true`；多图测试 labels 默认 true，并逐图冻结计算后的实际参数。一般实验 API 的同名字段默认 false，兼容历史固定参数协议。校准与测试的自动参数模式必须一致。选择凭证仅在内存保留，最多 16 份，6 小时未读取即失效，服务重启后需重新选择目录。

多图测试详情的 `error_summary` 从全部已保存逐图结果统计，按方法给出 overall 与 scenes。每组包含 images、total_errors、counts（no_face/multiple_faces/rejected/wrong_identity/false_accept）、unclassified，不受逐图表分页限制；未知身份被正确拒绝不计错误。原有历史 summary、参数和结果不改写。

新建多图测试的 labels 可包含可选 `name`，去除首尾空格后最多 100 字。省略、空字符串或仅空格时，继续使用原来的“多图测试 MM-DD HH:MM:SS”默认名称；填写时将显示名称与任务一同保存，不改写原始数据清单名称。

自动参数的新实验同时冻结 `recognition_policy=aligned-fusion-v3` 和 `enhanced_feature_weight=0.3`；网页身份确认使用相同的融合路径。固定参数 API 与缺少该策略字段的历史配置继续使用 `processed-v1`。像素增强变换保持兼容，不根据标签挑选或切换预测。多脸存在性协议不能用于单脸阈值校准。模型状态返回实际会话 `inference_threads`，检测和识别均为 intra=2、inter=1。

`aligned-fusion-v3` 的逐图结果新增 `timing`：`original_inference_ms` 为共享原图成本，`method_ms` 为该方法其余计算，`accounting=standalone_with_shared_original`。`elapsed_ms` 为两者之和，不因缓存而少计成本；旧策略的 timing.accounting 为 standalone。

1.3 起模型状态增加 `recognition_backbone=glintr100`。服务会从已知旧模型的注册照片自动缓存当前模型特征；未知指纹、原图缺失或摘要不符返回 409。已有实验的模型指纹和结果不改写。

网页不再提供阈值输入或显示；省略 `threshold` 时后端使用冻结校准值。API 仍允许研究复现显式提供数值，历史实验保存各方法实际数值及 threshold_policy。图片测试接口采用有界 multipart 解析，支持单场景 1200 张图片；上限 1500，合计 100 MB。
