# 数据集可用性与权重来源核实

首次核实：2026-10-16；真实公开数据补充：2026-10-17，见本文末及 public-benchmark-protocol.md。以下说明来自官方来源；不自动同意协议、代签机构文件或获取限制下载的数据。

| 数据集 | 官方说明与身份/光照覆盖 | 获取与授权现状 | 本项目状态 |
|---|---|---|---|
| Extended Yale B | UCSD 官方列出 28 人、9 姿态、64 光照、16128 图像；该数为扩展部分，不与合并后的 38 人裁剪集混淆 | 官方入口指向旧下载页，检查时返回 404；页面未明确提供可据以重新分发的授权条款 | 未下载；需确认维护者或有许可的来源。光照变化不等于红外 |
| CMU Multi-PIE | 官方列出 337 人、15 视角、19 光照，跨最多四个会话；包含身份结构 | 官方首页提供发行/订购链接至 Flintbox；未获得授权下载，费用与当前分发条件待提供方确认 | 未下载，不能宣称已覆盖 IR |
| SCface | 官方列出 130 人、4160 图像，含可见光与红外；采集使用室内监控摄像头 | 免费研究申请，需要机构抬头申请信和 Release Agreement，由全职工作人员签署，学生不能作为签署人 | 未申请、未下载；具 IR 样本但仍须按相机/距离/模态设计测试，不能自动等同目标场景 |

官方来源：

- [UCSD Extended Yale B](https://vision.ucsd.edu/datasets/extended-yale-face-database-b-b)
- [UCSD 页面指向的旧下载入口](https://datarepo.eng.ucsd.edu/visiondata/iskwak/public_html/ExtYaleDatabase/ExtYaleB.html)
- [CMU Multi-PIE](https://www.cs.cmu.edu/afs/cs/project/PIE/MultiPie/Multi-Pie/Home.html)
- [SCface 官方获取与协议说明](https://www.scface.org/)

## 预训练模型

使用 InsightFace 0.7.3 的 buffalo_l 检测和识别权重。官方说明库代码采用 MIT，预训练模型限非商业研究。项目用途为教学研究；未经额外许可不转为商业系统。

[InsightFace 模型与授权](https://github.com/deepinsight/insightface/blob/master/python-package/docs/model_zoo.md)

下载脚本先尝试 v0.7 release，再尝试官方 model-zoo release；两者均属于 deepinsight/insightface。运行时不会因为缺权重静默联网或替换模型。此次实际来源为：

`https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip`

| 文件 | 此次下载后计算的 SHA-256 |
|---|---|
| det_10g.onnx | 5838f7fe053675b1c7a08b633df49e7af5495cee0493c7dcf6697200b85b5b91 |
| w600k_r50.onnx | 4c06341c33c2ca1f86781dab0e829f88ad5b64be9fba56e56bc9ebdefc619e43 |

摘要用于复现与变更检测，不声称是第三方签名认证。权重不提交 Git，下载 provenance 保存在模型目录 source.json。

## 功能验证样例

`smoke_real_model.py` 使用 scikit-image 的 astronaut（官方说明 NASA 公有领域）与 Matplotlib 随包 grace_hopper 示例。两者来源和各自上游条款必须保留。脚本不对用户照片进行外传。

- [scikit-image 示例与 astronaut 许可说明](https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut)
- [Matplotlib 示例数据目录](https://github.com/matplotlib/matplotlib/tree/main/lib/matplotlib/mpl-data/sample_data)
- [Matplotlib 许可](https://matplotlib.org/stable/project/license.html)

功能测试用同源 Gamma 和局部压暗派生图，具有同源相关性，故 `real_capture=false`。它们只能验证管线可以运行，不能验证人物泛化、红外、真实逆光或 95% 考核目标。无红外样例时不生成红外“成功率”。

## 2026-10-17 补充核实与真实评估接入

已取得 OTCBVS 主办方公开提供的 CBSR NIR 完整归档（197 人、3940 图）和真实身份/眼点标注，按其教育研究条款仅在本地使用并致谢。已取得 Yale B 裁剪研究镜像，只使用原始编号 01–10，依据 Yale 官方研究条款，保留镜像来源且不再分发照片。实际已测子集、摘要与完整协议严格区分，见 public-benchmark-protocol.md 和 real-data-evaluation.md。

当前不能把这两份数据直接当成现场目标验收：CBSR 未提供夜间/跨会话标记，Yale 是短时受控光照序列。Idiap MCXFace 虽含 RGB/NIR、多会话及照明变化，但其 [Zenodo 原始记录](https://zenodo.org/records/7309673) 明确 Restricted，需要永久职位签署人和机构邮箱审批，尚未取得授权；不通过非授权镜像绕过此流程。

致谢：IEEE OTCBVS Workshop Series Benchmark；Center for Biometrics and Security Research (CBSR)；AuthenMetric Co. Ltd (Beijing)。参考 Stan Z. Li, RuFeng Chu, ShengCai Liao, Lun Zhang, “Illumination Invariant Face Recognition Using Near-infrared Images,” IEEE TPAMI 29(4), 627–639, 2007。

Yale 原始数据引用 Athinodoros Georghiades, Peter Belhumeur, David Kriegman, “From Few to Many: Illumination Cone Models for Face Recognition under Variable Lighting and Pose,” IEEE TPAMI, 2001。裁剪处理同时说明 Kuang-Chih Lee, Jeffrey Ho, David Kriegman, “Acquiring Linear Subspaces for Face Recognition under Variable Lighting,” IEEE TPAMI, 2005。

## AT&T / ORL 功能演示数据（2026-10-17）

已从[剑桥大学托管页](https://www.cl.cam.ac.uk/research/dtg/attarchive/facedatabase.html)取得 40 个匿名身份、400 张照片，按来源要求致谢 AT&T Laboratories Cambridge。原始图像和来源页留在 datasets/raw/att-faces；本地整理目录为 datasets/att_faces_demo。身份编号不是真实姓名，转换与固定边框、注册/查询文件划分详见 web-identity-import.md，不作为实景目标证据。
