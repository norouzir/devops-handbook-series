# DevSecOps for DevOps Engineers — Markdown Manuscript

> **Volume 10 of the [DevOps Handbook Series](../README.md).**

A Pandoc-buildable Markdown manuscript of the book **DevSecOps for DevOps Engineers — A Practical Handbook for Securing the Pipeline**
(first edition, October 2026; verified against gitleaks v8, Semgrep 1.x, Trivy 0.6x, Cosign v2 on the Sigstore stack, Syft 1.x, Kyverno 1.1x, OPA Gatekeeper v3, OWASP ZAP 2.1x, Falco, kube-bench 0.1x, and `actions/checkout` v7 as of October 2026 - secrets detection and HashiCorp Vault with policies, AppRole, dynamic database credentials, and OIDC auth; least-privilege GitHub Actions with SHA-pinned actions and harden-runner; SAST with Semgrep and CodeQL; SCA with Dependabot and dependency review; container image security with distroless bases and Trivy gates; artifact signing, SBOMs, and SLSA provenance; a secured end-to-end build pipeline; Kyverno and Gatekeeper admission policies; NetworkPolicy and Falco runtime security; IaC scanning with Checkov; the OWASP Top 10 with ZAP baseline scans; security telemetry, incident response, compliance as code with kube-bench, and a scored red-team capstone).

The book is organized in **two parts**: Part I — Securing the Software Supply Chain (chapters 1–7) and
Part II — Runtime, Infrastructure, and Operations (chapters 8–16), plus four appendices.
Hands-on labs appear in six key chapters: a Vault you can break and rebuild, a repo with planted threats to catch, an image shrunk to a clean scan, a signed and tamper-tested artifact, a Kyverno rollout that rejects a violating deploy, and the scored red-team capstone that attacks the whole pipeline and turns every gap into a ticket. Chapter 3 adds a short workflow audit check in place of a lab.

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
│   ├── style.css          # screen styles (graphite-green security theme + sidebar TOC)
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

Each format lands in `output/` as `DevSecOps_for_DevOps_Engineers.html`, `DevSecOps_for_DevOps_Engineers.epub`, and
`DevSecOps_for_DevOps_Engineers.pdf`; `./build.sh` with no argument builds all three. The `make`
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
