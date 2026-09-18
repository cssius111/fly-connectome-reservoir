# fly-connectome-reservoir

一个在 Windows CPU 上可复现的计算神经科学实验：使用 FlyBrain 0.1.0 提供的 MaleCNS v1.0 衍生连接图，冻结 LIF 网络，只训练下降神经元活动的线性读出。

**不能把分类器学会任务称为“果蝇大脑学会任务”。** 直接向 LC4/LPLC2 特征神经元注入刺激；没有让完整眼睛处理图像。神经元动态、连接符号和归一化均含模型假设，未用真实果蝇记录验证。

实验与对照定义见 [PROTOCOL.md](PROTOCOL.md)，实际结果见 [results/REPORT.md](results/REPORT.md)。

## 在当前 Windows 环境运行

实际虚拟环境路径是 `D:\Projects\flybrain-lab\.venv`（在项目内部）。

```powershell
Set-Location D:\Projects\flybrain-lab
$env:FLY_DATA = "$PWD\data"
$env:NUMBA_NUM_THREADS = '4'
& .\.venv\Scripts\python.exe .\first_run.py
& .\.venv\Scripts\python.exe .\test_protocol.py
& .\.venv\Scripts\python.exe .\experiment.py
& .\.venv\Scripts\python.exe .\report.py
```

重复运行会覆盖同名结果；先复制 `results` 和 `artifacts/results` 可保留旧运行。用于发表/比较的新方案请另建配置和输出路径，例如 `experiment.py --config other-config.json --output results-new`；默认报告脚本读取 `results/`。修改参数后产生的结果属于新的实验，不应挑选测试结果最好的一组作为无偏估计。

## 从仓库重新建立环境

安装 Python 3.11.16 和 uv 后，在项目目录执行：

```powershell
uv venv --python 3.11.16 .venv
uv pip install --python .\.venv\Scripts\python.exe -r requirements-lock.txt
$env:FLY_DATA = "$PWD\data"
& .\.venv\Scripts\flybrain.exe download
& .\.venv\Scripts\flybrain.exe info
& .\.venv\Scripts\python.exe .\first_run.py
```

`requirements.txt` 是直接依赖，`requirements-lock.txt` 记录本次完整解析版本。若本机全局 uv 缓存没有写权限，可在 `uv pip install` 命令末尾加 `--no-cache`；不需要删除全局 Python 或缓存。当前未安装 CUDA/CuPy，CPU 是已验证的执行路径。

## 文件

| 文件 | 用途 |
|---|---|
| `first_run.py` | SHA256/ZIP 校验、加载、刺激、计时、同种子重放 |
| `config.json`、`PROTOCOL.md` | 首次运行前固定的参数与试验方案 |
| `experiment.py` | 划分、刺激、三种网络、原始输入和标签打乱对照、线性读出 |
| `test_protocol.py` | 划分平衡、重放、顺序任务控制条件、标准化与区间检查 |
| `report.py` | 从原始结果生成静态 PNG/SVG 和中文结果说明 |
| `results/` | 可提交的小体积指标、试验记录、图表和报告 |
| `artifacts/` | 本机神经元活动矩阵、分类器及绘图缓存，Git 忽略 |
| `game_config.json`、`game/` | 交互式苍蝇拍游戏的参数与代码（见下节） |
| `tools/calibrate_escape.py` | 测量 DNp01 的 loom / 无 loom 分布并记录逃逸阈值 |
| `test_game.py` | 游戏组件测试：感知瓶颈、编码器纯函数性、逃逸方向、致命窗口、定步长确定性 |

`.gitignore` 排除虚拟环境、连接数据、活动中间结果和日志，不把这些大文件提交到 GitHub。

## 交互游戏：连接组驱动的苍蝇拍

玩家用鼠标控制苍蝇拍，数字苍蝇以游戏物理维持低速巡航，威胁反应由 MaleCNS 衍生运行图驱动：拍子的逼近在苍蝇视网膜上形成扩张（looming），经 LPLC2/LC4 进入连接组，由 DNp01 的活动触发定向逃逸。实验流水线（`config.json`、`PROTOCOL.md`、`experiment.py`、`results/` 中已有结果）完全未改动。

```powershell
Set-Location D:\Projects\flybrain-lab
$env:FLY_DATA = "$PWD\data"
& .\.venv\Scripts\python.exe .\tools\calibrate_escape.py --trials 28   # 无匹配校准时运行
& .\.venv\Scripts\python.exe -m game.app                   # 开始游戏
& .\.venv\Scripts\python.exe -m unittest discover -v     # 全部游戏/实验测试
```

