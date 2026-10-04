# CapCut 实验支持

已在 Apple Silicon Mac 上完成 CapCut 草稿构建、独立副本编辑和本地原生 MP4 导出。
这不是官方 SDK，也不是任意 CapCut 版本兼容承诺。默认命令仍使用剪映；
每次 CapCut 调用须明确选择 `--app capcut`，或设置 `JIANYING_HEADLESS_APP=capcut`。

## 精确环境

| 项目 | 已验证值 |
| --- | --- |
| 应用 | `/Applications/CapCut.app`，9.5.0 build 286 |
| 平台 | Apple Silicon arm64，macOS 26.6.2 |
| Bundle / Team | `com.lemon.lvoverseas` / `22MMUN2RN5` |
| 引擎 SHA-256 | `16d31a486390aa027cec024a6e7752f0cfa9576a48d097c5f6438f90534a6218` |
| 原生配置 | `capcut-headless-macos-9.5.0-286` |
| 草稿格式 | 明文 JSON，`new_version=187.0.0` |
| 草稿根目录 | `~/Movies/CapCut/User Data/Projects/com.lveditor.draft` |
| 工具 | Python 3.9+、FFmpeg / ffprobe、Apple clang 21、macOS SDK 26.5 |

版本、build、库指纹和签名检查仍然启用；不修改官方库，不放宽身份验证。
CapCut 明文草稿不需要 `tools/build_native_codec.py` 的剪映加解密组件。
原生导出仍需匹配的编译工具链；Windows FFmpeg 后端不是 CapCut 草稿后端。

## Agent Skill

新会话可安装并使用 [hypit-capcut](../skills/hypit-capcut/README.md)。
它明确选择 `--app capcut`，检查本地字体依赖，并区分 Hypit 预渲染画面和
CapCut 独立可编辑图层；参考中保留已验证的八秒聊天示例及计划模板。
Skill 不包含引擎或通用 Hypit 工程转换器，不因被调用而授权付费生成或云端上传。

## 开始使用

在仓库根目录运行：

```bash
python3 tools/start_here.py --app capcut check
python3 skills/yichen-jianying-edit/scripts/headless_draft.py --app capcut doctor
python3 tools/start_here.py --app capcut build --source /absolute/path/to/video.mp4
```

向导仅生成独立的两秒视频/文字草稿，不自动登记或导出，后续命令保存在该任务的
`next-steps.md`。素材须有权使用。默认草稿目录应先由 CapCut 正常创建并保存一个工程，
然后正常退出；自定义草稿根目录未验证。

使用完整计划时沿用[计划格式](../skills/yichen-jianying-edit/references/headless-macos.md)：

```bash
python3 skills/yichen-jianying-edit/scripts/headless_draft.py --app capcut build \
  --plan /absolute/path/to/plan.json --out "$PWD/work/capcut-build"
python3 skills/yichen-jianying-edit/scripts/headless_draft.py --app capcut verify-build \
  --build "$PWD/work/capcut-build"
```

保存当前工作、完全退出 CapCut 后，再进行本机首页登记：

```bash
python3 skills/yichen-jianying-edit/scripts/headless_draft.py --app capcut publish \
  --build "$PWD/work/capcut-build" --audit "$PWD/work/capcut-publish"
```

`publish` 不是互联网发布。它只新增本任务草稿，并保留首页索引的 inode 和 xattr；
原有草稿不覆盖。事务备份与意图日志保存在 audit 目录。仍需实际打开、播放、保存、
退出、冷重开，再退出 CapCut 回读检查：

```bash
python3 skills/yichen-jianying-edit/scripts/headless_draft.py --app capcut verify \
  --build "$PWD/work/capcut-build" --report "$PWD/work/capcut-after-save.json"
python3 skills/yichen-jianying-edit/scripts/headless_draft.py --app capcut export \
  --build "$PWD/work/capcut-build" --out "$PWD/work/capcut-export"
```

