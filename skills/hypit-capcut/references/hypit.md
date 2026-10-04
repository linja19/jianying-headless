# Hypit → CapCut

## 先选模式

用户提供已完成 Build 时优先读取该 Build，不重生成素材。用该 checkout 的公开 CLI
检查输出并通过 `hypit get` 导出依赖；结果可能引用历史 Build 或外部文件，不能只复制
某个缓存目录。普通 Hypit Build Result 不等于已经自包含的媒体包。

两种交接必须明确区分：

- **渲染交接**：把已完成的视频作为 CapCut 主轨，另加原生文字、音频或画中画。
  HTML/CSS 动画内部仍是预渲染画面。
- **按项目转换**：检查选定 Build 的 `main.composition`、Timeline/ProgramSpace、素材与字体，
  显式把支持的图层映射为计划；没有通用转换器，不能声称任意 SVML 无损可编辑导入。

Composition 有画布和轨道，但帧率来自 Timeline/ProgramSpace。视觉区间使用半开帧范围，
元素可能有父级相对坐标，音频区间使用 48 kHz 样本；不要把数值直接当秒或画布像素。
有理帧率、源采样/循环、播放速度、复杂排版和非线性缓动需要逐项检查；不支持的能力
先报告，再按本次要求决定预渲染，不静默丢弃。

## 已验证的无生成模型示例

2026-10-04 在 Hypit 0.2.17、commit `4ff55cc7` 跑通
`examples/semantic-composition/chat.svrun`：540×960、30 fps、8 秒、240 帧。
聊天程序由 HTML/CSS 和帧驱动 JavaScript 绘制，不使用 WhisperX、生成配音、图像或视频模型。
示例文案中的 “whole scene editable” 指 Hypit 源组件，不代表 CapCut 内部图层可编辑。
不同 Hypit 版本应先读该 checkout 的示例 README 和 `package.json`，不把旧命令当兼容承诺。

本 Skill 不包含 Hypit。使用用户提供的 checkout；同工作区通常是核心项目的同级 `hypit/`，
先核对目录和仓库身份，不遍历无关项目。缺少时按本次授权取得公开
[Hypit 源码](https://github.com/hypit-ai/hypit)。

以下从 Hypit 根目录运行；0.2.17 要求 Node >=22.15，固定 pnpm 10.33.0：

```sh
npx --yes pnpm@10.33.0 install --frozen-lockfile --ignore-scripts
npx --yes pnpm@10.33.0 build:public-types
npx --yes pnpm@10.33.0 --filter @example/chat-scene build
node bin/hypit.mjs check examples/semantic-composition/chat.svml --workspace examples/semantic-composition
node bin/hypit.mjs programs prepare --runtime examples/semantic-composition/hypit.runtime.json --endpoint hyperframes.local
node bin/hypit.mjs build examples/semantic-composition/chat.svrun --workspace examples/semantic-composition --runtime examples/semantic-composition/hypit.runtime.json --follow
```

首次 preparation 会下载固定版本本地渲染器、浏览器及可能缺少的资源。只用该示例的 local
Profile，不连接或扫描生成模型凭据。`--follow` 只观察 Build；中止观察不取消后台任务。
如需取消，用实际 Build ID 的 `hypit cancel`。本次创建的后台任务要明确结束，不停用户已有的其他任务。

记录 CLI 返回的 **本次 Build ID**，成功后导出到本次新目录：

```sh
BUILD_ID="bld_actual_id_from_this_run"
WORK="/absolute/path/to/new-hypit-capcut-work"
node bin/hypit.mjs inspect "$BUILD_ID" --workspace examples/semantic-composition
node bin/hypit.mjs get "$BUILD_ID" --output final.video --workspace examples/semantic-composition --to "$WORK/hypit-chat.mp4"
node bin/hypit.mjs get "$BUILD_ID" --output main.composition --workspace examples/semantic-composition --to "$WORK/hypit-composition"
```

先创建 WORK，输出路径须新建。需要按项目解析时另导出实际 Timeline 输出；动画示例是
`animation.timeline`，其他工程名字由 inspect 确定。检查成片实际尺寸、帧率、帧数、时长和画面。

## 加入 CapCut

[聊天计划模板](../assets/chat.plan.template.json) 是这个八秒示例的 **渲染交接模板**，
不是 Hypit Composition 解析器。用 JSON 解析器加载并另存本次计划：

- 将 `name` 改为唯一新草稿名，不直接使用模板名。
- 将主视频 `source` 改为刚才导出的绝对路径。
- 将四个提示音片段的 `source` 改为本次的绝对本地音频路径。
- 模板字体是 CapCut 本机静态 OTF；缺少时报告并选择本次获授权的字体，不能隐式回退。
- 模板假定 8 秒、30 fps。若实际输出不同，重新按帧边界设计，不能截断或补尾帧冒充原样。

需要复现消息音时，用本地 FFmpeg 生成一次 0.24 秒、48 kHz 双声道 WAV：

```sh
ffmpeg -hide_banner -loglevel error -n -f lavfi \
  -i 'aevalsrc=0.35*exp(-18*t)*(sin(2*PI*880*t)+0.3*sin(2*PI*1320*t)):s=48000:d=0.24' \
  -af 'afade=t=in:d=0.005,afade=t=out:st=0.19:d=0.05' \
  -ac 2 -c:a pcm_s16le "$WORK/message.wav"
```

模板含一个缩放后留上下文字区的视频轨、两个原生文字轨和一个音效轨。
普通无声/不加标题的交接不强制使用该模板或音效。后续执行
[CapCut 构建、导出和原生保存验收](capcut.md)。本机该模板对应的首次导出得到
1080×1920、240/240 帧并完整解码；四次提示音对齐 0.5、2.0、3.5、5.2 秒。
这只是该样本的验证，不代表所有 Hypit 工程都可转换。

完成导出后，仅在没有其他使用者或未完成 Build 且确认是本次启动的 Runtime Worker 时停止它：

```sh
node bin/hypit.mjs runtime down --runtime examples/semantic-composition/hypit.runtime.json
```

保留用户明确需要继续使用的 Studio/Runtime；不因完成本示例就停止共享服务。
