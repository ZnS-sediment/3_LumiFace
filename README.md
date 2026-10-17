# 3_LumiFace

**复杂光照条件下人脸检测增强算法及系统实现** — 本科实训用本地 B/S 研究平台。

Vue 3 + TypeScript + Vite + Element Plus + Axios + ECharts + Vue Router；FastAPI + OpenCV + NumPy + InsightFace + ONNX Runtime + SQLAlchemy + SQLite + Pydantic。PyTorch 作为可选研究/硬件诊断依赖；预训练 ONNX 推理不需要重新训练或安装整套 PyTorch。

## 当前交付

- 六个中文页面：系统概览、增强实验室、人脸检测、身份库、身份确认、实验评估。
- 独立 Gamma、CLAHE、Single Scale Retinex、曝光补偿、归一化及自适应增强；直方图与前后对比。
- 真实 SCRFD 检测、五点对齐、ArcFace 特征；多图注册、编辑、删除、1:1 验证、1:N 检索、未知拒识。
- ZIP 标注数据集导入、泄漏检查、独立阈值校准、五组消融、按场景汇总、逐样本结果与 CSV。
- CPU 已实测；装有兼容 CUDA/cuDNN 与 ONNX Runtime GPU 时尝试自动启用 CUDA，实际 provider 记录在实验里。
- 新增真实公开数据评估：CBSR 主动近红外与 Yale B 受控光照，五组实际推理、独立未知人员划分、校准后冻结阈值、逐样本 CSV、Wilson 与按人员重采样区间。详见 `docs/real-data-evaluation.md`。
- **95% / 90% / 95% 现场目标仍需实景验收**：公开 NIR 缺少夜间/独立会话证明，受控照明不能等同实景强逆光。新增实景采集协议与数据审计工具，自动列明缺口。

## 在当前 WSL 环境直接启动

项目位于 `/home/zns/3_LumiFace`，依赖和官方模型已安装：

```bash
cd /home/zns/3_LumiFace
bash scripts/start.sh
```

浏览器打开 http://localhost:5173；Swagger 为 http://localhost:8000/docs。按 Ctrl+C 同时停止前后端。首页可加载模型，首次人脸请求也会延迟加载模型。

Windows 资源管理器路径：`\\wsl.localhost\Ubuntu-20.04\home\zns\3_LumiFace`。

## 从零安装

需要 Python 3.11–3.12、Node.js 20.19+ 或 22.12+（此环境 Node 24.11.0）、npm、C++ 编译器。

```bash
# Ubuntu/WSL，若系统 python3 版本过低，显式选择 Python 3.11+
PYTHON_BIN=/home/zns/anaconda3/bin/python bash scripts/setup.sh
bash scripts/start.sh
```

模型只从官方 InsightFace release 下载。失败会报错，不安装假模型。下载包仅解压检测和识别权重，不包含年龄、性别分析模块。预训练权重为非商业研究用途，详见 `docs/datasets-and-licenses.md`。

## 建议演示顺序

1. 在增强实验室上传 JPG/PNG，选择自适应或手动方法，查看直方图与下载结果。
2. 在人脸检测页比较原始/增强两路，查看边界框、关键点与对齐人脸。
3. 用单人脸照片注册身份；每次支持 1–10 张，多图同一身份、同一采集会话。
4. 在身份确认页切换 1:1 / 1:N 和增强开关；低于阈值显示未知身份。
5. 先导入 `calibration` 标注集运行消融并冻结阈值；再导入独立 `test` 集选择校准记录评估。
6. 查看各场景样本数、错误率和逐样本结果，导出 CSV。缺失场景为“未评估”。

## 验证

```bash
bash scripts/check.sh
# 使用真实权重；隔离临时数据库；公开图片派生样本不是性能基准
.venv/bin/python scripts/smoke_real_model.py
```

单元测试中的确定性模型替身只存在于 `backend/tests/conftest.py`；真实模型联调脚本不使用替身。当前已通过 68 项后端测试、前端构建和完整真实后端浏览器流程。详细已执行结果见 `docs/verification.md`。完整依赖快照在 `backend/requirements-lock.txt`，前端使用 `frontend/package-lock.json`。

## 复现真实数据研究

```bash
# 研究许可、来源、固定子集与完整协议先读 docs/public-benchmark-protocol.md
bash scripts/run_public_study.sh
# 审计自行采集的真实数据，不会将空模板视为完成验收
.venv/bin/python scripts/audit_field_data.py /path/to/collection.json --output work/field-audit
```

下载的原始照片只保存在本机 `datasets/raw`，不进入源码包。源码附保存的预测、冻结协议和真实结果，结果可在实验页查看并导出。默认研究脚本使用 320×320 检测输入，与应用默认 640×640 分别记录，不混用校准记录。

## 目录

```text
3_LumiFace/
├── backend/app/{api,core,schemas,models,database,services,algorithms}
├── backend/tests/            # 算法、指标、接口、数据泄漏与故障测试
├── frontend/src/             # 六个 Vue 页面与共享组件
├── frontend/tests/           # Playwright 真实后端浏览器流程
├── scripts/                  # 安装、启动、检查、官方模型下载与真实联调
├── experiments/{configs,scripts,results}
├── datasets/README.md        # 标注 ZIP 协议
├── docs/                     # 架构、算法、接口、实验、部署与实训报告
├── runtime/                  # 私有数据库、照片和模型，已忽略 Git
└── work/                     # 开发验证日志和临时截图，已忽略 Git
```

## 数据与使用范围

默认只监听回环地址。`runtime` 不被静态托管；注册图片经受控接口读取，普通查询不返回特征向量。人员删除会删除注册照片、特征与涉及该人员的查询记录；历史实验标注/编号是独立研究记录，可进一步删除实验和数据集。不要把本教学系统直接暴露到公网，不应将其识别结果作为真实场景唯一身份认证依据。

详细文档：`docs/architecture.md`、`docs/algorithms.md`、`docs/api.md`、`docs/experiments.md`、`docs/deployment.md`、`docs/project-report.md`。

最后更新：2026-10-17。若此前已启动旧服务，请在普通 WSL 终端执行 `bash scripts/stop.sh`，再执行 `bash scripts/start.sh` 载入新增接口；浏览器进入“实验评估”可查看真实研究结果。旧服务未自动重启。
