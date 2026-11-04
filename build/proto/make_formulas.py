"""把公式渲染成 PNG（mathtext，透明底），供 PPT 里做「教材式」公式。"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent / "assets"
OUT.mkdir(parents=True, exist_ok=True)

INK = "#1F2A26"

plt.rcParams.update({
    "mathtext.fontset": "stix",
    "font.family": "STIXGeneral",
})

FORMULAS = {
    "f_score": r"$\mathrm{score} = \sum_{i=1}^{6} w_i\, s_i$",
    "f_air": r"$s_{\mathrm{air}} = \mathrm{clip}\left(100\cdot\frac{40-\mathrm{NO_2}}{30},\ 0,\ 100\right)$",
    "f_green": r"$s_{\mathrm{green}} = 0.7\left(1-e^{-2.5S}\right) + 0.3\left(1-\frac{d}{1500}\right)$",
    "f_slope": r"$s_{\mathrm{slope}} = 100\left(1-\frac{|i|}{10}\right)$",
    "f_cross": r"$s_{\mathrm{cross}} = 100 - 7\,n_{200}$",
    "f_fac": r"$s_{\mathrm{fac}} = 100\,e^{-d/500}$",
    "f_cost": r"$c = d\cdot\left(1 + \frac{100-p}{40}\right)$",
}


def main() -> None:
    for name, tex in FORMULAS.items():
        fig = plt.figure(figsize=(8, 2))
        fig.patch.set_alpha(0)
        fig.text(0.01, 0.5, tex, fontsize=30, color=INK, va="center")
        path = OUT / f"{name}.png"
        fig.savefig(path, dpi=300, transparent=True, bbox_inches="tight", pad_inches=0.06)
        plt.close(fig)
        print(path.name, path.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