操作：移动鼠标控制拍子，左键挥拍，`R` 重开，`空格`/`P` 暂停，`H` 切换神经 HUD，`F11` 全屏，`Esc` 退出全屏或退出游戏。

**架构约束：原始鼠标坐标不会进入苍蝇的大脑。** 只有 `game/world.py` 知道鼠标位置；`game/perception.py` 把世界压缩成冻结的 `Retina`（只有角直径 `theta`、扩张率 `theta_dot`、自体坐标方位 `azimuth` 三个标量）；`game/fly.py` 的 `FlyLoop.step` 只接受 `Retina` 类型，连 `Retina` 的子类都会被拒绝。挥拍的抬手阶段没有任何隐藏标志位传给苍蝇——拍子在三维中下落并从侧向转为正面，苍蝇看到的就是真实的角扩张。LC4/LPLC2 两侧数量不等（LC4 左 71 右 55，LPLC2 左 94 右 91），按 PROTOCOL.md 同样的规则用固定种子下采样到每侧较小值，避免输入偏向一侧。

逃逸阈值不是手调的：`tools/calibrate_escape.py` 在同一条游戏流水线上固定苍蝇的位置与朝向、保持速度为零、禁用全部巡航/探索运动、策略逃逸及碰撞，测量有 loom 与无 loom 时的 DNp01 轨迹，按"在全部无 loom 时刻都不误触发的最小阈值"这一事先定好的规则选取，并把完整扫描记录写入 `artifacts/game/calibration.json`（本机，Git 忽略）与 `results/game/calibration.json`（可提交摘要）。

**不能把这个游戏称为"果蝇学会了躲苍蝇拍"。** 没有光感受器/视小叶层的图像处理：编码器直接驱动视觉投射神经元，这一点上游 `flybrain/eyes.py` 自己的文档也明确说明。LIF 参数是手工标定而非实测，逃逸解码器是固定阈值而非训练所得，行为来自单一解剖标本。游戏演示的是"逼近几何经 MaleCNS 衍生运行图到达 DNp01，并由其速率与侧别决定定向逃逸"，不是真实果蝇逃逸行为的验证。

## M1.1 接口与校准约束

游戏设置 `sensory_input=false`：加载时移除指向感觉神经元的边，得到冻结的 **MaleCNS 衍生运行图**。原始数据为 **25,582,938** 条连接；当前游戏运行图约 **25,088,107** 条。数据文件没有被改写，游戏运行中没有训练或可塑性；不能把它称为未改动的完整 MaleCNS 图。

`Policy` 行为协议仍只有 `reset()` 与 `decide(motor)`。策略可选提供 `diagnostics()`（例如 `escape_threshold`、`refractory_seconds`、`behavior_state`、`escape_strength`）；Session 统一暴露诊断字典，HUD 没有相应字段时隐藏阈值/冷却显示。仅实现行为协议的策略也能正常渲染。

`Action.lateral/forward` 只定义机体坐标方向。`strength` 是独立、有限且位于 [0,1] 的标量；非法值抛 `ValueError`。物理层只归一化方向，施加 `escape_impulse * strength` 的速度冲量，然后执行阻尼和限速；零强度或零方向不产生冲量。`turn` 独立，由 `fly.turn_rate` 缩放。省略强度时默认为 1，保留既有定幅调用的行为。固定策略按 DNp01 活动生成 0.5–1 的逃逸强度，尚未学习。

启动固定策略时，Session 检查**实际传入配置**的规范化 JSON SHA256、校准协议版本、FlyBrain 版本、编码器种子/细胞类型与平衡规则、`sensory_input` 和时间步。完整配置内容也包含在哈希内。旧记录、配置不匹配或无效阈值会被跳过；过期的 `artifacts/game/calibration.json` 不会遮盖匹配的已提交记录。若无匹配记录，启动失败并提示：

```
python tools/calibrate_escape.py --trials 28
```

自定义配置需加 `--config PATH`，游戏也使用同一个配置。配置的原始文件 SHA256 另保存在记录顶层，便于审计；运行时使用规范化内容哈希，避免 Windows 换行/JSON 排版造成误判。旧的“可 wander”校准不再匹配 fixed-fly-v2 协议。阈值在校准样本上选择；样本内零误触发不代表长期游戏永不误触发。

## M1.2：持续巡航与点击前避让

旧版 `wander_speed=42` 实际作为随机加速度使用，速度被 `3/s` 的阻尼压低，且每 0.55 秒换方向；它不是 42 单位/秒的持续飞行。旧悬停高度 300、可见尺寸比例 0.3 产生的角扩张很弱，DNp01 往往直到挥拍才被有效驱动。

