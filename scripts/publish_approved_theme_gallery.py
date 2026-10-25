"""Publish all 14 approved palette families with genuine Light/Dark Desktop screenshots.

Input is the exact GitHub authoring artifact, after QVS source and native pixel
gates. No fabricated renderers, no token swatches disguised as screenshots.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path

from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
CAPTURE_DIMS=(3915,2394)
CROP=(0,264,3315,2140)
FEATURED=("sunny-palette","organic-palette","graphite-red",
          "indigo-ember","petrol-gold","riviera-pop","okabe-ito-night")
PAGES=(("Executive overview","executive-overview"),
       ("Products & brands","products-and-brands"))
DESCRIPTIONS={
 "sunny-palette":"Amber-orange and charcoal, with soft peach control surfaces.",
 "organic-palette":"Cobalt, vivid magenta, green and cyan with differentiated controls.",
 "graphite-red":"Graphite, ruby and carefully contrasted supporting hues — no green.",
 "indigo-ember":"Indigo-violet balanced with warm editorial accents.",
 "petrol-gold":"Petrol and warm gold for a confident executive dashboard.",
 "riviera-pop":"Expressive seaside color, controlled by a disciplined layout.",
 "okabe-ito-night":"Clear categorical hues and understated interface chrome.",
 "arctic-aurora":"Quiet glacier-inspired greens and blue-grey neutrals.",
 "mediterranean-terra":"Warm terracotta, sea hues and natural editorial neutrals.",
 "saffron-spruce":"Golden saffron with spruce-like support and structured controls.",
 "autumn-editorial":"Muted autumn colors with a calm analytical presentation.",
 "violet-ice":"Cool violet, pale blue and restrained supporting accents.",
 "electric-atelier":"Electric, contemporary hues with clear series separation.",
 "bold-eclectic":"Confident multicolor contrast with a purposeful interface."
}
def sha(path:Path)->str:
 return hashlib.sha256(path.read_bytes()).hexdigest()
def slug_anchor(name:str)->str:
 return name.replace("&","").replace("  "," ").lower().replace(" ","-")
def build(artifact:Path,commit:str)->dict:
 selection=json.loads((ROOT/"docs/APPROVED_THEME_SELECTION.json").read_text(
  encoding="utf8"))["presets"]
 names=[x["slug"] for x in selection]
 assert len(selection)==14 and len(set(names))==14
 assert set(FEATURED).issubset(names)
 ordered=list(FEATURED)+[x for x in names if x not in FEATURED]
 titles={x["slug"]:x["title"] for x in selection}
 dest=ROOT/"docs/images/adaptive-showcase"
 chips=ROOT/"docs/images/approved-themes/swatches"
 dest.mkdir(parents=True,exist_ok=True);chips.mkdir(parents=True,exist_ok=True)
 provenance={
  "schema":"vqs.public-theme-showcase/2",
  "authoringHead":commit,
  "source":"five-page fictional Contoso Retail PBIP; exact GitHub-authored candidates",
  "captureHost":"Microsoft Power BI Desktop, verified model refresh, native PNG capture",
  "galleryModes":28,"displayedPagesPerMode":2,"rawPagesPerMode":5,
  "modes":{}}
 for slug in ordered:
  for mode in ("light","dark"):
   key=f"{slug}-{mode}"
   candidate=artifact/key
   source=candidate/"theme-manifest.json"
   manifest=json.loads(source.read_text(encoding="utf8"))
   assert manifest["mode"]==mode and manifest["counts"]["blocked"]==0
   assert manifest["counts"]["unknown"]==0
   assert manifest["candidateDigest"] and manifest["modelDigest"]
   capt=artifact/"captures"/key
   raw_files=sorted(capt.glob("*.png"))
   assert len(raw_files)==5,(key,len(raw_files))
   hashes={}
   for f in raw_files:
    with Image.open(f) as im:
     assert im.size==CAPTURE_DIMS,(key,f.name,im.size)
    hashes[f.stem]=sha(f)
   published=dest/key
   published.mkdir(exist_ok=True)
   allowed={n+".webp" for _,n in PAGES}
   for old in published.glob("*.webp"):
    if old.name not in allowed:old.unlink()
   entries=[]
   for page,short in PAGES:
    source_file=capt/(page+".png")
    with Image.open(source_file) as image:
     view=image.convert("RGB").crop(CROP)
     view.thumbnail((1680,1080),Image.Resampling.LANCZOS)
     path=published/(short+".webp")
     view.save(path,"WEBP",quality=85,method=6)
    assert path.stat().st_size>20000,(key,path.name)
    entries.append({
     "page":page,"file":path.relative_to(ROOT).as_posix(),
     "captureSha256":hashes[page],"webpSha256":sha(path),
     "captureDimensions":list(CAPTURE_DIMS),
     "publicCanvasCropBox":list(CROP),
     "publicDimensions":list(Image.open(path).size)})
   provenance["modes"][key]={
    "sourceDigest":manifest["sourceDigest"],
    "candidateDigest":manifest["candidateDigest"],
    "paletteHash":manifest["paletteHash"],
    "modelDigest":manifest["modelDigest"],
    "rawPageSha256":hashes,
    "screenshots":entries}
   item=next(x for x in selection if x["slug"]==slug)
   palette=json.loads((ROOT/item["resource"]).read_text(encoding="utf8"))[mode]
   # Swatches additionally show a genuine closed-dropdown/control shade and
   # selection fill. Unlike the images, these SVGs are token visualizations.
   bg, surface=palette["canvas"],palette["surface"]
   fg, faded=palette["foreground"],palette["mutedForeground"]
   nav,nav_fg=palette["slicerBackground"],palette["slicerForeground"]
   selected,selected_fg=palette["selection"],palette["selectionForeground"]
   svg=['<svg xmlns="http://www.w3.org/2000/svg" width="840" height="204" viewBox="0 0 840 204">',
        f'<rect width="840" height="204" rx="18" fill="{bg}"/>',
        f'<rect x="12" y="12" width="816" height="180" rx="12" fill="{surface}"/>',
        f'<text x="30" y="46" fill="{fg}" font-family="Segoe UI,Arial,sans-serif" font-size="21" font-weight="600">{html.escape(titles[slug])}</text>',
        f'<text x="30" y="73" fill="{faded}" font-family="Segoe UI,Arial,sans-serif" font-size="15">{mode.title()} · real theme tokens</text>']
   for i,color in enumerate(palette["dataColors"][:8]):
    svg.append(f'<rect x="{30+i*96}" y="91" width="86" height="35" rx="7" fill="{color}"/>')
   svg.extend([
      f'<rect x="30" y="145" width="384" height="39" rx="8" fill="{nav}"/>',
      f'<text x="44" y="170" font-family="Segoe UI,Arial,sans-serif" font-size="16" fill="{nav_fg}">Reporting year   ▾</text>',
      f'<rect x="430" y="145" width="160" height="39" rx="8" fill="{selected}"/>',
      f'<text x="448" y="170" font-family="Segoe UI,Arial,sans-serif" font-size="16" fill="{selected_fg}">Selected</text>',
      '</svg>'])
   (chips/key).with_suffix(".svg").write_text("\n".join(svg)+"\n",encoding="utf8")
   print("PUBLISH_MODE",key,"PAGES",len(raw_files),"WEBP",len(entries),flush=True)
 assert len(provenance["modes"])==28
 assert sum(len(x["screenshots"]) for x in provenance["modes"].values())==56
 (dest/"PROVENANCE.json").write_text(json.dumps(provenance,indent=2)+"\n",encoding="utf8")
 readme=(ROOT/"README.md").read_text(encoding="utf8")
 start=readme.index("## Real Power BI showcase")
 end=readme.index("## Try it",start)
 section=["## Real Power BI showcase","",
  "**Seven curated families on the homepage. All 14 Light/Dark families in the full gallery.**",
  "These are real, populated Power BI Desktop screenshots captured from one",
  "fictional Contoso Retail report; none is a simulated dashboard.",
  "Each screenshot is bound to the generating GitHub candidate and source hash.","",
  "**[Explore the complete 14-family native gallery](docs/REAL_THEME_SHOWCASE.md)** ·",
  "[Compare all color and control tokens](docs/APPROVED_THEME_LIBRARY.md) ·",
  "[View the provenance](docs/images/adaptive-showcase/PROVENANCE.json)",""]
 for slug in FEATURED:
  title=titles[slug]
  a=f"docs/images/adaptive-showcase/{slug}-light/executive-overview.webp"
  b=f"docs/images/adaptive-showcase/{slug}-dark/executive-overview.webp"
  section.extend([f"### {title}","",DESCRIPTIONS[slug],"",
   "| Light · actual report | Dark · actual report |",
   "| :--- | :--- |",
   f"| [![{title} Light real Power BI report]({a})](docs/REAL_THEME_SHOWCASE.md#{slug}) | [![{title} Dark real Power BI report]({b})](docs/REAL_THEME_SHOWCASE.md#{slug}) |",""])
 section+=["**[See all 14 palettes and 56 authentic report previews](docs/REAL_THEME_SHOWCASE.md)**","",
  "The gallery also shows Products & Brands, making all seven subcategory",
  "colors easy to compare. Each control palette includes themed dropdown,",
  "filter and selection surfaces. Interactive flyouts remain separately",
  "reviewable; static screenshots are not interaction certification.","",""]
 (ROOT/"README.md").write_text(readme[:start]+"\n".join(section)+readme[end:],encoding="utf8",newline="\n")
 # Full gallery with accessible navigation, two genuine pages per Light/Dark mode.
 gallery=["# All 14 Power BI themes — real Desktop gallery","",
  "**14 approved families · 28 Light/Dark variants · 56 real report screenshots.**",
  "The seven-feature homepage is intentionally curated; this page is the complete",
  "collection, with both an Executive and a Products & Brands screenshot for",
  "every theme. All versions come from one identical synthetic Contoso report.",
  "There are no generated dashboard mockups or counterfeit report images.","",
  "[Back to curated homepage](../README.md#real-power-bi-showcase) ·",
  "[Palette and dropdown-control colors](APPROVED_THEME_LIBRARY.md) ·",
  "[Exact candidate and image hashes](images/adaptive-showcase/PROVENANCE.json)","",
  "## Explore the themes","",
  "| Featured seven | Additional seven |",
  "| :--- | :--- |"]
 other=[s for s in ordered if s not in FEATURED]
 for i in range(7):
  gallery.append(f"| [{titles[FEATURED[i]]}](#{FEATURED[i]}) | [{titles[other[i]]}](#{other[i]}) |")
 for heading,slugs in (("Curated seven",FEATURED),("The other seven",other)):
  gallery.extend(["",f"## {heading}",""])
  for slug in slugs:
   title=titles[slug]
   gallery.extend([f'<a id="{slug}"></a>',f"### {title}","",
    DESCRIPTIONS[slug],"",
    f"![{title} Light palette and dropdown-control token colors](images/approved-themes/swatches/{slug}-light.svg)","",
    "**Executive overview — Light / Dark**","",
    "| Light | Dark |","| :--- | :--- |",
    f"| ![{title} Light Executive actual Power BI screenshot](images/adaptive-showcase/{slug}-light/executive-overview.webp) | ![{title} Dark Executive actual Power BI screenshot](images/adaptive-showcase/{slug}-dark/executive-overview.webp) |","",
    "**Products & Brands — Light / Dark**","",
    "| Light | Dark |","| :--- | :--- |",
    f"| ![{title} Light Products real Power BI screenshot](images/adaptive-showcase/{slug}-light/products-and-brands.webp) | ![{title} Dark Products real Power BI screenshot](images/adaptive-showcase/{slug}-dark/products-and-brands.webp) |","",
    f"[Color and control tokens](APPROVED_THEME_LIBRARY.md#{slug}) · [Image provenance](images/adaptive-showcase/PROVENANCE.json)",""])
 gallery+=["## Verification boundaries","",
  "These are source-matched Desktop screenshots of default page states after",
  "model refresh. Native pixel checks verify assigned category colors and the",
  "closed dropdown/control surface. They do **not** certify the appearance of",
  "open filter menus, flyout search, every slicer selection, or every report.",
  "Independent visual G2, functional G4 and owner G6 release acceptance",
  "are separate requirements; this draft PR is not a production release.",""]
 (ROOT/"docs/REAL_THEME_SHOWCASE.md").write_text("\n".join(gallery).rstrip()+"\n",encoding="utf8")
 library=["# Approved Power BI theme library — 14 families, 28 modes","",
  "All 14 themes are registered as distinct native Light and Dark presets;",
  "four older compatibility presets remain unchanged. This compact reference",
  "shows genuine **palette and control tokens**, including dropdown surfaces",
  "and selected states. For **actual Power BI Desktop screenshots of every",
  "family**, use the [full gallery](REAL_THEME_SHOWCASE.md).","",
  "| Family / screenshots | Light · palette and controls | Dark · palette and controls |",
  "| :--- | :--- | :--- |"]
 for slug in ordered:
  t=titles[slug]
  library.append(f"| **[{t}](REAL_THEME_SHOWCASE.md#{slug})** | ![{t} Light tokens](images/approved-themes/swatches/{slug}-light.svg) | ![{t} Dark tokens](images/approved-themes/swatches/{slug}-dark.svg) |")
 library+=["","## Safe use","",
  "Use `vqs theme inspect/preview/apply/audit` for source-safe candidates.",
  "For screen-visible proof, open the generated PBIP in Power BI Desktop,",
  "refresh the model, then capture and review the actual target state.",
  "Colors are generic palette designs, not claims of external affiliation.",
  "The color-vision checks are engineering screening thresholds, not a",
  "guarantee of accessibility or live interaction behavior.",""]
 (ROOT/"docs/APPROVED_THEME_LIBRARY.md").write_text("\n".join(library).rstrip()+"\n",encoding="utf8")
 print("GALLERY_COMPLETED",28,56,len(ordered)*2,"control swatches",flush=True)
 return provenance

def main()->int:
 p=argparse.ArgumentParser()
 p.add_argument("artifact",type=Path)
 p.add_argument("--authoring-head",required=True)
 a=p.parse_args()
 assert len(a.authoring_head)==40 and all(c in "0123456789abcdef" for c in a.authoring_head)
 build(a.artifact,a.authoring_head)
 return 0
if __name__=="__main__":
 raise SystemExit(main())
