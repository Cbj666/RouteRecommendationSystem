"""只负责把 P8 的公式渲染成透明 PNG（用项目 .venv 的 matplotlib）。"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
FIMG = ROOT / "build" / "proto" / "assets" / "p8"

plt.rcParams.update({"mathtext.fontset": "stix", "font.family": "STIXGeneral"})

FORMULAS = {
    "f_safety": r"$s_{\mathrm{safe}}=\mathrm{clip}\!\left(R(\mathrm{fclass})-15\,\mathbf{1}[d<50]-10\,\mathbf{1}[d<20],\ 0,\ 100\right)$",
    "f_green": r"$s_{\mathrm{green}}=0.7\left[100(1-e^{-2.5S})\right]+0.3\left[\mathrm{clip}(100(1-d/1500))\right]$",
    "f_slope": r"$s_{\mathrm{slope}}=\mathrm{clip}\!\left(100\left(1-\frac{i}{10}\right),0,100\right)$",
    "f_cross": r"$s_{\mathrm{cross}}=\mathrm{clip}\!\left(100-7\,n_{200},\ 0,\ 100\right)$",
    "f_air": r"$s_{\mathrm{air}}=\mathrm{clip}\!\left(100\cdot\frac{40-\mathrm{NO_2}}{30},\ 0,\ 100\right)$",
    "f_fac": r"$s_{\mathrm{fac}}=100\,e^{-d/500}$",
    "f_score": r"$\mathrm{score}=\sum_{i=1}^{6} w_i\, s_i$",
}


def main() -> None:
    FIMG.mkdir(parents=True, exist_ok=True)
    for name, tex in FORMULAS.items():
        fig = plt.figure(figsize=(9, 1.5))
        fig.patch.set_alpha(0)
        fig.text(0.005, 0.5, tex, fontsize=26, color="#1F2A26", va="center")
        out = FIMG / f"{name}.png"
        fig.savefig(out, dpi=300, transparent=True, bbox_inches="tight", pad_inches=0.05)
        plt.close(fig)
        print(out.name, out.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
