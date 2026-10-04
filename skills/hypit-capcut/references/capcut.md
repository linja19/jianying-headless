# CapCut 本地工作流

先定位核心项目，以下变量均替换为本次实际绝对路径。在该仓库根目录运行：

```sh
CORE="$PWD"
PY="$CORE/.venv/bin/python"
ENTRY="$CORE/skills/yichen-jianying-edit/scripts/headless_draft.py"
"$PY" "$ENTRY" --app capcut doctor
```

有可用 `.venv` 就复用。没有时选一个受控 Python 环境并检查需要的依赖，不能假定系统
Python 有 fontTools。本机聊天示例曾因系统 Python 缺少 fontTools 失败，改用已有
`.venv/bin/python` 后成功。没有本地字体的任务不强制新增字体依赖。

## 新建

按 [计划格式](../../yichen-jianying-edit/references/headless-macos.md) 准备
`jy14-headless-plan/v1`。时间单位为整数微秒，第一轨为从零开始的连续主视频轨，
其他素材、文字、音频在主轨时长内。所有媒体路径是本次有权使用的绝对路径。
支持的帧率为 24、25、30、50、60；Hypit 的其他有理帧率不能静默近似。

```sh
PLAN="/absolute/path/to/plan.json"
BUILD="/absolute/path/to/new-capcut-build"
"$PY" "$ENTRY" --app capcut build --plan "$PLAN" --out "$BUILD"
"$PY" "$ENTRY" --app capcut verify-build --build "$BUILD"
```

`build` 不登记实时草稿，CapCut 可运行；输出目录须不存在，且不能在实时草稿树中。
字体只接受经过工具检查的本地静态 OTF/TTF；原生字号不是 CSS px。
线性关键帧限制、源区间/速度条件、特效资源要求均以计划验证器与
[CapCut 支持范围](../../../docs/CAPCUT.md) 为准，不为通过检查移除用户选定效果。

## 本机登记与保存

确认用户工作已保存并正常退出 CapCut。不要强杀；若有无法保存的无关工作，先停在离线成果。
默认草稿根目录应已经由 CapCut 正常创建并保存过工程；自定义根目录未验证。

```sh
AUDIT="/absolute/path/to/new-capcut-publish-audit"
"$PY" "$ENTRY" --app capcut publish --build "$BUILD" --audit "$AUDIT"
```

只登记本次新草稿，保留原索引与其他项目。失败保留 audit，按
[登记恢复说明](../../../docs/CAPCUT.md) 判断 `resume-publish` 或 `recover-capcut-index`，
不要盲目再建同名项目、删除现场或覆盖索引。

在原生界面打开本次草稿，检查素材、画面、切口、文字和声音，播放、保存、正常退出。
冷启动重开并确认原生编辑控件，再退出后执行：

```sh
"$PY" "$ENTRY" --app capcut verify --build "$BUILD" --report "/absolute/path/to/new-after-save.json"
```

离线检查、成功登记、实际播放和保存重开是不同证据，不相互替代。

## 原生导出

用户要求成片或示例预览时，导出已经校验的冻结快照：

```sh
EXPORT="/absolute/path/to/new-capcut-export"
"$PY" "$ENTRY" --app capcut export --build "$BUILD" --out "$EXPORT"
```

输出为 `render.mp4`，H.264/AAC。检查 `expected_frames`、实际帧数、完整解码及实际内容。
间歇缺尾帧时保留失败结果；不补帧，不覆盖，不称检查已通过。
手工修改 live 草稿不会改变旧 build；需要这些修改时先创建并验证新的导出快照。
不使用 GUI 的云同步/分享路径代替本地导出。

## 已有草稿的独立副本

仅读取用户指定的源草稿，先 inspect，再按
[副本计划格式](../../yichen-jianying-edit/references/edit-existing-macos.md) 新建副本：

```sh
"$PY" "$ENTRY" --app capcut edit inspect --draft "/absolute/path/to/authorized-draft" --out "/absolute/path/to/new-inspection.json"
"$PY" "$ENTRY" --app capcut edit build --plan "/absolute/path/to/edit-plan.json" --out "/absolute/path/to/new-edit-build"
"$PY" "$ENTRY" --app capcut edit verify-build --build "/absolute/path/to/new-edit-build"
```

之后按本次要求登记或导出。复合片段仍只限实验性的离线修改和冻结快照导出，不登记为
已经保存可靠的嵌套草稿。CapCut 不使用剪映 cached-sound 身份；获授权的本地音频可单独导入。
