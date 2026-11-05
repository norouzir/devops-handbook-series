#!/usr/bin/env python3
"""Assemble the GitHub Pages site from the built HTML of every volume.

Each volume's HTML build is already a single self-contained file — build/html.yaml
sets both `standalone` and `embed-resources` — so publishing the series as a
website is only a layout problem: one landing page that lists the volumes in
reading order, and one directory per volume so its address is `/01-docker/`
rather than a long file name.

    python3 tools/make_site.py --out site

The script reads `books/*/output/*.html`, so `make html` has to run first; a
volume that was not built is reported by name instead of leaving a hole in the
site. Nothing it writes is committed: `site/` is git-ignored and rebuilt by
`.github/workflows/pages.yml` on every push to `main`.
"""

from __future__ import annotations

import argparse
import html
import pathlib
import re
import shutil
from dataclasses import dataclass

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO_URL = "https://github.com/norouzir/devops-handbook-series"
RELEASES_URL = f"{REPO_URL}/releases"
LICENSE_URL = f"{REPO_URL}/blob/main/LICENSE"

ACCENT_RE = re.compile(r"--accent:\s*(#[0-9A-Fa-f]{3,8})")
DEFAULT_ACCENT = "#1A6DA8"


@dataclass(frozen=True)
class Volume:
    folder: str
    number: int
    title: str
    subtitle: str
    date: str
    accent: str
    html_file: pathlib.Path


def load_volumes(books_dir: pathlib.Path) -> list[Volume]:
    """Read every volume's metadata and built HTML, sorted by series number."""
    volumes: list[Volume] = []
    for book in sorted(p for p in books_dir.iterdir() if p.is_dir()):
        meta_path = book / "build" / "metadata.yaml"
        if not meta_path.is_file():
            continue

        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        outputs = sorted((book / "output").glob("*.html"))
        if len(outputs) != 1:
            raise SystemExit(
                f"{book.name}: expected one HTML file in output/, found {len(outputs)}"
                " — run ./build.sh html (or `make html`) first"
            )

        style = book / "build" / "style.css"
        accent = ACCENT_RE.search(style.read_text(encoding="utf-8")) if style.is_file() else None

        number = meta.get("volume")
        if not isinstance(number, int):
            prefix = book.name.split("-", 1)[0]
            number = int(prefix) if prefix.isdigit() else len(volumes) + 1

        volumes.append(
            Volume(
                folder=book.name,
                number=number,
                title=str(meta.get("title") or book.name),
                subtitle=str(meta.get("subtitle") or ""),
                date=str(meta.get("date") or ""),
                accent=accent.group(1) if accent else DEFAULT_ACCENT,
                html_file=outputs[0],
            )
        )

    if not volumes:
        raise SystemExit(f"no volumes with build/metadata.yaml under {books_dir}")

    numbers = [v.number for v in volumes]
    if len(set(numbers)) != len(numbers):
        raise SystemExit(f"duplicate volume numbers in metadata: {sorted(numbers)}")
    return sorted(volumes, key=lambda v: v.number)


# The book HTML keeps its own stylesheet; this adds only the pill that leads
# back to the series index, so a reader who lands on a volume is never stuck.
SERIES_NAV_CSS = """
.series-nav{position:fixed;right:1rem;bottom:1rem;z-index:100;display:inline-flex;
  align-items:center;gap:.4rem;padding:.5rem .85rem;border-radius:999px;
  background:#0D1B2A;color:#EAF3FB;border:1px solid #2496ED;
  font-family:"Helvetica Neue","Carlito","Liberation Sans",Arial,sans-serif;
  font-size:.78rem;line-height:1;text-decoration:none;
  box-shadow:0 2px 10px rgba(13,27,42,.28)}
.series-nav:hover{background:#17547F;color:#FFFFFF;text-decoration:none}
.series-nav-mark{font-size:.95rem;line-height:1}
@media print{.series-nav{display:none}}
"""


