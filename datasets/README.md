# 数据集导入协议

将 `manifest.json` 放到 ZIP 根目录，图片路径相对 ZIP 根目录。图片须 JPEG/PNG，框坐标对应 EXIF 方向纠正后的图像。每个框采用 [x1,y1,x2,y2]，单位像素，不能超出图像边界。

```json
{
  "name": "真实光照测试集",
  "split": "test",
  "source": "采集者/数据集来源；设备、模态、照明条件、采集会话与授权记录位置",
  "license": "获得的许可或自采受试者同意信息",
  "real_capture": true,
  "items": [
    {"file":"images/known.png","scene":"backlight","capture_id":"test-session-01",
     "faces":[{"bbox":[20,30,180,220],"person_id":1,"subject":"subject-A"}]},
    {"file":"images/unknown.png","scene":"normal","capture_id":"test-session-02",
     "faces":[{"bbox":[15,25,170,215],"person_id":null,"subject":"unknown-test-B"}]},
    {"file":"images/no_face.png","scene":"low_light","capture_id":"test-session-03","faces":[]}
  ]
}
```

- `split` 为 calibration 或 test。训练/策略开发数据不导入最终评估集。
- `person_id` 必须对应真实已注册身份编号；未知身份必须 null，subject 是稳定的受试者匿名标识。
- `scene` 支持 normal、low_light、backlight、infrared、overexposed、uneven。
- `capture_id` 标识真实采集会话；同一视频/同一连拍中的近邻帧应使用同一个会话编号，不可为绕过检查修改编号。
- 每份 ZIP 最多 500 图片、压缩 ≤100 MB、声明解压总量 ≤256 MB；单图 ≤12 MB、≤1600 万像素。
- 拒绝重复像素图像、跨划分重复会话、与注册重叠的像素/会话、跨校准测试复用未知身份。
- 真实/合成标志和身份标签属于数据责任人的声明，系统无法从像素证明真伪；应保留原始采集日志供审查。
- 同一张原图的压暗、裁剪和压缩变体属于同源派生，不能通过改名视为独立采集。精确像素哈希不能识别所有近重复，仍需人工协议审查。
- 红外仅用于真正红外采集。普通 RGB 变暗不算红外。

前端提供空的标注清单下载模板，不含真实数据。先注册 gallery，再导入 calibration/test；已知身份可以在 gallery 和查询集出现，必须是不同采集。未知身份在校准与测试间互斥。

导入时服务自动将已知身份编号与原注册时间绑定。删除后重建身份会使旧标注失效，即使旧 SQLite 表复用了数字编号也会拒绝执行。旧版本导入记录若缺少该绑定，应核实编号后重新导入。

## 可用于网页批量注册的公开身份样例

已准备 `datasets/att_faces_demo/gallery`（40 人、120 张参考照片）及 `datasets/att_faces_demo/query`（280 张查询照片）。原始来源为剑桥托管 AT&T / ORL 数据，提供匿名身份编号，不是真实姓名。请在“身份库管理 → 批量导入身份”选择 gallery；此文件夹不是实验评估用标注 ZIP。来源、格式转换与操作详见 `docs/web-identity-import.md`。


## 模拟复杂光照方案（2026-10-17）

主包 `att_lighting_simulation.zip`，Windows 解压后 `gallery` 用于身份注册，`query` 用于四种场景演示。全部标记为模拟，不能替代实景验收。数据与实验说明见 `docs/simulated-lighting-data.md`。CBSR、Yale 的原始归档缓存已清理，保留来源摘要和既有报告，可按原脚本重新下载。

当前三类演示包 `att_lighting_three_scenes.zip` 按网页的三种算法整理：逆光_CLAHE、光照不均_Retinex、低照度_Gamma。新生成光照不均输入；不包含伪红外分类。详见 `docs/three-scene-demo.md`。原有两个下载包与研究报告保留。
