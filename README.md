# LumiFace

复杂光照下的人脸增强与身份确认系统。Vue 3 + FastAPI + SQLite，使用本地 InsightFace SCRFD 检测与 Glint360K ResNet100（ArcFace）特征提取模型。

## 运行

已安装环境的项目位于 `/home/zns/3_LumiFace`：

```bash
cd /home/zns/3_LumiFace
bash scripts/start.sh
```

网页：http://localhost:5173；接口文档：http://localhost:8000/docs。Ctrl+C 停止前后端；修改后端代码后需要停止并重新启动，刷新浏览器不会更新已运行的 Python 进程。

首次安装需要 Python 3.11–3.12、Node.js 20.19+ 或 22.12+、npm 和 C++ 编译器：

```bash
PYTHON_BIN=python3.11 bash scripts/setup.sh
```

安装脚本包含开发测试依赖。`backend/requirements.txt` 是运行依赖，`requirements-dev.txt` 额外包含测试工具；`requirements-lock.txt` 保存已验证环境的完整快照。模型从官方 InsightFace release 下载，不在 API 调用中隐式下载。

## 功能与演示

- **图像增强**：Gamma（低照度）、CLAHE（逆光）、Retinex（光照不均），查看处理前后图像并下载结果。
- **人脸检测**：可选增强，显示检测框、关键点和对齐裁剪。
- **身份库管理**：单人或批量注册、查看、编辑、批量删除；Windows/WSL 系统目录选择会自动获取完整路径与照片。
- **身份确认**：1:1 验证或 1:N 检索，逐脸识别多人照片，自动判定并拒绝未知身份。
- **实验评估**：一次测试多图，按“新建测试 / 测试结果 / 历史记录”操作，保存逐图判定、分组正确率与历史记录。

首页直接进入图像增强。服务启动时自动加载本地人脸模型，网页不显示模型状态或加载按钮。已有身份会从注册照片自动建立新版特征，原照片和原始特征保留，无需重新导入。模型异常时图像增强仍可用，人脸操作返回具体原因。

身份与光照包只在“身份库管理 → 批量导入身份”提供两个独立下载链接：原 120 人包，以及身份完全不重叠的新 280 人包。各有 `gallery` 注册图与 `query` 查询图；正常、逆光、光照不均和低照度每场景分别为 360 / 840 张。两包可同时注册为 400 人图库。特殊光照为软件模拟输入；正确率与增强效果以实际输出为准，不作为 95%／90%／95% 实景指标的验收结论。

演示步骤见 [现场演示](docs/demo-walkthrough.md)，导入与目录选择见 [身份导入](docs/web-identity-import.md)，批量评估见 [多图测试](docs/multi-image-evaluation.md)。

## 数据管理

- `runtime/`：私有数据库、注册副本和模型；不作为静态目录公开。
- `datasets/`：下载包、原始与模拟输入。
- `experiments/results/`：冻结研究协议及结果。
- `work/`：开发验证日志、截图与测试夹具。

删除身份会清理该身份的注册副本、特征和关联识别记录。下载包、源照片和模型保留；清理失败会登记任务，在后续删除或服务启动时重试。

## 检查与研究复现

```bash
bash scripts/check.sh
LUMIFACE_TEST_API_PORT=8013 LUMIFACE_TEST_UI_PORT=5186 bash scripts/browser_check.sh
```

CLAHE 识别在对齐人脸上处理光照并融合镜像特征；Gamma、Retinex 融合原图与增强图特征，默认判定参数在开发数据上选取，页面无需设置；多脸测试按任一已确认的精确身份命中计算，单脸规则不放宽。旧实验保留原始结果，新规则需新建测试。

当前下载包验证：`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python scripts/benchmark_face_local.py`，加 `--original-package` 检查旧 120 人包。需要已有的 `work/lfw-400/references.json` 真实模型参考缓存，结果写入 `work/face-local-v4/`，不操作正式数据库。开发与留出验证分别运行 `scripts/probe_face_local.py`、`scripts/evaluate_face_local.py`；历史融合验证脚本保持旧协议。

浏览器测试使用临时数据库与真实本地模型，不操作正式身份库。详细检查结果见 [验证记录](docs/verification.md)。

公开研究的固定协议、原始预测与复现方式见 [公开基准协议](docs/public-benchmark-protocol.md)；历史算法用于读取及复现既有研究，网页提供三种增强方法。

更多说明：[部署](docs/deployment.md) · [架构](docs/architecture.md) · [算法](docs/algorithms.md) · [API](docs/api.md) · [数据许可](docs/datasets-and-licenses.md) · [报告初稿](docs/project-report.md)。
