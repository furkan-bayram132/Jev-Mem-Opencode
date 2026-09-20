"""Render an editable vector overview of the implemented Jev-Mem workflows."""
from pathlib import Path
import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/jev-mem-figure-mpl")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle

plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "none", "pdf.fonttype": 42})
fig, ax = plt.subplots(figsize=(16, 10.6))
fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
ax.set(xlim=(0, 16), ylim=(0, 10.6))
ax.axis("off")
palette = {"jev": ("#E8F0FF", "#3564AC"), "data": ("#EAF4EF", "#388568"),
           "store": ("#F4F6F8", "#758394"), "llm": ("#FFF0DC", "#BC791F"),
           "input": ("#FFFFFF", "#758394")}
ink = "#183044"


def text(x, y, s, size=11, weight="normal", color=ink, ha="center"):
    ax.text(x, y, s, fontsize=size, weight=weight, color=color, ha=ha,
            va="center", linespacing=1.5, zorder=4)


def box(x, y, width, height, label, kind="data", size=11):
    fill, edge = palette[kind]
    ax.add_patch(FancyBboxPatch((x-width/2, y-height/2), width, height,
        boxstyle="round,pad=0.015,rounding_size=0.10", linewidth=1.4,
        facecolor=fill, edgecolor=edge, zorder=2))
    text(x, y, label, size=size)


def arrow(points, dashed=False, color="#596E80"):
    for start, end in zip(points[:-2], points[1:-1]):
        ax.plot([start[0], end[0]], [start[1], end[1]], color=color, lw=1.4,
                linestyle="--" if dashed else "-", zorder=1)
    ax.add_patch(FancyArrowPatch(points[-2], points[-1], arrowstyle="-|>",
        mutation_scale=13, linewidth=1.4, color=color,
        linestyle="--" if dashed else "-", zorder=1))


text(0.4, 10.18, "Jev-Mem", size=23, weight="bold", ha="left")
text(2.55, 10.17, "Typed decisions for memory construction and retrieval", size=15, ha="left")
text(0.4, 9.65, "WRITE WORKFLOW", size=12, weight="bold", ha="left")
text(3.0, 9.65, "Retain every valid observation; no admission filter", size=11, ha="left")

box(1.6, 8.85, 2.5, 1.0, "Observation\nText + provenance", "input")
box(4.8, 8.85, 2.7, 1.0, "Jev: memory typing\nFour overlapping Nouls", "jev")
box(8.0, 8.85, 2.7, 1.0, "Embed + find candidates\nBounded pair set", "data")
box(11.2, 8.85, 2.7, 1.0, "Jev: relation decisions\nBatched Noul + Choice", "jev")
box(14.35, 8.85, 2.5, 1.0, "Insert memory\nNode + vector + edges", "data")
for left, right in [(2.87, 3.43), (6.17, 6.63), (9.37, 9.83), (12.57, 13.08)]:
    arrow([(left, 8.85), (right, 8.85)])
text(11.2, 8.04, "Known timestamps and exact names use rules", size=9)

ax.add_patch(FancyBboxPatch((0.4, 5.25), 11.85, 1.78,
    boxstyle="round,pad=0.015,rounding_size=0.12", linewidth=1.4,
    facecolor=palette["store"][0], edgecolor=palette["store"][1], zorder=0))
text(6.32, 6.70, "SHARED MEMORY DATA PLANE", size=12, weight="bold")
text(6.32, 6.38, "Canonical observation nodes · original content · provenance · type scores", size=11)
for x, label in [(1.98, "Semantic"), (4.88, "Temporal"), (7.78, "Causal"), (10.68, "Entity")]:
    box(x, 5.96, 2.45, 0.40, label + " relations", "store", size=10)
text(6.32, 5.49, "Vector index + keyword index reference the same nodes", size=10)
arrow([(14.35, 8.33), (14.35, 7.52), (10.7, 7.52), (10.7, 7.05)])
arrow([(8.0, 7.05), (8.0, 8.32)])
text(6.5, 7.59, "Existing memory candidates", size=9)
box(14.3, 6.13, 2.7, 1.40, "Periodic consolidation\nJev decisions + links\nPreserve raw observations", "jev", size=10)
arrow([(12.28, 6.47), (12.92, 6.47)], dashed=True)
arrow([(12.92, 5.85), (12.28, 5.85)], dashed=True)
text(14.3, 5.16, "Optional summary callback to System Two", size=9)

text(0.4, 4.84, "RETRIEVAL WORKFLOW", size=12, weight="bold", ha="left")
box(1.35, 3.95, 1.9, 1.16, "Query", "input", size=12)
box(3.9, 3.95, 2.5, 1.16, "Jev: query needs\nGraph budgets\n+ depth allowance", "jev", size=10.5)
box(6.7, 3.95, 2.4, 1.16, "Hybrid anchors\nVector + keyword\nrank fusion", "data", size=10.5)
box(9.4, 3.95, 2.3, 1.16, "Jev: evidence check\nSufficiency + gaps\nUsefulness + conflict", "jev", size=10)
box(12.0, 3.95, 2.3, 1.16, "Bounded expansion\nTyped neighbors\n+ remaining budgets", "data", size=10)
box(14.65, 3.95, 2.25, 1.16, "Jev: candidate scores\nWeighted ranking\n+ beam update", "jev", size=10)
for left, right in [(2.32, 2.63), (5.17, 5.48), (7.92, 8.23), (10.57, 10.83), (13.17, 13.5)]:
    arrow([(left, 3.95), (right, 3.95)])
arrow([(6.7, 5.23), (6.7, 4.55)])
arrow([(12.0, 5.23), (12.0, 4.55)])
text(10.71, 4.70, "continue", size=9)
text(3.9, 2.99, "Hard limits: graph expansions, nodes, edges,\ndepth, Jev attempts, elapsed time", size=10)
arrow([(14.65, 3.35), (14.65, 2.12), (9.4, 2.12), (9.4, 3.35)])
text(12.1, 2.36, "Update evidence and repeat", size=10)
arrow([(8.65, 3.35), (8.65, 2.55), (6.7, 2.55), (6.7, 1.51)])
text(7.66, 2.77, "stop / hard limit", size=9)
text(6.7, 1.82, "Selected original evidence + source metadata", size=10)
box(6.7, 0.99, 3.0, 0.98, "System Two\nAnswer synthesis", "llm", size=12)
box(10.75, 0.99, 2.75, 0.98, "Answer\n+ retrieval trace", "input", size=11)
arrow([(8.22, 0.99), (9.35, 0.99)])

for x, kind, label in [(0.48, "jev", "Jev decisions"), (3.4, "data", "Memory operations"),
                       (7.0, "store", "Persistent evidence"), (10.65, "llm", "System Two")]:
    ax.add_patch(Rectangle((x, 0.10), 0.18, 0.18, facecolor=palette[kind][0], edgecolor=palette[kind][1]))
    text(x+0.28, 0.19, label, size=9, ha="left")
text(14.15, 0.19, "Dashed: periodic branch", size=9)

directory = Path(__file__).resolve().parent
for extension in ("svg", "pdf", "png"):
    fig.savefig(directory / f"jev_mem_overview.{extension}", dpi=160, facecolor="white")
plt.close(fig)
print("Wrote jev_mem_overview.svg, .pdf and .png")