def add_series_nav(markup: str, volume: Volume) -> str:
    """Insert the return-to-index pill into a volume's self-contained HTML."""
    if "</head>" not in markup or "<body" not in markup:
        raise SystemExit(
            f"{volume.folder}: built HTML has no </head> or <body>; cannot attach navigation"
        )
    nav = (
        f'<a class="series-nav" href="../" style="border-color:{volume.accent}"'
        ' title="DevOps Handbook Series — all ten volumes">'
        '<span class="series-nav-mark">&larr;</span>All volumes'
        "</a>"
    )
    markup = markup.replace("</head>", f"<style>{SERIES_NAV_CSS}</style>\n</head>", 1)
    return re.sub(r"<body[^>]*>", lambda m: f"{m.group(0)}\n{nav}", markup, count=1)


INDEX_CSS = """
:root{
  --navy:#0D1B2A; --head:#17547F; --blue:#1A6DA8; --accent:#2496ED;
  --body:#1A1A1A; --muted:#6B7784; --line:#D2DFEC; --paper:#FFFFFF;
  --serif:Georgia,"Tinos","Liberation Serif","Times New Roman",serif;
  --sans:"Helvetica Neue","Carlito","Liberation Sans",Arial,sans-serif;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:#FBFCFD;color:var(--body);font-family:var(--serif);
  line-height:1.62;font-size:17px}
a{color:var(--blue)}
.wrap{max-width:64rem;margin:0 auto;padding:0 1.25rem}

.cover{background:var(--navy);color:#EAF3FB;text-align:center;
  border-top:3px solid var(--accent);border-bottom:3px solid var(--accent);
  padding:4rem 1.25rem 3.2rem}
.cover .eyebrow{font-family:var(--sans);font-size:.8rem;font-weight:700;
  letter-spacing:.16em;text-transform:uppercase;color:#7FB6E4;margin:0 0 1rem}
.cover h1{font-family:var(--sans);font-size:clamp(1.7rem,4vw,2.6rem);
  line-height:1.22;font-weight:700;margin:0 auto 1rem;max-width:34rem}
.cover .lede{color:#C4DAED;font-size:1.05rem;max-width:36rem;margin:0 auto 1.5rem}
.cover .meta{font-family:var(--sans);font-size:.82rem;color:#A6C0D8;margin:0}
.cover .meta span+span::before{content:"·";margin:0 .5rem;color:#4E6b85}

main{padding:3rem 0 1rem}
.section-head{display:flex;align-items:baseline;justify-content:space-between;
  gap:1rem;flex-wrap:wrap;margin:0 0 1.4rem;border-bottom:2px solid var(--blue);
  padding-bottom:.55rem}
.section-head h2{font-size:1.3rem;color:var(--head);margin:0}
.section-head p{font-family:var(--sans);font-size:.82rem;color:var(--muted);margin:0}

.volumes{list-style:none;margin:0;padding:0;display:grid;gap:1rem;
  grid-template-columns:repeat(auto-fill,minmax(19rem,1fr))}
.volume{display:flex;flex-direction:column;gap:.35rem;height:100%;
  background:var(--paper);border:1px solid var(--line);
  border-left:4px solid var(--accent,#2496ED);border-radius:4px;
  padding:1.15rem 1.3rem 1.05rem;text-decoration:none;color:inherit;
  transition:transform .12s ease,box-shadow .12s ease}
.volume:hover{transform:translateY(-2px);box-shadow:0 6px 18px rgba(13,27,42,.10)}
.volume-number{font-family:var(--sans);font-size:.78rem;font-weight:700;
  letter-spacing:.14em;color:var(--accent,#2496ED)}
.volume-title{font-family:var(--sans);font-size:1.06rem;font-weight:700;
  color:var(--head);line-height:1.3}
.volume-subtitle{font-size:.9rem;color:var(--muted);font-style:italic;line-height:1.45}
.volume-cta{margin-top:auto;padding-top:.6rem;font-family:var(--sans);
  font-size:.8rem;font-weight:700;color:var(--blue)}
.volume:hover .volume-cta{text-decoration:underline}

footer{border-top:1px solid var(--line);margin-top:2.5rem;padding:1.6rem 0 3rem;
  font-family:var(--sans);font-size:.82rem;color:var(--muted)}
footer p{margin:.35rem 0}
"""


