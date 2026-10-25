"""Native Contoso screenshot pixel gate: all named category fills, not three.

Use only after the per-category source gate and five-page Desktop capture:
  python scripts/theme_native_category_pixel_gate.py CAPTURE_ARTIFACT_ROOT

Validates screenshot pixels inside individual chart regions against exact
active theme tokens, including ALL SEVEN product subcategories, the
three GM-target bars and region variance bars that previously collided.
Coordinates are deliberately source-specific to the fixed 3915x2394
Contoso sample; this is evidence, NOT a generic screenshot color oracle.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from vqs.series_readability import distance
from vqs.theme import load_palette, source_digest

CANVAS=(3915,2394)
# Chart interior rectangles in actual native Power BI Desktop captures.
CHARTS=(
 ("Executive overview","monthly-sales-line",(230,870,2100,1380),2),
 ("Executive overview","regional-bars",(2390,875,3260,1390),3),
 ("Executive overview","gm-target-bars",(1445,1610,3220,1950),3),
 ("Markets & drivers","regional-variance",(350,975,2200,1460),3),
 ("Markets & drivers","retail-vs-online",(2300,980,3200,1450),2),
 ("Markets & drivers","sales-by-category",(390,1590,2200,2030),3),
 ("Products & brands","brand-bars",(315,855,1370,1420),5),
 ("Products & brands","subcategory-bars",(1550,850,3300,1420),7),
 ("Stores & customers","store-bars",(335,860,1570,1450),5),
 ("Stores & customers","segment-bars",(1745,855,3180,1450),3),
)
SHOWCASE=("sunny-palette","organic-palette",
          "graphite-red","indigo-ember","petrol-gold")
MIN_MATCHED_PIXELS=170


def verify(artifact: Path) -> dict:
    assert len(list(artifact.glob("*/Contoso Retail.pbip")))==28
    original=ROOT/"examples/contoso-retail/Contoso Retail.Report"
    digest=source_digest(original)
    checks=[]
    for slug in SHOWCASE:
        for mode in ("light","dark"):
            name=f"{slug}-{mode}"
            root=artifact/name
            manifest=json.loads((root/"theme-manifest.json").read_text("utf8"))
            assert manifest["sourceDigest"]==digest,(name,"stale source")
            colors=load_palette(mode,None,slug)["dataColors"]
            for page,chart,region,count in CHARTS:
                path=artifact/"captures"/name/(page+".png")
                assert path.stat().st_size>=15000,path
                with Image.open(path) as img:
                    assert img.size==CANVAS,(name,page,img.size)
                    pixels=np.asarray(img.convert("RGB").crop(region),dtype=np.int16)
                matches={}
                for idx in range(count):
                    col=colors[idx]
                    rgb=np.array([int(col[i:i+2],16) for i in (1,3,5)])
                    hits=int(np.count_nonzero(
                        np.max(np.abs(pixels-rgb),axis=2)<=6))
                    matches[col]=hits
                    assert hits>=MIN_MATCHED_PIXELS,(
                        name,page,chart,idx,col,hits)
                for i in range(count):
                    for j in range(i+1,count):
                        normal=distance(colors[i],colors[j])
                        cv=min(distance(colors[i],colors[j],eye)
                               for eye in ("protan","deutan","tritan"))
                        normal_limit,cv_limit=(
                            (50,19) if count<=3 else (45,15))
                        assert normal>=normal_limit and cv>=cv_limit,(
                            name,chart,i,j,round(normal,2),round(cv,2))
                checks.append({"mode":name,"page":page,"chart":chart,
                               "categoryCount":count,"pixelHits":matches})
                print("DESKTOP_CATEGORY_PIXELS_PASS",name,chart,
                      "categories",count,flush=True)
    return {"schema":"vqs.native-category-pixel-gate/1",
            "sourceDigest":digest,"modes":10,"checks":len(checks),
            "status":"pass","charts":checks}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact",type=Path)
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    try:
        result=verify(args.artifact)
    except (AssertionError,OSError,ValueError,KeyError) as exc:
        print("CATEGORY_PIXEL_GATE_FAILED",repr(exc),flush=True)
        return 1
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(result,indent=2)+"\n",encoding="utf8")
    print("TOTAL_DESKTOP_CATEGORY_PIXEL_CHECKS",result["checks"],flush=True)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
