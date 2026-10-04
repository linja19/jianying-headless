---
name: hypit-capcut
description: 在匹配版本的 Apple Silicon Mac 上，用 Jianying Headless 构建 CapCut 草稿、编辑独立副本和原生导出 MP4，或将 Hypit 已完成的构建结果交给 CapCut 继续编辑。用于 Hypit + CapCut 示例、工程交接和本地原生出片；不用于 CapCut 网页版或通用无损 SVML 转换。
---

# Hypit + CapCut

使用本机 Jianying Headless 的 CapCut 后端。默认后端仍是剪映，每次调用都明确传入
`--app capcut`；不要把旧剪映 Skill 的默认命令或资源身份直接套用到 CapCut。
按用户本次要求交付草稿、成片或两者，不把历史示例的文案、音效和画幅变成默认偏好。

## 定位和检查

1. 解析本 Skill 的真实路径（安装可能是符号链接）。同仓时，核心项目是
   `skills/hypit-capcut/` 的上两级目录；独立安装时使用明确配置的
   `JIANYING_HEADLESS_ROOT`。确认其中存在 `engine/` 和
   `skills/yichen-jianying-edit/scripts/headless_draft.py`，不从其他私人项目猜路径。
2. 优先使用核心项目已有的 `.venv/bin/python`。没有时检查选定的 Python 环境；
   指定本地字体需要 `requirements-fonts.txt` 中的 fontTools，不能因为依赖缺失而
   删除 `font_path` 或悄悄换字体。运行入口的 `--app capcut doctor`。
3. 本机已验证的是 CapCut 9.5.0 build 286、Apple Silicon macOS。
   不匹配时停在离线准备阶段，不改固定版本、哈希或签名来通过检查。
   CapCut 明文草稿不需要剪映的 native codec；原生导出仍需要匹配工具链。

## 按任务读取

- CapCut 新建、已有草稿独立副本、登记与导出：读 [CapCut 工作流](references/capcut.md)。
- Hypit 生成或读取成片，然后交给 CapCut：读 [Hypit 交接](references/hypit.md)。
  请求无付费示例时可用其中的八秒聊天动画和 [计划模板](assets/chat.plan.template.json)。
- 支持范围和精确环境的权威记录：核心项目 [CAPCUT.md](../../docs/CAPCUT.md)。
  计划字段见 [计划格式](../yichen-jianying-edit/references/headless-macos.md)。

## 交接边界

优先复用用户选定的已完成 Hypit Build，而不是用当前源文件猜历史结果。
用公开 `hypit inspect/get` 导出实际使用的输出与依赖；不要遍历私人素材缓存或凭据。
一起核对 `Composition`、Timeline/ProgramSpace 中的帧率和时长，以及实际素材和字体。

HTML/CSS 浏览器程序、复杂排版和非线性动画可以预渲染为视频层。
其内部气泡、文字、图形不会因此变成 CapCut 原生可编辑对象。
基础素材、普通文字与线性关键帧只有显式映射并验收后才称为独立可编辑轨道。
当前没有随仓库提供的通用 Hypit-to-CapCut 转换器，也没有双向同步。

## 验收与交付

- 使用新草稿名和全新的工作目录；保留原素材、原草稿及人工修改。
  `publish` 是本机首页登记，不是互联网发布，执行时 CapCut 必须正常退出。
- 先 `build`、`verify-build`。需要成片时导出冻结快照，再查帧数、完整解码、
  实际画面及音频。已知导出可能间歇少一帧；保留失败，不补帧或放宽检查。
  重试只在本次请求允许且已说明失败后，使用新目录，限制次数并保留原记录。
- 可编辑草稿要在 CapCut 打开、播放、保存、正常退出、冷重开，再退出回读。
  GUI 用当前宿主提供的 GUI 工具；不可用时明确标记未完成，不能用离线检查代替。
- 付费生成、ASR、云端上传及在线资源获取不是此 Skill 的隐含步骤。
  确需使用时先确定本次范围与授权，不接入或读取无关账号。
- 交付成片或预览、草稿名、复现计划和验收结果，并明确哪些层可编辑。
  用户要求 token 时报告宿主可读的本次实际统计及截止时间；缓存输入包含在总输入中，
  推理包含在输出中，不能重复相加。无法读取时说明限制；Agent token 与生成服务用量分开。
- 核心项目的非商业许可、Hypit 的附加条件许可证、CapCut 协议及素材授权分别适用。
  技术出片成功不授予商用、会员或再分发权限。
