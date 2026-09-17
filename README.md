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

`.gitignore` 排除虚拟环境、连接数据、活动中间结果和日志，不把这些大文件提交到 GitHub。

## 数据来源与归属

- [MaleCNS 官方数据](https://male-cns.janelia.org/download/)：MaleCNS v1.0，FlyEM / HHMI Janelia 及合作团队，CC-BY。
- [社区模拟器 fly.ai](https://github.com/alextitonis/fly.ai)：使用其发布的 `flybrain==0.1.0` 及经 SHA256 校验的 `brain-v1` 预构建数据。其点神经元动力学不是完整生理仿真。

本项目保存数据来源与校验和，不重新发布连接数据。GPU、突触可塑性和更复杂的视觉任务不属于这次基线运行。
