# 工具与验证

## 运行环境

Python 3.10+ 与 Pillow；`capture_review.cjs` 另需 Node、Playwright、Sharp 和本地 Chromium/Edge。优先通过 Codex 的 `load_workspace_dependencies` 获取当前运行库路径，不假设系统 `python` 指向正确环境。PowerShell 设置 `$env:PYTHONUTF8 = '1'`，避免中文日志编码错误。

以下命令中的 `$skillRoot` 为本 SKILL.md 所在目录；`$pythonPath`、`$nodePath` 和 Node 包路径由当前运行环境发现。Windows 正式命令使用 PowerShell 7。

## 精确提取与组合

```powershell
& $pythonPath (Join-Path $skillRoot 'scripts\skin_tools.py') inspect --source 'E:\当前角色\原图.png' --model slim --face head.front --id current_face --output 'E:\当前角色\审阅\原图正脸.json'

& $pythonPath (Join-Path $skillRoot 'scripts\skin_tools.py') compose --source 'E:\当前角色\原图.png' --model slim --template (Join-Path $skillRoot 'assets\templates\eye_B\template.json') --palette 'E:\当前角色\第二种角色眼睛配色.json' --purpose review --output 'E:\当前角色\审阅\第二种角色眼睛候选.png'
```

配色 JSON 为颜色键到 RGBA 的映射，例如：

```json
{"I":[218,90,123,255],"J":[252,167,195,255],"S":[255,244,238,255]}
```

未知颜色键、改变 Alpha 的换色、缺少模板声明的必需颜色绑定会被拒绝。第一种角色眼睛的 `U/V` 分别为外眼角上、下两段颜色，按当前参考独立配色，不全随 `L` 染黑。两种角色眼睛模板不含发色或 `H`，外层全部 KEEP；基础层须逐格识别旧眼部与实际发丝后再组合，不能把 y=4 的 x=1、6 等固定位置一律保留或恢复肤色，冲突用角色变体。正式制作默认 `--purpose production`，未批准模板会被拒绝；不要自行改审核状态。

`compose` 输出原生 PNG 与 `.manifest.json`，包含模板哈希、版本、配色、源图哈希、变化坐标、遮挡例外、允许的 Alpha 及回读结果。已有输出路径会被拒绝，使用新版本文件名。

`compose` 与 `validate` 均支持 `--exceptions`、`--allowed-alpha`，分别接收同格式的 JSON 文件，见下方说明。只有当前参考或已选部件实际需要时才传入，例如在上述组合命令中添加 `--exceptions 'E:\当前角色\遮挡例外.json' --allowed-alpha 'E:\当前角色\允许透明度.json'`。

## 单独验证

```powershell
& $pythonPath (Join-Path $skillRoot 'scripts\skin_tools.py') validate --source 'E:\当前角色\审阅\第二种角色眼睛候选.png' --model slim --template (Join-Path $skillRoot 'assets\templates\eye_B\template.json') --overrides 'E:\当前角色\按模板配色.json' --output 'E:\当前角色\审阅\像素检查.json'
```

`validate --overrides` 使用模板 ID 分组，格式为 `{"eye_B":{"I":[218,90,123,255]}}`，与 `compose --palette` 的单模板格式不同。应采用候选清单中实际使用的颜色、遮挡例外和允许的 Alpha；否则检查器会把合法换色或参考要求的遮挡判断为违规。

保护区中未声明例外的外层 Alpha 非零会报 `eye_occluded`；基础面透明报 `base_alpha`，无效 UV 区绘色报 `unused_uv`，模板主动绘制的颜色改变报 `template_pixel_changed`。绘制眼缘不等于要求每格都完全露出：外伸上缘和外眼角允许被参考发型部分遮住，不应全部加入强制透明保护区。额外遮眼记录依据与准确例外，不自动剪发。外层例外不能替代基础层适配；参考发丝与眼型冲突时，按当前角色变体验证。

普通外层默认 Alpha 只取 0/255。半透明镜片使用 `--allowed-alpha` 或模板内 `allowed_alpha`，例如：

```json
[{"face":"head.front","layer":"outer","xy":[1,5],"values":[128]}]
```

这只允许指定位置的指定数值。基础面仍不允许半透明。眼部有意遮挡用 `--exceptions`，格式：