导出只使用已验证的冻结快照，不含后来在 UI 中的修改。输出为 `render.mp4`，
H.264/AAC，必须通过帧数和完整解码检查。build、audit、export 目录须为全新的工作目录，
不能位于实时草稿树中。原生渲染在隔离进程内运行，不联网或读取账号数据库。

登记中断后先保留现场。`resume-publish` 用于继续已复制但尚未完成登记的任务；
若索引发生可识别的部分写入，可对原 audit 执行：

```bash
python3 skills/yichen-jianying-edit/scripts/headless_draft.py --app capcut recover-capcut-index \
  --audit "$PWD/work/capcut-publish"
```

恢复会检查备份、JSON、原 inode 与当前字节，不覆盖其他写入者产生的有效索引。
恢复索引不删除已经复制的草稿。程序正常保存的系统安全属性保持不变。

## 独立副本和口播流程

[副本编辑格式](../skills/yichen-jianying-edit/references/edit-existing-macos.md)保持不变：

```bash
python3 skills/yichen-jianying-edit/scripts/headless_draft.py --app capcut edit inspect \
  --draft /absolute/path/to/capcut-draft --out "$PWD/work/capcut-inspection.json"
python3 skills/yichen-jianying-edit/scripts/headless_draft.py --app capcut edit build \
  --plan /absolute/path/to/edit-plan.json --out "$PWD/work/capcut-edit-build"
python3 skills/yichen-jianying-edit/scripts/headless_draft.py --app capcut edit verify-build \
  --build "$PWD/work/capcut-edit-build"
python3 skills/yichen-jianying-edit/scripts/headless_draft.py --app capcut export \
  --build "$PWD/work/capcut-edit-build" --out "$PWD/work/capcut-edit-export"
```

仅读取明确指定的本地草稿；修改发生在新副本，不写原工程。
口播计划编译、SRT/文字稿及试听 WAV 仍由 `scripts/edit_plan.py` 完成，
将生成的 **compiled.json 文件**而非目录交给转换入口：

```bash
python3 skills/yichen-jianying-edit/scripts/headless_draft.py --app capcut from-compiled \
  --compiled /absolute/path/to/compiled.json --name capcut-speech \
  --out "$PWD/work/capcut-speech.plan.json"
```

再用 `build` / `verify-build` / `export`。ASR 依赖外部转写执行器、凭据与单独授权；
本次未调用 ASR 服务。剪映缓存音效身份不适用于 CapCut，`cached-sound` 和
含这些 sfx 的转换会拒绝；本地音频文件可用于计划的 audio 轨道。

## 实测范围

| 功能 | 本机验证情况 |
| --- | --- |
| 基础视频、文字、源音轨 | 构建、登记、原生播放保存、退出冷重开回读；基础导出 120/120 帧 |
| 多轨 / PIP / 音量 / 透明度 | 冻结快照导出、完整解码；合成混音 RMS 增益检查；未逐项完成 UI 冷重开 |
| trim / 固定速度 / 素材替换 | 新建及副本路径实测；少一帧限制见下方 |
| PNG / JPEG / GIF / HEVC 输入 | 原生 H.264 导出、完整解码；不是 HEVC 输出支持 |
| 线性关键帧 | x/y、缩放、旋转、透明度、音量；X-only 保留静态 Y 的像素检查 |
| 本地字体 | 应用内静态 OTF 新建与副本替换；其他字体仍需按字体规则检查 |
| 帧率 | 24 / 25 / 30 / 50 / 60 fps 合成样本 |
| 遮罩 | circle / rectangle / line / mirror / star / heart；实际形状及像素覆盖检查 |
| 转场 | `cross-fade`；原生 UI 本地导出及 headless 中点混合像素检查 |
| 视频特效 | `subtle-shake`；原生 UI 导出、静态图对照和帧间运动检查 |
| 副本结构操作 | 文字/字体替换、轨道重命名、片段复制/删除、变速、transform/volume/opacity |
| 复合片段 | 可编辑子时间线的离线修改和冻结快照导出；首页登记继续拒绝 |
| 编译口播计划 | 时间映射、SRT/文字稿、试听 WAV、转 CapCut 计划、原生导出 |

