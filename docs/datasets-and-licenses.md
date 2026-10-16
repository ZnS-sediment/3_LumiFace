# 数据集可用性与权重来源核实

核实日期：2026-10-16。以下说明来自官方来源；不自动同意协议、代签机构文件或获取限制下载的数据。

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
