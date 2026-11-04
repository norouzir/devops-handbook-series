# Azure & GCP for DevOps Engineers — Markdown Manuscript

> **Volume 9 of the [DevOps Handbook Series](../README.md).**

A Pandoc-buildable Markdown manuscript of the book **Azure & GCP for DevOps Engineers — A Practical Handbook for Multi-Cloud Delivery**
(first edition, October 2026; verified against az CLI 2.x with bundled Bicep, `azure/login` v3, `google-github-actions/auth` v3, and `actions/checkout` v7 as of October 2026 - Entra ID and RBAC, managed identities and federated credentials, Bicep deployments, VNets/NSGs and Blob storage, AKS with workload identity, Azure Functions and Container Apps, gcloud, IAM with Workload Identity Federation, Compute Engine and MIGs, Cloud Storage and Cloud SQL, GKE Autopilot, Cloud Run, and keyless GitHub Actions pipelines to both clouds).

The book is organized in **two parts**: Part I — Microsoft Azure (chapters 1–7) and
Part II — Google Cloud and Multi-Cloud Delivery (chapters 8–16), plus four appendices.
Hands-on labs appear in six key chapters: a Bicep stack you can break and rebuild, an AKS cluster with identity-aware pods, a keyless OIDC pipeline to Azure, a GKE Autopilot cluster with Workload Identity, a Cloud Run deploy with canary and rollback, and the three-cloud capstone that ships the same application to AWS, Azure, and GCP, measures it, and compares the bills.

## Repository layout

```
.
├── manuscript/            # the book — one file per part / chapter / appendix
│   ├── 01-preface.md
│   ├── 02-part-i-…md               # Part I divider (chapter list)
│   ├── 03-…09-chapter-*.md         # Part I: chapters 1-7
│   ├── 10-part-ii-…md              # Part II divider (chapter list)
│   ├── 11-…19-chapter-*.md         # Part II: chapters 8-16
│   └── 20-…23-appendix-*.md        # appendices A-D
├── build/
│   ├── metadata.yaml      # title / author / date / lang (used by all builds)
│   ├── html.yaml          # pandoc defaults → standalone HTML
│   ├── epub.yaml          # pandoc defaults → EPUB 3
│   ├── pdf.yaml           # pandoc defaults → print HTML for WeasyPrint
│   ├── style.css          # screen styles (blue-slate cloud theme + sidebar TOC)
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

Each format lands in `output/` as `Azure_GCP_for_DevOps_Engineers.html`, `Azure_GCP_for_DevOps_Engineers.epub`, and
`Azure_GCP_for_DevOps_Engineers.pdf`; `./build.sh` with no argument builds all three. The `make`
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
Part dividers and chapters carry `#part1`, `#ch1` … `#ch7`, `#part2`,
`#ch8` … `#ch16`; the appendices carry `#appA` … `#appD`.
Every hands-on lab has its own id, `#lab1` … `#lab6`.

## Editing the manuscript

- Each chapter is an ordinary Markdown file starting with a level-1 `#` heading; add, remove, or reorder files freely — the build picks up `manuscript/*.md` in alphabetical order.
- Part dividers (`02-part-i…`, `10-part-ii-…`) are short files with the part title and its chapter list; keep them between the chapters they introduce.
- Hands-on labs are fenced `::: {.lab}` divs whose first heading is `### Lab N - … {#labN}`; keep the id when you rename a lab.
- Callouts are Pandoc fenced divs: `::: {.note}`, `::: {.warn}`, `::: {.lab}` — the stylesheets already know them.
- Keep heading ids intact when renaming titles; links in other chapters depend on them.
