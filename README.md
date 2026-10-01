# Minecraft 像素皮肤 Skill

让 AI Agent 按参考图逐格制作、修改和检查 Minecraft `64×64` 像素皮肤。适合想拥有自己皮肤、还不熟悉 UV 展开和像素绘制的新手。

这个 Skill 提供制作流程、眼型模板、像素工具和审阅页工具。你描述角色、提供参考图，Agent 绘制原生皮肤、检查基础层与外层，并输出预览供你调整。

**目前只在 Codex 中进行过测试验证。** 可以让豆包、Qoder 等具有文件读写和代码执行能力的 Agent 阅读并尝试使用，但本仓库未验证这些平台；具体成品取决于模型能力、参考图和执行环境。只有聊天或出图能力的平台，可能需要你另行运行工具。

Skill 本身不收费；Agent 服务、模型调用和平台额度以各平台实际规则为准。无需购买额外绘图软件，本仓库不要求接入指定的付费模型。

## 它能做什么

- 根据角色参考制作原生 `64×64 RGBA PNG`，明确 Slim（细臂）或 Classic（普通手臂）。
- 使用已确认的眼型结构，按角色参考调整瞳色、眼缘、发型和服饰。
- 修改已有皮肤，保留原图，记录实际改变的像素。
- 检查透明度、UV 有效区、眼部遮挡和模板保护区。
- 生成基础层、外层及叠加图，制作可旋转的本地 3D 审阅页。

工具按原生像素操作，不能把高清插画整体缩小后当成皮肤成品。浏览器里的动作和旋转用于审阅，皮肤本身仍是静态 PNG。

## 安装到 Codex

可以把下面的话发给 Codex：

```text
使用 skill-installer，安装 https://github.com/SuiSuiNian721/minecraft-pixel-skin
这个仓库根目录中的 Skill，名称为 minecraft-pixel-skin。
```

也可以使用 Git 克隆到自己的技能目录。Windows PowerShell 7 示例：

```powershell
$skillDestination = Join-Path $env:USERPROFILE '.agents\skills\minecraft-pixel-skin'
if (Test-Path -LiteralPath $skillDestination) {
    throw '目标目录已经存在，请先检查已有版本，避免覆盖。'
}
git clone 'https://github.com/SuiSuiNian721/minecraft-pixel-skin.git' $skillDestination
```

安装后在 Codex 中选择或输入 `$minecraft-pixel-skin`。如果技能列表没有更新，重启 Codex。目录位置和调用方式见 [OpenAI 官方 Skills 文档](https://learn.chatgpt.com/docs/build-skills)。

## 新手使用方法

1. 准备清晰的角色参考图，尽量提供正面、背面，说明发色、瞳色、服装和配饰。
2. 告诉 Agent 使用本 Skill，明确细臂或普通手臂、眼型及想保留的特征。
3. 查看分层图和多视角预览，提出具体修改，例如“背后的发尾再长一格”。
4. 取走最终的原生 `64×64 PNG`，在 Minecraft 的皮肤入口选择匹配的手臂模型，并检查游戏内效果。

可以直接复制这段提示词，再附上自己的参考图：

```text
使用 $minecraft-pixel-skin，按我提供的角色参考制作 Minecraft 皮肤。
使用 Slim 细臂模型和 A 眼型，保留参考中的发型、配色、服装与配饰。
先读取 SKILL.md 和角色制作说明，从模板目录读取已批准的冻结版本。
不要把高清图片直接缩小成皮肤，也不要覆盖原文件。
请交付原生 64×64 RGBA PNG、分层图和可旋转的 3D 预览。
检查正面、侧面、背面与基础层；没有做过的游戏内验证请明确说明。
```

在其他 Agent 中，把第一句改成“读取并使用这个文件夹中的 SKILL.md”，并提供完整文件夹，而不是只复制一个 Markdown 文件。工具执行所需的依赖可交由 Agent 检查和配置。

## 眼型模板

| 眼型 | 结构 | 正式模板 |
| --- | --- | --- |
| A | 两格高虹膜；外眼角上下两段可分别配色 | [A 1.0.0](assets/templates/eye_A/versions/1.0.0.json) |
| B | 一格高虹膜，眼型更窄 | [B 1.0.0](assets/templates/eye_B/versions/1.0.0.json) |
| C | 闭眼线，不绘制虹膜或眼白 | [C 1.0.0](assets/templates/eye_C/versions/1.0.0.json) |

眼型固定的是像素结构。瞳色、发型和刘海应依照当前角色参考适配，指南中的示例发型不是每个角色都要套用的发型。

目录中共登记 36 个部件入口，当前正式可用的是 A/B/C 三项眼型；其余 33 项仍待重建，不能当作现成模板使用。`template.json` 保留历史候选，正式制作以 [模板目录](assets/templates/index.json) 指向的冻结版本为准。

## 工具与验证

像素工具需要 Python 3.10+ 和 Pillow。进入本仓库后：

```powershell
python -m pip install -r requirements.txt
python scripts/skin_tools.py catalog --index assets/templates/index.json
python -m unittest discover -s tests -v
```

若要自动截取浏览器多视角，还需要 Node、Playwright、Sharp，以及可用的 Chromium 或 Edge。具体命令、配色格式和检查边界见 [工具与验证](references/tools-and-validation.md)。

自动像素检查、浏览器预览和游戏内效果是不同的验证环节。通过像素检查不代表角色一定像参考，也不保证所有客户端或模组的表现一致。

## 文件结构

```text
SKILL.md                 Agent 的制作入口
agents/openai.yaml       Codex 技能名称与提示词
references/              模板制作、角色制作和工具说明
scripts/                 像素工具与审阅页工具
tests/                   像素约束测试
assets/templates/        模板目录、历史候选与冻结版本
assets/fixtures/         工具复现所需的演示样本
assets/sources/          指南与精确提取所需的参考素材
assets/vendor/           本地 3D 渲染库及许可说明
```

发布副本移除了历史记录中的私人称谓、聊天原句和本机路径；冻结模板的像素定义、配色、保护区及其哈希保持不变。历史审阅记录的范围见 [发布说明](docs/publication.md)。第三方渲染库的许可说明保留在 `assets/vendor/`；参考素材的原有署名与来源说明保持原样。