现在物理层维持 **85 单位/秒的前向巡航目标**，速度以惯性逐步接近目标。探索是平滑的朝向漂移（最大 0.24 rad/s，每 1.6 秒重采样目标角速度，0.8 秒平滑），不是随机选择屏幕运动方向；靠近墙壁时进行温和转向。固定 seed 的轨迹可重放。巡航远慢于 440–880 单位/秒的逃逸冲量。巡航与避墙都是**游戏物理**，不声称来自连接组。

悬停高度改为 140、可见尺寸比例改为 0.65；LPLC2 的扩张增益为 20，LC4 的角大小/扩张参考量为 0.5 rad 和 2 rad/s。这些是明确记录的游戏/编码器参数，不是果蝇生理测量。拍子在悬停状态接近时，`theta` 与 `theta_dot` 就会增加；`azimuth` 仍只决定自体坐标中的输入侧别。点击没有隐藏提示通道：挥拍通过高度下降及拍面旋转产生更强角扩张。Retina 三字段接口不变，原始鼠标坐标不进入 FlyLoop、MotorState 或策略。

固定解码器在 DNp01 总迹线达到逃逸阈值的 55% 时开始 ALERT 转向，以 0.12 秒平滑；这个较低比例是游戏设计参数，**没有被宣称为校准所得的生理阈值**。侧别先积累 0.12 秒的神经活动证据，避免单次对侧噪声脉冲立刻翻转方向；转向以这个 DNp01 两侧的归一化差值决定，DNa02 只调制幅度（最多 15%，不能反转侧别）。达到完整 DNp01 阈值、且不在不应期时触发 ESCAPE 冲量；`strength` 仍为 0.5–1。双侧相等时不再任意指定向右，而保留前向分量。身体朝向持续积分，不再被侧向速度直接拉转；渲染对朝向也做插值，逃逸箭头使用施加冲量时的朝向。

H 可切换诊断 HUD：CALM / ALERT / ESCAPE、theta、theta_dot、LC4/LPLC2 注入电压、DNp01 左右迹线、巡航目标速度、实际速度和逃逸强度。ESCAPE 在逃逸/不应期内保持显示，强度表示该次冲量而非每一帧重新施加；ALERT 可包含转向的短暂衰减。神经噪声仍可能产生短暂 ALERT，校准的零误触发约束针对紧急 ESCAPE 样本。

重新运行 `python tools/calibrate_escape.py --trials 28` 后：阈值实测仍为 **1.45**；无 loom 均值 0.0875、p99 1.0006、最大 1.4493；挥拍窗口内 DNp01 峰值均值 3.8059、范围 2.7350–4.8523。28/28 检测，点击后中位延迟 0.06 秒，2520 个无 loom 样本内零紧急阈值越界。固定苍蝇的校准协议不变，运行时必须匹配新配置的来源记录。

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -v
& .\.venv\Scripts\python.exe -m game.app --smoke 3
& .\.venv\Scripts\python.exe .\tools\chase_sanity.py
```

`test_game_behavior.py` 增加持续飞行、平滑/确定性、左右转向、真实连接组点击前响应、无输入时无紧急逃逸、挥拍强于普通接近、连续轨迹、感知瓶颈、HUD，以及静默连接组对照（仍巡航，但无威胁转向/冲量）。原 M1.1 BarePolicy、强度语义和来源匹配回归保留。

脚本追逐使用固定的 101–104 种子：先在远处跟随 1 秒，再逼近，1.90 秒点击。完整迹线存于 `artifacts/m1-2/chase.json`，摘要存于 `results/game/chase_m1_2.json`；它检查动作是否早于点击/致命帧，不用命中率调参。**是否好玩、是否能通过预测命中，仍必须由人工试玩验收**。没有学习、塑性或 Milestone 2 训练；原 reservoir 实验代码和历史结果保持不变。

## 数据来源与归属

- [MaleCNS 官方数据](https://male-cns.janelia.org/download/)：MaleCNS v1.0，FlyEM / HHMI Janelia 及合作团队，CC-BY。
- [社区模拟器 fly.ai](https://github.com/alextitonis/fly.ai)：使用其发布的 `flybrain==0.1.0` 及经 SHA256 校验的 `brain-v1` 预构建数据。其点神经元动力学不是完整生理仿真。

本项目保存数据来源与校验和，不重新发布连接数据。GPU、突触可塑性和更复杂的视觉任务不属于这次基线运行。
