# REST API

开发地址 `http://127.0.0.1:8000`，Swagger `/docs`，OpenAPI `/openapi.json`。前端 `/api` 请求经 Vite 代理到此地址。默认仅本机访问。

## 统一响应

成功：`{"data": ..., "message":"ok"}`。失败：`{"data":null,"message":"原因"}`。HTTP 400 格式错误、404 不存在、409 重复/关联冲突、413 太大、415 格式不支持、422 参数/人脸数量无效、503 模型缺失或不可加载。CSV、PNG 接口直接返回对应媒体。

JSON 请求使用 Pydantic；图片接口 multipart/form-data。增强 options 是 JSON 字符串，例如 `{"method":"gamma","gamma":0.65}`。支持 `original/gamma/clahe/retinex/exposure/normalize/adaptive`；参数详见算法说明。

## 路由

| 方法与路径 | 输入 | 输出核心字段 |
|---|---|---|
| GET /api/system/overview | 无 | persons,samples,detections,recognitions,datasets,experiments,model,latest_experiment |
| POST /api/system/model/load | 无 | ready,model,providers,fingerprint,error |
| POST /api/enhance/analyze | file | mean_brightness,histogram,underexposed_ratio,overexposed_ratio,contrast,illumination_unevenness,sharpness,scene |
| POST /api/enhance/process | file,options | original/enhanced(data URL),before/after,steps,elapsed_ms,parameters |
| POST /api/face/detect | file,options | original/enhanced 中的 faces,count,elapsed_ms,image；增强组另含 enhancement_ms,total_ms |
| POST /api/person/register | name,note,capture_id,files(可重复字段) | 人员与样本元信息 |
| GET /api/person | q 可选 | 人员列表，不含特征 |
| GET /api/person/{id} | 路径 ID | 样本质量、维数、模型指纹、受控 image_url |
| PATCH /api/person/{id} | JSON name,note | 更新人员 |
| DELETE /api/person/{id} | 路径 ID | 删除编号 |
| GET /api/person/{id}/samples/{sample_id} | 两个 ID | 私有样本 PNG，no-store |
| POST /api/recognition/verify | file,person_id,options,threshold | 决策、相似度、阈值、人脸与图像 |
| POST /api/recognition/identify | file,options,threshold | 同上，最多 5 个候选身份 |
| GET /api/recognition/records | 无 | 最近 50 条决策记录 |
| POST /api/dataset/import | file(ZIP) | 数据集 ID、划分、来源、场景数量 |
| GET /api/dataset | 无 | 数据集列表 |
| GET /api/dataset/{id} | ID | 元信息与标注清单 |
| DELETE /api/dataset/{id} | ID | 无实验引用时删除数据和图片 |
| POST /api/experiment/run | JSON dataset_id,methods,threshold,calibration_id | 排队任务与冻结配置 |
| GET /api/experiment | 无 | 最近 100 个任务及汇总 |
| GET /api/experiment/{id} | ID | 状态、进度、参数、环境、summary,error |
| GET /api/experiment/{id}/results | offset=0,limit=50 (≤100) | 逐样本真实预测、计数、耗时 |
| GET /api/experiment/{id}/preview/{result_id} | ID | 原图、按记录参数重建增强图和预测标注 |
| GET /api/experiment/{id}/csv | ID | UTF-8 BOM CSV，各方法/样本计数与耗时 |
| DELETE /api/experiment/{id} | ID | 删除已完成/失败实验，引用校准时保护 |
| POST /api/calibration | JSON experiment_id,target_far | 校准 ID、分方法阈值、样本数、观测 FAR |
| GET /api/calibration | 无 | 所有校准记录 |

## 示例

```bash
curl http://127.0.0.1:8000/api/system/overview
curl -X POST http://127.0.0.1:8000/api/enhance/process \
  -F 'file=@photo.jpg' -F 'options={"method":"gamma","gamma":0.65}'
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

`confirmed=false` 时返回的 person_id 为 null，最高候选只在 candidates 中呈现。若未检测到人脸或出现多人脸，身份确认返回 422，不写入一次成功确认。注册验证所有输入后一次提交，不会因为第二张照片失败而留下半个身份。

实验 summary 各方法含 overall/scenes/targets。分母为零的指标为 null；前端显示“未评估”。queued/running 为未完成，failed 保存错误，不生成达标汇总。

## 真实研究结果与场景证据

- `GET /api/research/benchmarks`：只返回本机已经完成的 CBSR/Yale 真实公开评估摘要，无原始图片或特征向量。
- `GET /api/research/benchmarks/{dataset}/csv`：下载真实逐样本计数。
- `GET /api/research/benchmarks/{dataset}/protocol`：查看运行前冻结的源图清单、划分、参数、摘要和证据范围；dataset 仅接受 cbsr-nir / yale-b。

数据集清单新增可选 `localization_protocol`（iou、eye_containment、single_face_presence）和 `protocol` 场景证据。默认保持 IoU 协议；非 IoU 结果不能解释为 IoU 精度。眼点协议需 faces[].eyes 两个独立标注坐标。

protocol.capture_independence 为 session_disjoint / condition_disjoint / frame_disjoint / unknown；scene_evidence 中记录 source、annotation_basis、modality、active_illumination、night_confirmed、backlight_confirmed、low_light_confirmed。real_capture=true 本身不再足以判为现场目标达成。

实验汇总新增 known_subjects、unknown_subjects、confirmation_ci95、unknown_far_ci95、confirmation_subject_bootstrap_ci95。targets 同时给出 reasons、点估计、区间及证据状态。
