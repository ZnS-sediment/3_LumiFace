# 模拟复杂光照演示与压力测试

日期：2026-10-17。按用户选择，以已有公开人脸照片制作软件模拟光照；不再等待新的实景数据申请。

## 已准备的文件

- `datasets/att_lighting_simulation.zip`：Windows 下载和解压用的主包。40 个 AT&T 身份，120 张原有注册参考图，1120 张四类查询图，以及 8 张公开未知样例的变体。
- `datasets/att_lighting_simulation/evaluation/calibration-1.zip`：324 图，含 320 个已知查询和 4 个未知查询。
- `datasets/att_lighting_simulation/evaluation/test-1.zip`、`test-2.zip`：各 402 图、各含 400 个已知查询和 2 个未知查询。需合并逐样本计数，不平均两个包的百分比。
- `experiments/results/simulated-att-lighting`：真实模型运行得到的逐样本预测、冻结阈值及 CSV。输入为模拟数据，不是实景报告。

## Windows 网页怎么用

1. 下载主包并解压到 Windows 本地目录，避免文件选择器读取 WSL 共享路径。
2. 身份库管理 → 批量导入身份 → 选择解压目录下的 `gallery`。现有 ATT_s01–ATT_s40 会按同名跳过，不需要删库重建。
3. 身份确认时，选择 `query` 下的场景、人员和照片，例如 `query/low_light/ATT_s01/06.png`，目标身份为 ATT_s01。
4. 同一源图的四个版本位于 `normal`、`low_light`、`backlight`、`pseudo_infrared`。用相同人员、相同编号对比增强开关和算法，结果以实际输出为准。
5. 新增网页“下载模拟光照演示包（40 人）”入口。新接口需重启后端后使用；在原启动终端 Ctrl+C，再执行 `bash scripts/start.sh`。

`pseudo_infrared` 是模拟灰度补光效果，不能复原真实红外光谱信息。AT&T 原照片本身即为灰度；本方案没有 AI 重画五官或生成新身份。

## 图像效果与身份一致性

- 已有人脸由 92×112 裁剪图统一放大两倍，再加入 20px 检测上下文；所有查询场景采用相同几何尺寸。
- 模拟低照度：线性域曝光衰减、柔和空间阴影、暗角、散粒噪声、读出噪声和轻微镜头软化。
- 模拟逆光：压低主体曝光并加入方向性遮光和宽范围眩光。
- 模拟灰度补光：前向照明场、暗角、灰度传感器噪声和轻微软化。
- 强度与噪声种子按文件固定，在模型测试前冻结；不根据测试成绩删图、重新选择参数或隐藏困难样本。

## 数据划分与统计范围

原图库使用源文件 01–03；源文件 04–05 用于校准；06–10 用于测试。同一原图的所有变体都留在同一个划分。校准和测试的未知样例分别来自 astronaut 和 Hopper，身份来源互斥，但各只有一个未知源人物，不能证明可靠的未知误接受率。

按人员进行身份注册和模板聚合，用真实 SCRFD/ArcFace 模型推理。离线报告的图库固定为 AT&T 40 人；网页业务库若含其他人员，或使用默认 640×640 检测配置，结果可能与本报告不同。五种方法分别在校准集选阈值并冻结，随后才处理测试集。报告正常基线、模拟低照度、模拟逆光及模拟灰度补光的确认正确数、分母、失败数、未知误接受及 CSV。综合可见光统计只合并前三类的正确数和查询数。

所有实验导入清单都写明 `real_capture: false`。本包使用单人脸存在性协议，清单 bbox 仅为图像范围的结构占位，不是人工真实人脸框，不用于 IoU 检测准确率结论。不同文件不代表独立采集会话；模拟数据不能完成原始 95%／90%／95% 实景验收。

配套实验包绑定生成时业务库中的姓名与 person_id 映射，记录于 `evaluation/person-ids.json`。若删库、重新注册或人员编号改变，先重新生成实验包，避免标签对应错人。

## 来源与引用

- AT&T / ORL：致谢 AT&T Laboratories Cambridge。[官方说明](https://www.cl.cam.ac.uk/research/dtg/attarchive/facedatabase.html)。
- 校准未知样例 astronaut：[scikit-image 样例与 NASA 公有领域说明](https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut)。
- 测试未知样例 grace_hopper：Matplotlib 随包公开样例，[数据来源](https://github.com/matplotlib/matplotlib/tree/main/lib/matplotlib/mpl-data/sample_data)与[上游许可](https://matplotlib.org/stable/project/license.html)。

## 清理内容

已删除未参与本轮模拟方案的两个可重新下载归档缓存：CBSR-NIR.zip、CroppedYale.zip，以及 3 张与 query 子目录完全重复的夜间 PNG，共约 408.8 MiB。删除前核对原始摘要；清理记录在 `work/simulation-cleanup.json`。

保留业务身份库与参考照片、模型权重、AT&T 源照片、来源与摘要、真实夜间小样本原件及全部既有研究结果。需要复现旧公开基准时，可使用原有 `scripts/download_research_data.py` 按固定摘要重新下载。

## 复现

```bash
cd /home/zns/3_LumiFace
.venv/bin/python scripts/prepare_simulated_lighting.py
.venv/bin/python experiments/scripts/benchmark_simulated.py --workers 2 --detector-size 320
```

运行前先检查是否已有同名完成报告，脚本不会静默覆盖。源码包不含业务库、模型和原始人脸；数据包单独提供。

## 本次真实模型实测结果（模拟输入）

五组方法完成全部 1620 次校准预测和 4020 次测试预测。检测输入 320×320，40 人图库，阈值先校准后冻结。

| 方法 | 原始基线 | 模拟低照度 | 模拟逆光 | 模拟灰度补光 | 前三类合并 |
|---|---:|---:|---:|---:|---:|
| 不增强 | 200/200 | 198/200 | 200/200 | 200/200 | 598/600（99.67%） |
| Gamma | 200/200 | 198/200 | 200/200 | 200/200 | 598/600（99.67%） |
| CLAHE | 200/200 | 198/200 | 200/200 | 200/200 | 598/600（99.67%） |
| Retinex | 200/200 | 196/200 | 200/200 | 200/200 | 596/600（99.33%） |
| 自适应 | 200/200 | 196/200 | 200/200 | 200/200 | 596/600（99.33%） |

自适应的四次失败发生于模拟低照度，保留在分母和逐样本记录中。未增强组的综合比例略高，自适应并非在所有图片上都有提升。所有方法在这批模拟数据上的三项观测比例都达到对应数值目标；这一结论不转写为真实实景目标通过。未知测试只有一名来源人物、4 张相关变体，观察到 0/4 误接受不构成可靠 FAR 证明。
