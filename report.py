"""Regenerate static scientific figures and a Chinese report from recorded results."""
import csv
import json
import os
from pathlib import Path
os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent/"artifacts"/"matplotlib"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import numpy as np

ROOT = Path(__file__).resolve().parent
OUT = ROOT/"results"
METHODS = ["connectome", "target_permutation", "no_connections", "raw_history", "raw_integrated", "shuffled_labels"]
LABELS = ["Connectome", "Target permutation", "No connections", "Raw full history", "Raw integrated", "Shuffled fit labels"]
CN = ["真实连接", "目标神经元重排", "无连接", "原始完整刺激历史", "原始刺激积分", "打乱拟合标签"]
COLORS = ["#235C91", "#B56827", "#787878", "#576B38", "#A78A47", "#9A617C"]


def main():
    records = json.loads((OUT/"metrics.json").read_text(encoding="utf-8"))
    manifest = json.loads((OUT/"manifest.json").read_text(encoding="utf-8"))
    cfg = manifest["config"]
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
        "axes.spines.top": False, "axes.spines.right": False, "savefig.dpi": 180})
    summaries = []
    fig, axes = plt.subplots(1, 2, figsize=(12.2, 5.2), sharey=True)
    for task, ax in zip(("side", "order"), axes):
        for i, method in enumerate(METHODS):
            rr = sorted([r for r in records if r["task"] == task and r["method"] == method], key=lambda r: r["seed"])
            assert len(rr) == len(cfg["seeds"])
            a = np.array([r["accuracy"] for r in rr])
            mean, sd = a.mean(), a.std(ddof=1)
            summaries.append(dict(task=task, method=method, mean_accuracy=mean, sample_sd=sd,
                accuracies=a.tolist(), correct=sum(r["correct"] for r in rr), n=sum(r["n_test"] for r in rr)))
            ax.errorbar(mean, i, xerr=sd, fmt="o", color=COLORS[i], capsize=5, markersize=7)
            ax.scatter(a, i+np.linspace(-0.13, 0.13, len(a)), marker="|", s=100, color=COLORS[i])
        ax.axvline(0.5, color="#444444", ls="--", lw=1, label="50% chance")
        ax.set_xlim(0, 1.06)
        ax.set_xticks(np.arange(0, 1.01, .25))
        ax.xaxis.set_major_formatter(PercentFormatter(1))
        ax.set_yticks(range(len(METHODS)), LABELS)
        ax.set_xlabel("Held-out accuracy")
        ax.set_title("Side: during stimulus" if task == "side" else "Order: after stimulus")
        ax.grid(axis="x", color="#E4E4E4")
        ax.set_axisbelow(True)
    axes[0].invert_yaxis()
    fig.suptitle("Frozen MaleCNS-derived network: trained linear readouts", fontsize=15)
    fig.text(.5, .025, "Dots = means; error bars = sample SD across 3 seeds; ticks = individual runs. 60 test trials/run.\nSD is not a confidence interval. A perfect input-history baseline limits claims of reservoir advantage.", ha="center", fontsize=10)
    fig.tight_layout(rect=(0, .105, 1, .92))
    fig.savefig(OUT/"accuracy.png")
    fig.savefig(OUT/"accuracy.svg")
    plt.close(fig)

    data = np.load(OUT/"population_traces.npz")
    fig, axes = plt.subplots(3, 2, figsize=(12, 8.8))
    for i, method in enumerate(METHODS[:3]):
        for j, task in enumerate(("side", "order")):
            ax = axes[i, j]
            # Use class 0 only, clearly labelled. All independent TEST trials included.
            trace = np.mean([data[f"{task}_{s}_{method}"][0] for s in cfg["seeds"]], axis=0)
            spec = cfg["tasks"][task]
            t = (np.arange(spec["steps"])+.5)*cfg["dt_seconds"]
            for side, color, ls in ((0, "#235C91", "-"), (1, "#B56827", "--")):
                ax.plot(t, trace[:, side], color=color, ls=ls, label=("Left DN" if side == 0 else "Right DN"))
            for key in ("pulse1", "pulse2"):
                if key in spec:
                    a, b = spec[key]
                    ax.axvspan(a*.02, b*.02, color="#999999", alpha=.13)
            a, b = spec["readout"]
            ax.axvspan(a*.02, b*.02, color="#235C91", alpha=.10)
            ax.set_title(f"{LABELS[i]} / {'left only' if task == 'side' else 'left then right'}", fontsize=11)
            ax.set_ylabel("Mean DN firing rate (Hz)")
            ax.set_xlabel("Time since trial reset (s)")
            ax.set_ylim(bottom=0)
            ax.grid(axis="y", color="#E8E8E8")
    for j in range(2):
        ymax = max(axes[i, j].get_ylim()[1] for i in range(3))
        for i in range(3):
            axes[i, j].set_ylim(0, ymax)
    axes[0, 0].legend(frameon=False, loc="upper left")
    fig.suptitle("Descending activity on held-out class-0 trials", fontsize=15)
    fig.text(.5, .018, "90 test trials per panel (30/seed). Grey = injected pulses; blue shading = classifier readout window.\nEqual y-scales within each task. Population averages can hide informative single-neuron responses.", ha="center", fontsize=10)
    fig.tight_layout(rect=(0, .07, 1, .95))
    fig.savefig(OUT/"activity.png")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(8, 4.2))
    for ax, task in zip(axes, ("side", "order")):
        cm = np.zeros((2, 2), int)
        for r in records:
            if r["task"] == task and r["method"] == "connectome":
                np.add.at(cm, (r["test_labels"], r["predictions"]), 1)
        ax.imshow(cm, cmap="Blues", vmin=0, vmax=90)
        for (i, j), value in np.ndenumerate(cm):
            ax.text(j, i, str(value), ha="center", va="center", color="white" if value > 45 else "#222222", fontsize=16)
        labels = ["Left", "Right"] if task == "side" else ["L then R", "R then L"]
        ax.set_xticks([0, 1], labels)
        ax.set_yticks([0, 1], labels)
        ax.set_xlabel("Prediction")
        ax.set_ylabel("True label")
        ax.set_title("Side" if task == "side" else "Order")
    fig.suptitle("Connectome readout: pooled test confusion counts")
    fig.text(.5, .015, "180 predictions/task from 3 independently fitted readouts; not 180 independent animals.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .04, 1, .93))
    fig.savefig(OUT/"confusion.png")
    plt.close(fig)

    (OUT/"summary.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    with (OUT/"metrics.csv").open("w", newline="", encoding="utf-8") as f:
        fields = [k for k in records[0] if k not in ("predictions", "test_labels")]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows({k:r[k] for k in fields} for r in records)
    lookup = {(r["task"], r["method"]): r for r in summaries}
    lines = ["# 首次 CPU 实验结果", "", "本实验冻结网络全部连接权重，只拟合读取下降神经元活动的线性分类器。输入是直接注入 LC4/LPLC2 特征神经元的电压；不是完整眼睛处理图像，也不是果蝇大脑学会了任务。", "",
        "## 测试集准确率", "", "每项任务每个种子使用 60 训练、20 验证、60 测试试验；3 个独立数据/噪声种子。表中为平均值 ± 样本标准差，单位是百分比/百分点；不是置信区间。", "",
        "| 方法 | 左右辨别 | 延迟顺序辨别 |", "|---|---:|---:|"]
    for method, name in zip(METHODS, CN):
        vals = [lookup[t, method] for t in ("side", "order")]
        lines.append(f"| {name} | " + " | ".join(f"{v['mean_accuracy']*100:.1f}% ± {v['sample_sd']*100:.1f}" for v in vals)+" |")
    lines += ["| 理论机会水平 | 50% | 50% |", "", "![测试集准确率](accuracy.png)", "",
        "## 如何解释", "", "1. 原始完整刺激历史可以直接提供标签。左右辨别的高准确率只验证输入到下降神经元之间存在可解码信号，不能说明真实连接优于一般机器学习模型。",
        "2. 顺序任务两侧积分输入严格相等，读取活动时刺激已撤去。它检验短暂状态/最近侧记忆；最后一次刺激的侧别本身就确定标签，所以不能称为复杂顺序计算或长期记忆。",
        "3. 重排对照仅打乱目标神经元身份，保留每个源的出度和权重、入度分布及归一化行和分布；它同时破坏解剖定位和输入输出对应关系。即便真实连接更好，也不能据此独立归因于精细拓扑。", ""]
    for task, name in (("side", "左右"), ("order", "顺序")):
        a = np.array(lookup[task, "connectome"]["accuracies"])
        b = np.array(lookup[task, "target_permutation"]["accuracies"])
        d = 100*(a-b)
        lines.append(f"- {name}任务真实连接减重排连接的配对差值：{', '.join(f'{v:+.1f}' for v in d)} 个百分点；平均 {d.mean():+.1f}。仅描述 3 次配对重复，不做显著性或生物泛化声明。")
    lines += ["", "每次测试的 Wilson 95% 区间见下表；这些区间以该次已拟合模型为条件，不覆盖模型选择、动物差异或参数不确定性。", "",
        "| 任务 | 种子 | 真实连接正确数 | Wilson 95% 区间 |", "|---|---:|---:|---:|"]
    for r in records:
        if r["method"] == "connectome":
            lines.append(f"| {r['task']} | {r['seed']} | {r['correct']}/{r['n_test']} | {r['wilson_low']*100:.1f}%–{r['wilson_high']*100:.1f}% |")
    lines += ["", "![混淆矩阵](confusion.png)", "", "## 活动与运行成本", "", "![下降神经元活动](activity.png)", "",
        f"共模拟 {len(cfg['seeds'])*3*sum(cfg[k] for k in ('train_trials','validation_trials','test_trials'))*len(cfg['tasks']):,} 次完整试验。正式运行总耗时 **{manifest['total_seconds']:.1f} 秒**（含数据校验、JIT、模拟、分类器与保存；不含画图和安装）。", "",
        "| 网络 | 平均全网放电率 Hz | 读出窗口满步放电比例 | 含采集开销 ms/步 |", "|---|---:|---:|---:|"]
    for method, name in zip(METHODS[:3], CN[:3]):
        rr = [r for r in manifest["runtimes"] if r["method"] == method]
        lines.append(f"| {name} | {np.mean([r['mean_all_neuron_hz'] for r in rr]):.3f} | {np.mean([r['readout_ceiling_fraction'] for r in rr])*100:.3f}% | {np.mean([r['ms_per_step'] for r in rr]):.3f} |")
    lines += ["", "当前 CPU 成本足以继续小规模实验，暂不安装 GPU 依赖。已检测到 RTX 4060 Laptop GPU / 8188 MiB，但尚未测量 GPU 速度、峰值显存或 CPU/GPU 统计一致性。扩大试验数、扫描延迟/噪声或加入更严格重连对照时，再单独做 GPU 基准。", "",
        "## 可复现记录与局限", "", "- `manifest.json`：完整参数、数据/源码 SHA256、版本、各条件耗时、权重冻结验证。",
        "- `trials.csv`：每个试验的划分、标签、强度、噪声种子；`metrics.json`：测试预测及所选正则化参数。",
        "- `population_traces.npz`：绘图使用的测试集群体轨迹；大一些的单神经元活动与拟合模型在本机 `artifacts/results/`，被 Git 排除。",
        "- 三次重复来自同一个解剖图；固定一个编码器子集、单一 LIF 参数组、短时重置试验。无法估计跨个体泛化、稳态行为或真实生理反应。",
        "- 默认保留感觉神经元反馈；上游已描述部分感觉回路的高自发活动问题。未在当前任务上扫描该选项，以避免测试集调参。",
        "- 无连接/标签打乱对照的偏离 50% 应结合小测试集波动理解；本次只有 3 组重排网络，不足以做稳健的结构优势推断。",
        "- 后续应另建未查看过的测试集，增加重复和延迟梯度，加入逐神经元有符号入/出度匹配的重连对照，以及末次侧别相同、只有更早历史不同的任务。", "",
        "方案、来源和数据许可见 [PROTOCOL.md](../PROTOCOL.md)。"]
    (OUT/"REPORT.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print(json.dumps(summaries, indent=2))
    print(f"Figures and report saved to {OUT}")


if __name__ == "__main__":
    main()
