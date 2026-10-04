# hypit-capcut

为匹配版本的 macOS CapCut 提供本地 Agent 工作流，并支持 Hypit 成片交接。
入口见 [SKILL.md](SKILL.md)；不包含应用引擎，也不提供通用 SVML 无损转换器。

## 安装到 Codex

在 Jianying Headless 仓库根目录安装符号链接，以保留核心项目与参考文档的关系：

```sh
SKILLS_HOME="${CODEX_HOME:-$HOME/.codex}/skills"
mkdir -p "$SKILLS_HOME"
ln -s "$PWD/skills/hypit-capcut" "$SKILLS_HOME/hypit-capcut"
```

目标已存在时先检查，不用 `ln -sf` 覆盖其他 Skill。保持本机 checkout 可用；移动或删除
仓库后符号链接会失效。安装只添加 Skill，不启动 Hypit、CapCut 或付费服务。
不要仅复制 `SKILL.md`；参考文件、模板和核心项目都需要保留。

新会话可以明确调用：

```text
使用 $hypit-capcut 跑一个不调用付费模型的 Hypit 聊天动画示例，生成 CapCut 可编辑草稿和本地 MP4，报告实际验收结果。
```

也可以请求用现有本地素材构建 CapCut 草稿或修改独立副本，不强制先运行 Hypit。
若技能列表没有更新，重开会话或重启宿主后检查，不据安装文件存在就宣称已实际触发。

## 前提

- 已检出的 Jianying Headless 核心项目和匹配版本 CapCut；精确环境见 [CapCut 文档](../../docs/CAPCUT.md)。
- Python、FFmpeg/ffprobe、匹配的 Xcode 工具链；本地字体还需 fontTools。
- 仅 Hypit 路径需要额外的 Hypit checkout、Node 和固定版本的包管理器。
- 普通素材和计划不需要生成模型账号；示例渲染器、浏览器、字体可能需要首次下载。

本 Skill 按 [核心项目许可证](../../LICENSE) 使用。Hypit 和 CapCut 的许可及素材授权独立适用。
