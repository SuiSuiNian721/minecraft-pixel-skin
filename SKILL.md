---
name: minecraft-pixel-skin
description: Use when creating, adapting, or checking Minecraft 64x64 pixel skins, reconstructing guide-based eye or accessory templates, or explaining their base and outer pixel layers.
---

# Minecraft 像素皮肤

以逐格母版固定眼型或部件结构，以当前角色参考决定配色、发型和组合。适用于静态 `64×64 RGBA PNG`；明确使用 Slim 或 Classic。工具按原生像素操作，不把高清插画整体缩小当作皮肤成品。

## 选择工作入口

- **建立/修正模板**：读 [模板制作](references/template-authoring.md)，先查看 `assets/templates/index.json` 的来源、版本和就绪状态。
- **制作/修改角色**：读 [角色制作](references/character-production.md)，读取当前原图与角色设定，沿用用户已明确的选型。
- **执行像素操作或验证**：读 [工具与验证](references/tools-and-validation.md)。脚本需要 Python + Pillow；立体截图另需 Node、Playwright 和 Sharp。

## 不可丢失的制作信息

1. 每个实际涉及的面必须明确基础层、外层、透明格、坐标、配色用途、保护区；从同一模板数据生成 PNG、分层图和清单。
2. `exact_png` 是原始像素提取；`reconstructed_from_guide` 是效果重建。看不到的底层不能声称精确还原。
3. 未确认模板只生成带 `review` 标记的候选。用户看过具体像素并确认后再冻结版本；已有选择与授权持续有效，不重复询问。若用户已明确接受候选制作，直接完成可审阅产物。
4. A/B/C 的眼缘包括上眼缘与外眼角，不补成无依据的闭合黑圈；A 的外眼角上、下两段 `U/V` 按当前参考独立配色，不全随眼睑 `L` 染黑。外层全部 KEEP，基础层先逐格识别源图语义：替换旧眼部，保留实际发丝，不能凭固定坐标认定头发或恢复肤色。发型依据当前参考，冲突用角色变体；明确变化格后锁定，无需重批整个通用模板。指南 A/B/C 发型只用于独立示例。
5. `.` 表示保留，`-` 表示清空外层，颜色键表示写入。允许刘海部分遮住底层延伸眼缘，不要求外眼角对应外层全透明。参考明确要求遮眼刘海或眼罩时，记录依据、准确允许区域与已有选型/授权；不要自动剪掉发型，也不能整体关闭眼部检查。
6. 保留原图，新文件名输出；局部修改核对变化坐标。二维叠加、立体预览和游戏内验证分别报告。

## 当前资源状态

指南目录包含 36 个入口。作者于 2026-09-11 查看 v07 睫毛分层图后确认 A/B/C，三者已分别冻结为 `assets/templates/eye_A/versions/1.0.0.json`、`eye_B/versions/1.0.0.json`、`eye_C/versions/1.0.0.json`，目录中 3 项可用于正式制作。像素定义与已确认候选完全相同；冻结文件记录确认依据、来源版本、哈希及 v07 的 Slim 双配色、文件和浏览器验证范围，游戏内未验证。原 `template.json` 保留历史候选，制作时读取目录指向的冻结版本。其他 33 个部件仍待重建；小璃正脸仅为精确提取样本，不能直接当作指南 A。

基础工具见 `scripts/skin_tools.py`；审阅页与分层图见 `scripts/render_review.py`；浏览器截图与颜色校准见 `scripts/capture_review.cjs`。每次交付包含可用 PNG、相关面的分层图、立体预览及采用的模板版本。皮肤制作不自动包含账号、启动器、联网设置或上传应用操作。
