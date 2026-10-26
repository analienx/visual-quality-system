"""Deterministic categorical-series perception checks (advisory, stdlib only).

WCAG contrast is measured against the chart surface separately. CIELAB
distances here are screening heuristics, not a substitute for a native
screenshot or human color-vision assessment. The matrices approximate severe
common color-vision deficiencies (Machado 2009, severity 1), on
properly linearized sRGB; never equate them to an individual's perception.
"""
from __future__ import annotations

import itertools
import math
from collections.abc import Sequence

MATRICES = {
    "protan": ((.152286, .114503, .733211),
               (.114503, .786281, .099216),
               (-.003882, -.048116, 1.051998)),
    "deutan": ((.367322, .860646, -.227968),
               (.280085, .672501, .047413),
               (-.011820, .042940, .968881)),
    "tritan": ((1.255528, -.076749, -.178779),
               (-.078411, .930809, .147602),
               (.004733, .691367, .303900)),
}


def lab(color: str, vision: str = "normal") -> tuple[float, float, float]:
    if (not isinstance(color, str) or len(color) != 7 or
            not color.startswith("#") or
            any(c not in "0123456789abcdefABCDEF" for c in color[1:])):
        raise ValueError("expected #RRGGBB")
    encoded = tuple(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    def linear(x: float) -> float:
        return x / 12.92 if x <= .04045 else ((x+.055)/1.055)**2.4
    rgb = tuple(linear(v) for v in encoded)
    # Machado matrices operate on LINEAR-light RGB, not gamma-encoded sRGB.
    # The older gamma-space approximation overstates some CVD distances.
    if vision != "normal":
        m = MATRICES[vision]
        rgb = tuple(max(0., min(1., sum(a*b for a,b in zip(row,rgb))))
                    for row in m)
    red,green,blue = rgb
    x = (.4124564*red+.3575761*green+.1804375*blue)/.95047
    y = .2126729*red+.7151522*green+.072175*blue
    z = (.0193339*red+.119192*green+.9503041*blue)/1.08883
    def f(t: float) -> float:
        return t**(1/3) if t>.008856 else 7.787*t+16/116
    fx,fy,fz = f(x),f(y),f(z)
    return 116*fy-16,500*(fx-fy),200*(fy-fz)


def distance(a: str, b: str, vision: str = "normal") -> float:
    return math.dist(lab(a,vision),lab(b,vision))


def categorical_series_findings(
        colors: Sequence[str], *, minimum_normal: float = 24.,
        minimum_cvd: float = 9., focus_normal: float = 43.,
        focus_cvd: float = 19.) -> list[dict]:
    """Report only source-provable categorical-pair weaknesses.

    First two colors get stricter requirements because two-series line plots
    often use palette[0:2]. This is not applied to numeric gradients or
    conditional red/green statuses, whose colors encode business semantics.
    """
    results = []
    for i,j in itertools.combinations(range(len(colors)),2):
        if colors[i] == colors[j]:
            metrics = {"normal":0.,"protan":0.,"deutan":0.,"tritan":0.}
        else:
            metrics = {v:round(distance(colors[i],colors[j],v),2)
                       for v in ("normal",*MATRICES)}
        special = (i,j)==(0,1)
        norm_limit = focus_normal if special else minimum_normal
        cvd_limit = focus_cvd if special else minimum_cvd
        failed = [vision for vision,delta in metrics.items()
                  if delta < (norm_limit if vision=="normal" else cvd_limit)]
        if failed:
            results.append({
                "series_indices":[i,j], "colors":[colors[i],colors[j]],
                "normal_delta_e76":metrics["normal"],
                "cvd_delta_e76":{k:metrics[k] for k in MATRICES},
                "simulations_below_threshold":failed,
                "thresholds":{"normal":norm_limit,"cvd":cvd_limit},
                "category":"series_distinguishability",
            })
    return results
