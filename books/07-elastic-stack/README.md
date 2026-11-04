# Elastic Stack for DevOps Engineers — Markdown Manuscript

> **Volume 7 of the [DevOps Handbook Series](../README.md).**

A Pandoc-buildable Markdown manuscript of the book **Elastic Stack for DevOps Engineers — A Practical Handbook for Search, Logs, and Observability**
(first edition, October 2026; verified against Elasticsearch 9.5, Kibana 9.5, and Logstash 9.5 as of October 2026 - Query DSL, ES|QL, Elastic Agent and Fleet, data streams and ILM, hot-warm-cold tiering, snapshots and SLM, and ECK 3.x on Kubernetes).

The book is organized in **two parts**: Part I — Elasticsearch Foundations (chapters 1–8) and
Part II — Production Elastic (chapters 9–14), plus three appendices.
Hands-on labs appear in five key chapters: the core Elasticsearch and Kibana stack with first documents, shipping Nginx logs through Filebeat with an ingest pipeline, a structured log search with the Query DSL, a Kibana analytics dashboard over aggregations, and a snapshot policy with a rehearsed restore drill.

## Repository layout

```
.
├── manuscript/            # the book — one file per part / chapter / appendix
│   ├── 01-preface.md
│   ├── 02-part-i-…md               # Part I divider (chapter list)
│   ├── 03-…10-chapter-*.md         # Part I: chapters 1-8
│   ├── 11-part-ii-…md              # Part II divider (chapter list)
│   ├── 12-…17-chapter-*.md         # Part II: chapters 9-14
│   └── 18-…20-appendix-*.md        # appendices A-C
├── build/
│   ├── metadata.yaml      # title / author / date / lang (used by all builds)
│   ├── html.yaml          # pandoc defaults → standalone HTML
│   ├── epub.yaml          # pandoc defaults → EPUB 3
│   ├── pdf.yaml           # pandoc defaults → print HTML for WeasyPrint
│   ├── style.css          # screen styles (deep-navy search theme + sidebar TOC)
│   ├── print.css          # paged-media rules for WeasyPrint (PDF)
│   ├── epub.css           # conservative styles for e-readers
│   └── epub-cover.png     # EPUB cover image (regenerate: python3 tools/make_covers.py)
├── build.sh               # one-command build for all formats
├── Makefile               # incremental rebuilds
└── output/                # build results land here
```

## Requirements

| Tool | Used for | Install |
|------|----------|---------|
| pandoc ≥ 2.19 | all builds | `apt install pandoc` / <https://pandoc.org> |
| WeasyPrint ≥ 53 | PDF build | `pip install weasyprint` |
| (optional) make | incremental builds | preinstalled on most systems |

## Build

```bash
./build.sh            # everything: HTML + EPUB + PDF
./build.sh html       # single self-contained HTML file
./build.sh epub       # EPUB 3 with cover
./build.sh pdf        # print PDF via WeasyPrint
```

Each format lands in `output/` as `Elastic_Stack_for_DevOps_Engineers.html`, `Elastic_Stack_for_DevOps_Engineers.epub`, and
`Elastic_Stack_for_DevOps_Engineers.pdf`; `./build.sh` with no argument builds all three. The `make`
targets (`make`, `make html`, `make epub`, `make pdf`, `make clean`) run the
same steps through the volume Makefile.

## Navigation features (bookmarks and links)

Every heading in the manuscript carries an explicit Pandoc identifier, so
anchors are stable across all three formats:

- **PDF** — WeasyPrint turns every `h1`–`h3` into a PDF outline bookmark
  (the sidebar "bookmarks" tree in any PDF reader), the table of contents
  shows real page numbers with leader dots (`target-counter`), and the TOC
  entries plus every in-text cross-reference are clickable internal links.
- **EPUB** — the EPUB 3 `nav.xhtml` table of contents plus NCX for older
  readers; chapters split at `h1` for snappy section navigation.
- **HTML** — a sticky sidebar table of contents on wide screens, a normal
  contents block on small ones; every heading is an anchor target.

Cross-references inside the text are ordinary Markdown links to the explicit
ids, e.g. `[Chapter 6](#ch6)`, `[Lab 2](#lab2)`, `[Appendix A](#appA)`.
Part dividers and chapters carry `#part1`, `#ch1` … `#ch8`, `#part2`,
`#ch9` … `#ch14`; the appendices carry `#appA` … `#appC`.
Every hands-on lab has its own id, `#lab1` … `#lab5`.
Often-linked sections keep their own ids too: `#ch4-pipelines` (ingest
pipelines), `#ch7-buckets` (bucket aggregations), `#ch7-composing`
(composing aggregations).

## Editing the manuscript

- Each chapter is an ordinary Markdown file starting with a level-1 `#` heading; add, remove, or reorder files freely — the build picks up `manuscript/*.md` in alphabetical order.
- Part dividers (`02-part-i…`, `11-part-ii-…`) are short files with the part title and its chapter list; keep them between the chapters they introduce.
- Hands-on labs are fenced `::: {.lab}` divs whose first heading is `### Lab N - … {#labN}`; keep the id when you rename a lab.
- Callouts are Pandoc fenced divs: `::: {.note}`, `::: {.warn}`, `::: {.lab}` — the stylesheets already know them.
- Keep heading ids intact when renaming titles; links in other chapters depend on them.
