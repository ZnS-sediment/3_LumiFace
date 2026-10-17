# 实际验证记录

最终复核日期：2026-10-17（北京时间）。以下结果均来自已执行命令；不包含未执行的 GPU、原生 Windows 或现场考核验收；真实公开数据研究另列。

## 已通过

| 检查 | 执行命令 | 实际结果与证据 |
|---|---|---|
| Python 依赖一致性 | `.venv/bin/python -m pip check` | No broken requirements found |
| 后端算法、指标、接口 | `.venv/bin/python -m pytest -c backend/pytest.ini backend/tests -q` | **68 passed**，52.09 秒；work/research/backend-tests.log |
| TypeScript 与生产构建 | `npm run build --prefix frontend` | vue-tsc 与 Vite 成功，构建 49.42 秒；work/research/frontend-build.log |
| 真实模型端到端 | `.venv/bin/python scripts/smoke_real_model.py` | 退出码 0；公开样例真实推理、注册、已知验证、未知拒识、双人脸、五组消融和删除 |
| 真实后端浏览器流程 | `bash scripts/browser_check.sh` | **2 passed、0 skipped**，覆盖六页面、实际公开研究报告、CSV/协议下载与移动布局；work/browser-results.json |
| 一键启动 | `bash scripts/start.sh` | 前端、Swagger、OpenAPI、系统概览均 HTTP 200；work/startup-check.json |
| 空业务库核对 | GET /api/system/overview | persons/samples/detections/recognitions/datasets/experiments 全为 0 |

测试浏览器为 Chromium 141（Playwright 1.56.1）。浏览器验证使用隔离数据库和公开示例，正式 runtime 未混入测试身份与数据集。

## 覆盖内容

- 七类增强入口在全黑、暗图、常量中灰、全白上的类型、形状、数值稳定性与输入不变性。
- Gamma 提亮/压暗方向、正常光照不增强、逆光统计、直方图计数。
- 无效图片、无效参数、空/非有限特征、零匹配拒识。
- 检测一对一 IoU、多余检测算 FP、漏检进入端到端分母、总体计数汇总、无样本返回 null。
- 多图注册事务、无人脸/多人脸拒绝、重复照片冲突、照片与特征删除。
- 校准/测试图像摘要、采集会话、未知身份划分隔离与 ZIP 路径限制。
- 固定校准阈值、方法覆盖检查、图库变更拒绝复用校准。
- 删除身份后拒绝旧数据集的失效标注；新表编号不复用，旧表数字编号复用仍被注册时间绑定拦截。
- 后台推理失败标记 failed，不生成成功汇总；CSV 与逐样本图像预览。
- 浏览器上传与增强下载、检测裁剪、注册与详情抽屉、确认与拒识、数据包导入、实验完成、缺失场景未评估、CSV 下载、390 px 手机宽度无横向溢出、无页面 JS 错误。

## 真实模型联调结果的解释

来源、逐样本预测、计数和环境在 experiments/results/smoke-real-model.json，CSV 为同名文件。

- CPUExecutionProvider；buffalo_l 的 SCRFD 与 ArcFace 权重，内容指纹 `1f1ada9ba62bb8b8295a8ab7e5cbae2c31f50be997640a3a7a1d05bb51ca6197`。
- 一个公开示例身份参考；已知派生查询相似度约 0.99948（同源图，不能代表泛化）。
- 另一公开示例作未知身份，最高相似度约 -0.00131，被默认阈值 0.45 拒绝。
- 拼接的双人脸图片检测到 2 张脸。
- 五方法各处理 4 个查询（3 已知、1 未知），各组实际确认 3/3，未知误接受 0/1。
- 查询使用同一来源的人工 Gamma/局部压暗派生图，real_capture=false，框为手工近似标注。上述计数仅证明流程运行，不是研究准确率。
- 此次最终验证与前端构建、浏览器检查有并行执行，耗时只作为本次工程运行记录，不能作为专门性能基准。

## 警告与尚未验证

- InsightFace 0.7.3 调用旧 scikit-image estimate API 产生 FutureWarning；当前固定依赖可运行。Starlette TestClient 的 AnyIO 别名有弃用警告；不影响当前测试通过。
- Vite 提示 Element Plus 和 ECharts 打包块超过 500 kB；本地生产构建成功，未声称完成公网首屏性能优化。
- 已补 CBSR 真实主动近红外与 Yale B 真实受控光照研究；仍缺夜间、独立会话与实景强逆光/低照度的完整证据，**95% / 90% / 95% 现场目标尚不能认定达标**。
- GPU 自动 provider 分支、原生 Windows、跨模态 RGB↔IR、生产认证和统计泛化未实测。
- 旧默认端口预览服务未自动重启。更新接口后，在普通 WSL 终端执行 stop.sh/start.sh；不将旧服务状态写作已更新。最终浏览器流程使用独立 8001/5174 端口和临时业务库。

## 真实公开数据与实景审计补充

- 真实图集：CBSR 80 图库 / 70 校准 / 200 测试，Yale B 24 图库 / 50 校准 / 89 测试；每套相同五方法，共 1445 个测试方法-图片预测。
- 数据来源、许可快照、归档摘要、预先冻结清单及逐样本预测均保留在本机；公开照片不进入源码交付包。
- render_research_report.py 核对协议/冻结源码摘要，从保存的真实预测重新计算定位、已知正确、未知误接受及汇总，核对阈值一致性，再生成报告和 CSV。
- 每组展示 Wilson 区间及按已知人员聚类的 2000 次重采样区间；不生成合成身份分数。
- 现场 audit_field_data.py 检查重复像素、会话隔离、身份一致性、未知人员划分、人工场景日志及数量缺口。空模板已实际审计，退出码 2、ready_for_target_assessment=false，未生成任何性能成绩。
- 检测输入为研究协议的 320×320；应用默认 640×640，尺寸不一致拒绝复用校准。研究定位用眼点/单脸存在性，不写成 IoU 检测准确率。
- 完整下载规模与已完成的 pilot 子集分别标记。早期内存不足的完整协议尝试未发布为完成结果。

实际数值、失败分解、固定默认阈值补充对照与三项现场目标限制详见 real-data-evaluation.md。

最终浏览器测试在真实报告生成后执行，两个测试均通过且无跳过；实际研究页截图为 work/research-results.png 和 work/research-yale-results.png。
