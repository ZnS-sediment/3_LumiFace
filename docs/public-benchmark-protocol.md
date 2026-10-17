# 真实公开基准协议

核实日期：2026-10-17。照片仅在本地研究使用，不进入源码包、输出下载或公网静态目录。

## 数据来源

### CBSR NIR / OTCBVS Dataset 07

主办方公开提供 197 人、3940 张真实近红外图像；原图库每人 8 张，查询每人 12 张，并给出身份和独立眼睛坐标。OTCBVS 集合允许教育研究使用并要求致谢。当前 HTTPS 证书过期，下载使用其公开 HTTP 入口；文件摘要固定在下载脚本和 provenance.json，用于复现校验，不声称是官方签名认证。

- [主办方数据说明](http://vcipl-okstate.org/pbvs/bench/Data/07/download.html)
- [主办方教育研究使用条款与致谢](http://vcipl-okstate.org/pbvs/bench/index.html)
- 实际归档 SHA-256：`066e385ac7469012f9c2574738c6b8bd15dcfcc5085e7eb97148e0b884b9fe53`

这是 NIR→NIR 同模态协议。主办方没有明确提供夜间环境和独立会话记录，故不能将本结果写成夜间补光或 RGB→NIR 已达标。

### Yale Face Database B

只使用原始编号 01–10。Yale 官方明确允许研究使用并要求引用 Georghiades、Belhumeur、Kriegman，PAMI 2001；裁剪版还应说明人工对齐、168×192 和数据处理来源。由于原下载端失效，采用公开教学研究镜像，记录传输来源；镜像中的扩展人员不参与本次协议，不把镜像项目的代码许可证解释为人脸图像授权。

- [Yale 原始说明与研究条款](http://cvc.cs.yale.edu/cvc/projects/yalefacesB/yalefacesB.html)
- [教学镜像来源说明](https://trokas.github.io/ai_primer/SVD.html)
- 实际归档 SHA-256：`7696c098b298561cd12e52c797b66fca5f864c27a000d7bda6d1b86c1fe91d39`

原始说明指出同一姿态下的光照序列约两秒内采集。因此它是受控光照压力测试，不能假称跨会话实景验收。按文件中的光源方位分为受控正面光、斜向光、背侧光、无闪光环境光；不用“强逆光”“夜间”替换这些源标签。

## 冻结与预处理

协议在任何模型推理前写出 protocol-frozen.json，包括原图路径、身份/光照条件划分、数据摘要、代码摘要、参数、工作进程数和时间。像素完全重复的图在推理前按图库→校准→测试优先顺序去重，所有排除单独记录，不按识别成败删样本。

校准完成后写出 thresholds-frozen.json，才开始测试。五方法使用同一模型、同一图库、同一划分；原始组含所有方法共有的输入准备。默认 CPU 固定子集使用 320×320 检测输入，正式系统默认 640×640；检测尺寸也是冻结配置的一部分，不将两个尺寸的结果混为同一实验。

Yale 紧裁剪图的检测边框在图库参考图上选定，测试前固定：增强先处理原图，然后仅为检测增加 100 px 灰度 100 的上下文边框，预测坐标再移回原图。边框不改变原有人脸光照，也不参与增强场景统计；各方法完全一致。这不是对测试人脸做真实场景合成。

## 定位真值边界

CBSR 仅提供眼点，没有独立 bbox。因此使用“预测框是否包含两个独立标注眼点”进行匹配。Yale 裁剪图使用恰有一个人脸输出的存在性判据。二者都不能当作 IoU=0.5 的检测精确率/召回率；研究结果界面和报告单独标示协议。

所有身份确认仍来自真实检测、特征与余弦分数。漏检、多脸歧义、相似度不足或身份错误均不会计为正确确认。注册失败的人员不会从已知查询分母中消失。

## 固定子集与完整协议

固定子集用于当前 7 GB WSL 环境，按编号和文件名预先确定，未根据模型成绩挑图：

- CBSR：实际编号排序前 20 人为已知，接着 10 人为未知校准，再接着 20 人为未知测试。每个已知人取原图库前 4 张；原查询前 2 张校准、随后 5 张测试。未知校准每人前 3 张，未知测试每人前 5 张。图库 80、校准 70、测试 200（已知 100、未知 100），最终还核对像素去重。
- Yale：01–06 为已知，07–08 未知校准，09–10 未知测试。已知图库使用固定四个正面照明条件；其他图按光照组与文件名确定校准/测试，无闪光环境光只用于查询。实际计数以冻结清单为准。

完整 CBSR 协议使用 100 名已知、40 名未知校准、57 名未知测试，图库 800、校准 560、测试 1484；Yale 完整受控协议使用剩余全部可用原始人员图像。完整协议的下载和执行入口保留，但不能把尚未完成的完整协议写成已完成结果。

```bash
.venv/bin/python scripts/download_research_data.py cbsr-nir
.venv/bin/python scripts/download_research_data.py yale-b
.venv/bin/python experiments/scripts/benchmark_public.py cbsr-nir --profile pilot --workers 2 --detector-size 320
.venv/bin/python experiments/scripts/benchmark_public.py yale-b --profile pilot --workers 2 --detector-size 320
# 内存与时间充足时，独立输出完整协议，避免覆盖固定子集报告
.venv/bin/python experiments/scripts/benchmark_public.py cbsr-nir --profile full --workers 2 --detector-size 640 --output work/cbsr-full
```

## 统计解释

逐样本保存真实预测及计数、固定阈值、方法与时延。报告 Wilson 95% 区间和按已知人员聚类的 bootstrap 区间；bootstrap 只重采样真实结果，不生成身份分数。未知 FAR 同时报告分母及区间。并发 CPU 时延仅记录运行环境，不作为独占硬件速度排名。

首次全规模尝试因 WSL 内存与交换区压力在校准前后中断，没有发布测试成绩。中断协议和日志保留在 work/research；最终完成报告只来源于明确冻结的固定子集。

## 原始采集异常

另外核对 Yale 官方 no_strobe.html 与 corrupt.html 清单。已记录的闪光未触发图独立标为“闪光未触发”，不按文件名的原计划灯光方位归类；轻微奇偶行强度不平衡保留质量标记。不会因这些图片识别失败而在测试后剔除。清单和处理规则在 Yale 运行前冻结。