```json
[{"face":"head.front","xy":[1,5],"reason":"当前权威参考中的刘海遮住此格；记录参考路径、哈希或图中位置","authorization":"用户指定该角色参考及保留发型的实际消息记录"}]
```

理由和授权字段须填入实际参考与已有选型/授权记录，不能照抄示例假装用户同意。先明确角色适配的具体像素再锁定；参考清楚且已有制作授权时，无需为普通发型适配重新批准整个通用眼型模板。例外只放行列出的坐标，不关闭其他保护检查。

## 分层与立体审阅

重新生成包内第一种角色眼睛与第二种角色眼睛的比较：

```powershell
& $pythonPath (Join-Path $skillRoot 'scripts\render_review.py') --project (Join-Path $skillRoot 'assets\fixtures\character-eyes-review-project.json') --output 'E:\当前任务\眼睛审阅新版本'
```

指南发型独立保存：第一种角色眼睛用 `assets/fixtures/guide-a-hair.json`，第二种角色眼睛用 `assets/fixtures/guide-bc-hair.json`；各示例卡显式声明自己的引用，例如第二种角色眼睛：

```json
{"template":"assets/templates/eye_B/template.json","example_overlays":["assets/fixtures/guide-bc-hair.json"]}
```

`card.example_overlays` 是相对 Skill 根目录的路径字符串数组，只能用于 `project.fixture` 示例审阅。含 `project.source` 的角色项目会拒绝该字段；发型不能从指南示例自动继承。

制作角色候选的最小项目 JSON：

```json
{
  "title":"当前角色 · 第二种角色眼睛候选",
  "subtitle":"保留当前角色发型；检查第二种角色眼睛与参考要求的组合",
  "source":"E:/当前角色/原图.png",
  "model":"slim",
  "focus":"head",
  "cards":[{"template":"assets/templates/eye_B/template.json","label":"第二种角色眼睛候选","detail":"一格高虹膜；发型形状、发长、分缝、刘海与配饰依据当前参考。"}],
  "palettes":[{"id":"pink","label":"角色粉瞳","overrides":{"I":[218,90,123,255],"J":[252,167,195,255],"S":[255,244,238,255]}}]
}
```

`source` 为绝对路径或相对项目 JSON 的路径；`template` 为包内相对路径或明确的绝对路径。用 `source` 时模板声明的必需颜色必须手动绑定；两种角色眼睛模板不要求发色绑定。用包内 fixture 时工具可根据对应颜色用途绑定示例颜色。`focus` 为 `head` 或 `full`。项目可声明 `allowed_alpha`、`exceptions`，格式与上文相同。

渲染命令同上，只更换 `--project`。输出目录必须不存在。生成原生 PNG、逐格图、本地 `眼型模板审阅.html` 与检查清单；审阅页自带库与图像，不依赖在线资源。

```powershell
& $nodePath (Join-Path $skillRoot 'scripts\capture_review.cjs') 'E:\当前任务\眼睛审阅新版本' 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
```

若 Node 包不在默认查找路径，先把 `$env:NODE_PATH` 指向已发现的包目录。浏览器路径只在本机确认存在后使用，也可以省略以使用 Playwright 配置的 Chromium。

脚本检查模型、外层开关、配色切换、原生 PNG 下载、页面脚本错误和固定 RGB 色块，并截图正/斜/另一侧/背/顶以及仅基础层。实际查看截图后再宣称视觉检查完成。当前随包渲染库是 skinview3d 3.4.2，MIT 许可在 `assets/vendor/skinview3d-LICENSE.txt`；特定色彩设置不应直接移植到其他渲染器版本。

## 验证边界

修改母版版本或状态后，运行目录一致性检查，避免目录仍指向旧版本：

```powershell
& $pythonPath (Join-Path $skillRoot 'scripts\skin_tools.py') catalog --index (Join-Path $skillRoot 'assets\templates\index.json')
```

运行 `tests/test_skin_tools.py` 检查关键像素规则。对具体任务还要核对真实输出，而不是只运行测试。自动检查不能证明角色像不像、接缝是否自然或某个模组中的效果；未进行的游戏内检查必须保持 false。

基础有效像素面积：Slim 为 1568，Classic 为 1632；两种模型各有 36 个面，外层同样计数。面矩形由工具中的单一 UV 映射生成。局部坐标都按 PNG 方向，最终立体朝向用模型确认，尤其注意底面和角色左右。
