# 界面参考与实现

查阅日期：2026-10-17。

## GitHub 参考项目

- [Tabler](https://github.com/tabler/tabler)，[官方预览](https://preview.tabler.io/)：实际打开预览检查了工具栏、统计信息、列表及间距。参考其明确的内容层次与统一控件尺度。
- [Vue Pure Admin](https://github.com/pure-admin/vue-pure-admin)：查阅 Vue 3 / Element Plus 后台项目与配置，参考常规后台导航、内容区和操作区的组织方式。
- [Vue Vben Admin](https://github.com/vbenjs/vue-vben-admin)：查阅其后台框架说明及组件体系，作为后台界面组织的补充参考。

本项目保留 Vue 3 / Element Plus，采用自行编写的布局与样式；以上链接用于说明设计参考来源。未使用参考项目的商标、头像、演示数据或截图作为界面素材。

## 当前实现

界面采用分组深色导航、白色工具栏与内容卡片、蓝色操作按钮，保留纯文字品牌。五个功能页面分别处理增强、检测、身份库、身份确认和实验评估；首页直接进入增强，模型状态放在需要它的页面标题旁。单图预览共用组件，实验对比集中在实验评估；移动端支持遮罩导航和长路径换行。

验证记录见 [verification.md](verification.md)。
