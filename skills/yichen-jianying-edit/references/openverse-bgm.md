# Openverse / Freesound BGM

通过 Openverse Audio API 搜索 Freesound 音乐；无需 API key。当前只接入 Freesound
CDN 的 MP3 **预览文件**，不是原始 WAV、无损下载、Freesound OAuth 或剪映内置曲库。
搜索与试听联网；添加音乐、构建草稿和原生导出仍是本地操作。需要 Python 3.9+、
FFmpeg / ffprobe；无新增 Python 依赖。

## 搜索与试听

以下命令从仓库根目录执行。所有输入文件使用绝对路径，输出必须是全新路径；
示例中的 `/absolute/path` 和 `UUID_FROM_CATALOG` 须替换为本次实际值。

```bash
python3 skills/yichen-jianying-edit/scripts/openverse_bgm.py search \
  --query "electronic music" --min-duration 20 --max-duration 120 --limit 5 \
  --work "$PWD/work/bgm-search"

python3 skills/yichen-jianying-edit/scripts/openverse_bgm.py preview \
  --catalog "$PWD/work/bgm-search/candidates.json" --id UUID_FROM_CATALOG \
  --work "$PWD/work/bgm-preview"
```

`search` 保存原始响应、候选、筛除理由，不下载音频。英文曲风或乐器关键词通常更有效；
只在本次第一页 20 条结果内排序，最多返回 20 条。时长参数以秒计，API 的 `duration`
以毫秒计。仅根据标题、标签、时长和许可排序，不代表已试听、无歌声或适合当前剪辑。
无合格结果或限流时停止，不换来源、不静默移除音乐。

`preview` 只下载明确选择的一首，保留 MP3、48 kHz 双声道 PCM16 `preview.wav`、
哈希、`preview.json` 和 `credits.md`。播放试听并检查源页面当前许可与第三方权利，
再决定是否使用。不能把报告中的 `listened: false` 当作已完成听感验收。

## 添加到计划

输入是 `jy14-headless-plan/v1`，不是语义口播计划或 compiled speech JSON。
口播流程先完成 `from-compiled`；Hypit 流程先映射成 headless plan。
此命令不直接修改已有 CapCut 草稿，也不执行 build / publish / export。

```bash
python3 skills/yichen-jianying-edit/scripts/openverse_bgm.py add \
  --preview "$PWD/work/bgm-preview/preview.json" \
  --plan /absolute/path/plan.json --out "$PWD/work/plan-with-bgm.json" \
  --work "$PWD/work/bgm-add" --license-reviewed \
  --volume 0.5 --fade-in 0.35 --fade-out 0.5 \
  --duck-track "Narration" --duck-db 8
```

没有名为 `Narration` 的独立口播轨就删去 `--duck-track`，或换成计划中实际的轨道名。
可重复指定多个名字；每个名字必须唯一对应一条 audio/video 轨。
只选择明确的口播区间轨：压低依据片段时间范围，不分析声音、VAD 或字幕，
不支持该参考轨的关键帧。连续整片旁白轨会让 BGM 几乎全程被压低。

- 默认从时间线 0 秒填充主视频剩余长度；`--start`、`--duration` 控制加入区间，
  `--source-start` 控制源音频起点，单位均为秒。单次最长 600 秒，不越过主轨结尾。
- 音乐不足时默认拒绝。明确加 `--loop` 才允许循环，接缝为 50 ms 交叉淡化，
  **不是节拍匹配**；循环是否自然需要试听。
- 选定片段归一化目标为 -23 dBFS RMS，最多提升 12 dB，峰值不超过 -2 dBFS。
  `--volume` 为后续轨道音量（0–1，默认 0.5），不是最终混音 LUFS 或防削波保证。
- 默认线性淡入 0.35 秒、淡出 0.5 秒；口播压低默认 8 dB，提前 80 ms 进入、
  结束后 250 ms 恢复。极短片段须相应缩短淡入淡出。
- 处理后的淡化、循环和压低已烘焙到 `bgm.wav`；草稿里音乐轨音量仍可调，
  重新调整这些处理参数需重新生成 WAV。
- 保留原计划的所有轨道，只向新计划追加 `Openverse BGM` 音轨。
  已有同名轨时拒绝重复添加；**不会检测其他名称的已有配乐**，应先检查避免叠加。
- `report.json`、音频哈希、`credits.md` 保留处理证据；失败保留现场，不覆盖输出。

## 构建和导出

```bash
python3 skills/yichen-jianying-edit/scripts/headless_draft.py --app capcut build \
  --plan "$PWD/work/plan-with-bgm.json" --out "$PWD/work/bgm-build"
python3 skills/yichen-jianying-edit/scripts/headless_draft.py --app capcut verify-build \
  --build "$PWD/work/bgm-build"
python3 skills/yichen-jianying-edit/scripts/headless_draft.py --app capcut export \
  --build "$PWD/work/bgm-build" --out "$PWD/work/bgm-export"
```

剪映去掉 `--app capcut`，仍遵循对应版本的导出限制。
上面的 export 只在用户要求成片时执行；首页登记另走已有 publish 流程。
构建后检查声音、转场、循环接缝、口播可懂度和混音削波。解码通过不代表听感通过。

## 许可与边界

仅接受 CC0、CC BY（2.0 / 2.5 / 3.0 / 4.0），排除 NC / ND / SA。
CC BY 需要在发布说明中提供作者、作品名、来源、许可链接与修改说明；
随结果交付可直接使用的 `credits.md`。CC0 也保留来源，便于追溯。
`--license-reviewed` 只记录调用者已核对，不是工具自动完成法律审核。
Openverse 索引可能滞后；不能以元数据或成功下载证明当前许可、上传者权利、
商标/采样权或平台 Content ID 安全，也不能保证 TikTok / Instagram 的商用音乐权益。

当前不提供自动按视频节拍选曲、BPM 检测、智能卡点、AI 作曲或原始文件认证下载。
如果预览音质不够，可从源站合法取得原文件后按普通本地音轨导入，勿冒充本流程下载的无损文件。

开发验证：`python3 -m unittest discover -s tests -p test_openverse_bgm.py -v`。
匹配 CapCut 的 Mac 还可运行 `python3 tools/openverse_bgm_smoke_test.py`，
只用合成素材在新工作目录检查原生构建、导出与音乐压低，不登记或改动现有工程。
