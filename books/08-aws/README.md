# AWS for DevOps Engineers — Markdown Manuscript

> **Volume 8 of the [DevOps Handbook Series](../README.md).**

A Pandoc-buildable Markdown manuscript of the book **AWS for DevOps Engineers — A Practical Handbook for Compute, Networking, and Automation**
(first edition, October 2026; verified against AWS CLI v2, Amazon Linux 2023, and `aws-actions/configure-aws-credentials` v6 as of October 2026 - IAM roles and OIDC federation, EC2 with IMDSv2 and Graviton, VPC design, S3 storage classes and lifecycle, RDS Multi-AZ and backups, EKS with IRSA and the ALB controller, Lambda, CloudWatch, Terraform remote state, and AWS Budgets).

The book is organized in **two parts**: Part I — AWS Foundations (chapters 1–8) and
Part II — Operating AWS at Scale (chapters 9–12), plus three appendices.
Hands-on labs appear in five key chapters: launching and snapshotting a real EC2 instance, building a two-tier two-AZ VPC from scratch, a versioned and life-cycled S3 bucket with a static site, an end-to-end EKS cluster with an ALB and a pod-level IAM role, and an OIDC GitHub Actions pipeline that deploys to EKS with no stored credentials.

## Repository layout

```
.
├── manuscript/            # the book — one file per part / chapter / appendix
│   ├── 01-preface.md
│   ├── 02-part-i-…md               # Part I divider (chapter list)
│   ├── 03-…10-chapter-*.md         # Part I: chapters 1-8
│   ├── 11-part-ii-…md              # Part II divider (chapter list)
│   ├── 12-…15-chapter-*.md         # Part II: chapters 9-12
│   └── 16-…18-appendix-*.md        # appendices A-C
├── build/
│   ├── metadata.yaml      # title / author / date / lang (used by all builds)
│   ├── html.yaml          # pandoc defaults → standalone HTML
│   ├── epub.yaml          # pandoc defaults → EPUB 3
│   ├── pdf.yaml           # pandoc defaults → print HTML for WeasyPrint
│   ├── style.css          # screen styles (navy-and-orange cloud theme + sidebar TOC)
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

Each format lands in `output/` as `AWS_for_DevOps_Engineers.html`, `AWS_for_DevOps_Engineers.epub`, and
`AWS_for_DevOps_Engineers.pdf`; `./build.sh` with no argument builds all three. The `make`
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
`#ch9` … `#ch12`; the appendices carry `#appA` … `#appC`.
Every hands-on lab has its own id, `#lab1` … `#lab5`.
The API Gateway section keeps `#ch8-api`.

## Editing the manuscript

- Each chapter is an ordinary Markdown file starting with a level-1 `#` heading; add, remove, or reorder files freely — the build picks up `manuscript/*.md` in alphabetical order.
- Part dividers (`02-part-i…`, `11-part-ii-…`) are short files with the part title and its chapter list; keep them between the chapters they introduce.
- Hands-on labs are fenced `::: {.lab}` divs whose first heading is `### Lab N - … {#labN}`; keep the id when you rename a lab.
- Callouts are Pandoc fenced divs: `::: {.note}`, `::: {.warn}`, `::: {.lab}` — the stylesheets already know them.
- Keep heading ids intact when renaming titles; links in other chapters depend on them.