def render_index(volumes: list[Volume]) -> str:
    """Build the landing page: a cover block and the ten volumes in order."""
    cards = "\n".join(
        "      <li>"
        f'<a class="volume" href="./{html.escape(v.folder)}/" style="--accent:{v.accent}">'
        f'<span class="volume-number">{v.number:02d}</span>'
        f'<span class="volume-title">{html.escape(v.title)}</span>'
        f'<span class="volume-subtitle">{html.escape(v.subtitle)}</span>'
        '<span class="volume-cta">Read online &rarr;</span>'
        "</a>"
        "</li>"
        for v in volumes
    )

    date = next((v.date for v in volumes if v.date), "")
    meta = [f"{len(volumes)} volumes"]
    if date:
        meta.append(date)
    meta.append("CC BY 4.0")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DevOps Handbook Series</title>
<meta name="description" content="Ten self-contained handbooks that teach the DevOps toolchain the way it is actually used — one tool per volume, from first principles to production operations.">
<style>{INDEX_CSS}</style>
</head>
<body>
<header class="cover">
  <div class="wrap">
    <p class="eyebrow">DevOps Handbook Series</p>
    <h1>Ten handbooks that teach the DevOps toolchain the way it is actually used</h1>
    <p class="lede">One tool per volume, from first principles to production operations. Each
      volume is a complete book rather than a chapter of one large text, but they share a
      sequence, a voice, and a set of conventions — so they can be read in order or picked up
      individually.</p>
    <p class="meta">{"".join(f"<span>{html.escape(m)}</span>" for m in meta)}</p>
  </div>
</header>

<main class="wrap">
  <div class="section-head">
    <h2>The volumes</h2>
    <p>In reading order · each opens as one page with its contents in the sidebar</p>
  </div>
  <ol class="volumes">
{cards}
  </ol>
</main>

<footer>
  <div class="wrap">
    <p>PDF and EPUB editions of every volume are attached to the
      <a href="{RELEASES_URL}">latest release</a>.</p>
    <p>Sources, build scripts, and the manuscript are in the
      <a href="{REPO_URL}">repository</a>; the text is licensed
      <a href="{LICENSE_URL}">CC BY 4.0</a>.</p>
  </div>
</footer>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out", default=ROOT / "site", type=pathlib.Path,
        help="output directory (default: site/)",
    )
    parser.add_argument(
        "--books", default=ROOT / "books", type=pathlib.Path,
        help="directory holding the volumes (default: books/)",
    )
    args = parser.parse_args(argv)

    volumes = load_volumes(args.books)

    out = args.out if args.out.is_absolute() else ROOT / args.out
    out = out.resolve()
    if out == ROOT or out in ROOT.parents:
        raise SystemExit(f"refusing to replace {out}: pick a subdirectory of the repository")

    # Written in place rather than recreated: a local `python -m http.server`
    # keeps its working directory open, and deleting the tree under it fails
    # on Windows. Only the pages this script owns are touched, plus directories
    # left behind by a volume that no longer exists.
    out.mkdir(parents=True, exist_ok=True)

    (out / "index.html").write_text(render_index(volumes), encoding="utf-8")
    total = (out / "index.html").stat().st_size
    for volume in volumes:
        target = out / volume.folder
        target.mkdir(exist_ok=True)
        page = target / "index.html"
        page.write_text(add_series_nav(volume.html_file.read_text(encoding="utf-8"), volume),
                        encoding="utf-8")
        total += page.stat().st_size
        print(f"  {volume.folder + '/':<26} {volume.title}")

    expected = {v.folder for v in volumes}
    for child in sorted(out.iterdir()):
        if child.is_dir() and child.name not in expected:
            shutil.rmtree(child)
            print(f"  removed stale {child.name}/")

    print(f"site: {out}  ({len(volumes)} volumes, {total / 1024 / 1024:.1f} MiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