资源目录为独立的 `engine/capcut-resource-catalog.json`，只记录本机取得的包身份及哈希，
不随源码分发资源字节。缺少本机包或字节不匹配时明确失败，不从网络自动补齐。
资源须先通过 CapCut 正常选择、保存并在既有授权范围内使用。

`cross-fade` 不等同于剪映 `dissolve`；CapCut 中名为 Dissolve 的资源观察到 Pro 标记，
未接入。`subtle-shake` 不等同于 `light-shake`，参数仅为 `speed`、`blur`（0..1），
默认 1/3、0.5。剪映轻微抖动仍保留原 `range`、`speed`。不得跨产品混用资源或导出快照。

## 已知限制和安全边界

- 原生导出存在间歇性末尾少一帧：trim / 固定变速曾出现 59/60，
  24 fps 出现 95/96，25 fps 出现 99/100，心形遮罩出现 119/120，口播样本出现 89/90。
  严格校验会拒绝，不静默补帧、放宽或掩盖。同一快照用全新输出目录再次显式导出
  曾达到完整帧数，但根因未解决，也不自动重试。
- 每个实际输出仍需查看画面、切口、字幕并试听音频；非空像素、完整解码不等于完整内容验收。
- Cross Fade 可能叠加重叠区源音频；未做隐式增益修正，也未套用剪映样本的具体 dB 测量。
- 不支持任意效果、滤镜、花字、动画模板、曲线变速、云端草稿、在线资源注册或账号权益获取。
- 复合片段没有可靠原生保存/冷重开验收，不能作为保存可靠的嵌套草稿交付。
- GUI 导出窗口可能默认开启 “Sync exported videos to space”；本次已关闭，仅本地导出。
  headless 不调用 GUI，也不分享或同步到云端。
- 没有修改官方程序、解除安全属性、绕过会员限制、读取账号库或上传现有项目。
- 无 Pro 标记或渲染成功不证明商用、会员、持续账号或再分发授权。
  仓库的[非商业许可证](../LICENSE)、应用协议和素材许可分别适用。

## 重现测试

关闭 CapCut，且本机具有上述匹配资源后，在仓库根目录运行：

```bash
python3 tools/check_package.py
python3 -m unittest discover -s tests
python3 tools/capcut_smoke_test.py
python3 tools/capcut_workflow_test.py \
  --draft "$HOME/Movies/CapCut/User Data/Projects/com.lveditor.draft/capcut-headless-basic-20261004"
```

workflow 测试仅用于自己创建的 `capcut-headless-` 合成测试草稿，不能拿真实用户工程代替。
每轮证据写入独立的 `work/capcut-smoke-*` / `work/capcut-workflow-*`；失败结果也保留。
基本 UI 验收仅针对本机合成草稿，不代表所有编辑操作均经过 UI 保存验收。

2026-10-04 本机记录：160 个单元测试及源码包装检查通过。完整原生矩阵首轮 21/24，
24 fps、25 fps、心形遮罩因末尾少一帧失败；同快照在全新 `export-retry` 目录
分别得到 96/96、100/100、120/120 帧，且完整解码及画面检查通过。
另一次资源专项矩阵 9/9（含静态图对照），Subtle Shake 帧间平均像素差 3.5535；
多轨合成音频相对原音 RMS 比值 0.559084，与 0.25/0.5 增益匹配。
副本/复合/口播流程首轮 7/8，口播快照首次复测仍为 89/90，第二次显式复测
得到 90/90 帧并通过完整解码。其他七项未重试；原素材、原草稿和构建快照未改动。
原始失败不改为成功，也不以复测证明间歇问题已经解决。
