# 仅直接下载公开数据：特殊光照照片与三项目标核查

核查日期：2026-10-17。用户约束：不自行采集，不申请数据权限，仅使用可直接下载的公开数据。

## 当前结论

本次完成来源与场景覆盖核查，并新增了一名人物、两段真实夜间录像的固定样本功能小测，没有将任何目标改为已达标。现有 CBSR-NIR、Yale B 的真实结果继续保留；三项实景目标尚未全部完成验证。

“已运行验证”与“指标达标”是两件事。取得合格数据后仍需执行冻结协议，正确数和分母均以实际预测计数；低于目标时应报告未达标。

## 目前 40 个 AT&T 身份的特殊光照照片

[官方 AT&T 说明](https://www.cl.cam.ac.uk/research/dtg/attarchive/facedatabase.html)只提供 40 人每人 10 张，包含部分光照、表情、眼镜变化。官方没有提供这 40 人标注齐全的夜间近红外、夜间低照度和强逆光套件。已下载的 gallery/query 来自这同一批 400 张原图，补边转换不产生新的真实光照采集。

使用其他公开库时，要从该库自己的人物建立注册图库，再使用其同身份查询。AT&T 的 s01 与其他库的 subject01 不代表同一个人。原有演示库无需删除；研究实验使用明确隔离的图库、标签和协议。

## 新找到的无需申请候选：MR-NIRP driving

- [Rice 官方入口](https://computationalimaging.rice.edu/mr-nirp-dataset/)
- [官方公开 Google Drive 文件夹](https://drive.google.com/drive/folders/1U3fzIOESmaBAyikGF0cKI2wW3YK8JqCK)
- [官方 README](https://cpb-us-e1.wpmucdn.com/blogs.rice.edu/dist/3/6742/files/2021/01/MR-NIRP-Car_README.pdf)

官方说明包含白天/夜间的 RGB 与 940/975nm 主动近红外视频。已实际读取公开目录和 Subject16 的记录目录；例如 subject16_driving_still_940 中 NIR.zip 显示约 3.91 GB、RGB.zip 约 2.02 GB。本轮通过 HTTP Range 读取两份公开 ZIP 的目录并固定提取 4 张原始 PGM（1 张参考、3 张查询），不必下载两份合计约 7.8 GB 的完整归档。逐帧通过 ZIP CRC 和 SHA-256 校验，保留原始 PGM；整份归档未下载，因此没有整包 SHA-256，不声称整库已下载。

该库用于生理信号研究，转为身份识别协议前必须核对身份、夜间序列、不同录制记录、原始 10bit 图像解析与使用条件。README 明确 Subject2 与 Subject16 是同一人，不能当两个人或拆成相互独立的未知校准/测试身份。缺少强逆光条件说明的片段不能仅凭像素变暗就标为强逆光。

获取后，完整保留采集序列标识。不能把同一段视频相邻帧分到注册、校准、测试三组，也不能把大量相邻帧视为大量独立人员。

## 已下载的小包在哪里，如何演示

整理包：`/home/zns/3_LumiFace/datasets/mr_nirp_night_demo.zip`。

- `gallery/MRNIRP_002`：1 张固定参考图，来自 small_motion_940 录像。
- `query/MRNIRP_002`：3 张固定查询图，来自 still_940 录像。
- `provenance.json`：原始成员路径、身份别名、校验摘要、取样规则与引用。

PNG 采用统一的 16bit 全范围到 8bit 固定缩放，没有使用 AI 改光或局部对比度增强来制造测试场景。原图在 `datasets/raw/mr-nirp-night-sample` 保留。复现：

```bash
cd /home/zns/3_LumiFace
.venv/bin/python scripts/fetch_mr_nirp_night_demo.py
```

Windows 解压后，网页批量导入只选择 `gallery`，将身份注册为 MRNIRP_002；查询从 `query/MRNIRP_002` 取图，不能把它指定为某个 AT&T 人员。身份确认阈值 0.45 仅用于功能排练。

真实模型对五种方法逐一检查全部 3 张固定查询：每种方法均为 2 张成功匹配、1 张未检测到人脸。失败图完整保留，没有按模型结果删图或换图。原始组两张成功图相似度约 0.856、0.870；自适应组约 0.861、0.881。详细记录在 `work/public-source-review/night-sample-test.json`。

这仅为 **1 人、不同录像、未独立校准、没有未知身份** 的小规模功能检查，不是 95% 夜间目标验收；同次采集的不同录像不自动证明独立会话。

## 其他已核查来源

| 来源 | 能验证什么 | 不能替代什么 |
|---|---|---|
| 本机 CBSR-NIR | 真实近红外研究协议 | 官方夜间与独立会话证据不足，不能直接认定夜间 95% |
| 本机 Yale B | 同身份真实受控光照变化 | 不具主动近红外，短时受控序列不直接替代独立实景验收 |
| [DARK FACE](https://flyywh.github.io/CVPRW2019LowLight/) | 真实夜间低光人脸检测，有框标注 | 官方描述未提供配套跨图身份识别标签，不能直接算已知人员身份确认率 |
| [SCface](https://www.scface.org/) | 有同身份可见光和 IR 夜视采集协议 | 需机构申请与正式签署，不满足用户无需申请限制 |
| [MCXFace](https://zenodo.org/records/7309673) | 多模态、不同会话及光照 | 文件 Restricted，需机构签署申请，不满足直接下载限制 |
| [IIT Delhi Near IR](https://www4.comp.polyu.edu.hk/~csajaykr/IITD/Database_Face.htm) | 有跨阶段近红外身份采集说明 | 下载需申请确认邮件，不满足直接下载限制 |

## 完成三项验收仍需要的证据

1. 夜间主动近红外 ≥95%：明确的夜间及主动补光记录，同身份图库/查询、独立录制与已知/未知身份标签。
2. 强逆光 ≥90%：真实背后强光场景及其光源/采集说明，同身份正常参考与独立逆光查询。不能用侧光或软件暗化替代。
3. 综合 ≥95%：正常、真实夜间低照度、强逆光均有样本，按正确总数/已知查询总数计算，不平均三个场景百分比。

目前未找到并取得足以覆盖上述全部条件的直接下载数据组合。尚未完成的工作必须继续保留为未验证；不使用 AI 改光、灰度滤镜或随意合并不同人物来补齐目标。
