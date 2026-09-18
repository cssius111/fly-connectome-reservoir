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

玩家用鼠标控制苍蝇拍，数字苍蝇由 MaleCNS 连接组驱动：拍子的逼近在苍蝇视网膜上形成扩张（looming），经 LPLC2/LC4 进入连接组，由 DNp01 的活动触发定向逃逸。实验流水线（`config.json`、`PROTOCOL.md`、`experiment.py`、`results/` 中已有结果）完全未改动。

```powershell
Set-Location D:\Projects\flybrain-lab
$env:FLY_DATA = "$PWD\data"
& .\.venv\Scripts\python.exe .\tools\calibrate_escape.py   # 首次运行必须，记录逃逸阈值
& .\.venv\Scripts\python.exe -m game.app                   # 开始游戏
& .\.venv\Scripts\python.exe .\test_game.py                # 测试
```

操作：移动鼠标控制拍子，左键挥拍，`R` 重开，`空格`/`P` 暂停，`H` 切换神经 HUD，`F11` 全屏，`Esc` 退出全屏或退出游戏。

**架构约束：原始鼠标坐标不会进入苍蝇的大脑。** 只有 `game/world.py` 知道鼠标位置；`game/perception.py` 把世界压缩成冻结的 `Retina`（只有角直径 `theta`、扩张率 `theta_dot`、自体坐标方位 `azimuth` 三个标量）；`game/fly.py` 的 `FlyLoop.step` 只接受 `Retina` 类型，连 `Retina` 的子类都会被拒绝。挥拍的抬手阶段没有任何隐藏标志位传给苍蝇——拍子在三维中下落并从侧向转为正面，苍蝇看到的就是真实的角扩张。LC4/LPLC2 两侧数量不等（LC4 左 71 右 55，LPLC2 左 94 右 91），按 PROTOCOL.md 同样的规则用固定种子下采样到每侧较小值，避免输入偏向一侧。

逃逸阈值不是手调的：`tools/calibrate_escape.py` 在同一条游戏流水线上测量有 loom 与无 loom 时的 DNp01 轨迹，按"在全部无 loom 时刻都不误触发的最小阈值"这一事先定好的规则选取，并把完整扫描记录写入 `artifacts/game/calibration.json`（本机，Git 忽略）与 `results/game/calibration.json`（可提交摘要）。

**不能把这个游戏称为"果蝇学会了躲苍蝇拍"。** 没有光感受器/视小叶层的图像处理：编码器直接驱动视觉投射神经元，这一点上游 `flybrain/eyes.py` 自己的文档也明确说明。LIF 参数是手工标定而非实测，逃逸解码器是固定阈值而非训练所得，行为来自单一解剖标本。游戏演示的是"逼近图像经未改动的 MaleCNS 连接通路到达 DNp01，并由其速率与侧别决定定向逃逸"，不是真实果蝇逃逸行为的验证。

## 数据来源与归属

- [MaleCNS 官方数据](https://male-cns.janelia.org/download/)：MaleCNS v1.0，FlyEM / HHMI Janelia 及合作团队，CC-BY。
- [社区模拟器 fly.ai](https://github.com/alextitonis/fly.ai)：使用其发布的 `flybrain==0.1.0` 及经 SHA256 校验的 `brain-v1` 预构建数据。其点神经元动力学不是完整生理仿真。

本项目保存数据来源与校验和，不重新发布连接数据。GPU、突触可塑性和更复杂的视觉任务不属于这次基线运行。
