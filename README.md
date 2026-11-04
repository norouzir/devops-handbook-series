# DevOps Handbook Series

Ten self-contained handbooks that teach the DevOps toolchain the way it is actually used:
one tool per volume, from first principles to production operations. Each volume is a complete
book rather than a chapter of one large text, but they share a sequence, a voice, and a set of
conventions, so they can be read in order or picked up individually.

**10 volumes · 140 chapters · 61 hands-on labs · ~205,000 words**

## The volumes

| # | Volume | Folder | Focus | Ch. | Labs |
|---|--------|--------|-------|-----|------|
| 1 | [Docker for DevOps Engineers](books/01-docker/README.md) | `books/01-docker` | Images and Dockerfiles, BuildKit, volumes, networking, Compose, securing Docker, CI/CD | 13 | 13 |
| 2 | [Kubernetes for DevOps Engineers](books/02-kubernetes/README.md) | `books/02-kubernetes` | Mental model, cluster anatomy, workloads, config, networking, storage, Helm/Kustomize, security, GitOps | 14 | 5 |
| 3 | [GitHub Actions for DevOps Engineers](books/03-github-actions/README.md) | `books/03-github-actions` | Workflow syntax, runners, matrices, OIDC, reusable workflows, releases, self-hosted scale | 14 | 5 |
| 4 | [Ansible for DevOps Engineers](books/04-ansible/README.md) | `books/04-ansible` | Inventories, playbooks, roles and collections, templating, Vault, execution environments, AWX | 14 | 6 |
| 5 | [Terraform for DevOps Engineers](books/05-terraform/README.md) | `books/05-terraform` | HCL, state, modules, testing, policy, HCP Terraform, plan/apply pipelines | 14 | 5 |
| 6 | [Prometheus & Grafana for DevOps Engineers](books/06-prometheus-grafana/README.md) | `books/06-prometheus-grafana` | Data model, PromQL, exporters, alerting, dashboards as code, Thanos/Mimir at scale | 13 | 5 + 3 drills |
| 7 | [Elastic Stack for DevOps Engineers](books/07-elastic-stack/README.md) | `books/07-elastic-stack` | Elasticsearch, Query DSL and ES\|QL, Logstash and Elastic Agent, ILM tiers, Kibana, snapshots | 14 | 5 |
| 8 | [AWS for DevOps Engineers](books/08-aws/README.md) | `books/08-aws` | IAM, EC2, VPC, S3, RDS, EKS, Lambda, CloudWatch, cost control | 12 | 5 |
| 9 | [Azure & GCP for DevOps Engineers](books/09-azure-gcp/README.md) | `books/09-azure-gcp` | Entra ID, Bicep, AKS, Functions; Workload Identity Federation, GKE, Cloud Run; keyless multi-cloud delivery | 16 | 6 |
| 10 | [DevSecOps for DevOps Engineers](books/10-devsecops/README.md) | `books/10-devsecops` | Secrets, supply-chain security, SAST/SCA, image signing and SBOMs, policy as code, runtime security | 16 | 6 + 1 check |

Docker is the only volume with a lab at the end of every chapter — it is the volume where typing
is the point. The later volumes run labs in the chapters where hands-on practice changes the most
(cluster creation, security, observability, operations) and leave the rest as desk-reference
material, which is what their prefaces say.

The Labs column counts numbered labs, 61 in total. Two volumes add short exercises beside them —
three drills in volume 6 and a workflow audit check in volume 10, Chapter 3 — which brings the
series to 65 hands-on exercises. Drills and checks are not numbered as labs and are not counted
as such here.

## How the volumes fit together

Volume 1 packages an application, 2 runs it, 3 builds and ships it automatically, 4 configures
the machines underneath it, and 5 creates that infrastructure in the first place. Volumes 6 and 7
cover the two observability halves — metrics and dashboards, then search and logs. Volume 8 goes
deep on one cloud, 9 covers a second and third along with multi-cloud delivery, and 10 secures
the whole pipeline.

Later volumes reference earlier ones in prose, and each book's preface says what it assumes you
already know. Every volume still stands on its own — you can start at volume 6 — but the
assumptions are lighter if you have read the ones before it.

### Why this order

The sequence is a dependency chain, not a curriculum of equal-weight topics. Each step is placed
so that nothing a volume assumes is taught later:

- **1 → 2.** Kubernetes is not explained from scratch anywhere; the Docker volume's Chapter 11
  hands off to it explicitly.
- **3 after 1 and 2.** CI/CD builds the images from volume 1 and deploys to the cluster of
  volume 2, so the pipeline engine comes after both.
- **4 → 5.** The Terraform volume argues plan-based provisioning against Ansible's model; that
  comparison only reads if Ansible came first.
- **6 after 2.** Prometheus Chapter 13 monitors Kubernetes; the metrics stack has to exist first.
- **8 after 2, 3 and 5.** The AWS volume's EKS chapter assumes the cluster mental model, its
  Chapter 9 deploys with GitHub Actions, and its Chapter 11 puts the estate under Terraform.
- **9 after 8.** Same shape, two more clouds, ending in a three-cloud capstone that compares
  against the AWS volume — so the pair stays together and after it.
- **10 last.** DevSecOps assumes all of it: it hardens Actions pipelines (3), writes Kyverno and
  Falco policy for Kubernetes (2), and scans Terraform (5).

Two orders were considered and rejected. Swapping 4 and 5 contradicts the Terraform volume's own
framing of the Ansible contrast. Moving 6 and 7 after the cloud volumes breaks the reverse
dependency: the cloud books point at the Prometheus volume as "the stack this chapter
deliberately did not duplicate".

## Repository layout

```
.
├── README.md                  # this file — series overview and build instructions
├── LICENSE                    # CC BY 4.0 (the full legal code)
├── VERSIONS.md                # which tool versions each volume was verified against
├── Makefile                   # build every volume: make [all|html|epub|pdf|check|clean]
├── .github/workflows/
│   ├── ci.yml                 # builds and structurally checks all ten volumes
│   └── release.yml            # on a tag push: builds all ten, publishes a GitHub Release
├── tools/
│   ├── check.py               # anchors, links, dividers, labs, metadata, build wiring
│   └── make_covers.py         # regenerates all ten EPUB covers
└── books/
    ├── 01-docker/
    │   ├── manuscript/        # one Markdown file per part, chapter, and appendix
    │   ├── build/             # Pandoc defaults, CSS themes, metadata, cover image
    │   ├── build.sh           # ./build.sh [html|epub|pdf|all]
    │   ├── Makefile           # make [html|epub|pdf|all|clean]
    │   ├── README.md          # what the volume covers, and its build notes
    │   └── output/            # generated artifacts (git-ignored)
    ├── 02-kubernetes/
    ├── …
    └── 10-devsecops/
```

Each volume is a self-contained Pandoc project. The `build/` folder holds its Pandoc defaults,
its own colour theme (each volume has a distinct accent colour on a dark cover), the book
metadata, and the EPUB cover.

## Building

| Tool | Used for | Install |
|------|----------|---------|
| pandoc ≥ 2.19 | every format | `apt install pandoc`, `brew install pandoc`, or <https://pandoc.org> |
| WeasyPrint | PDF | `pip install weasyprint` |
| Python 3 + PyYAML | structural checks (`tools/check.py`) | `pip install pyyaml` |
| Python 3 + Pillow | regenerating EPUB covers (optional) | `pip install pillow` |
| epubcheck | EPUB validation (optional) | `apt install epubcheck` |

Build everything from the repository root:

```bash
make            # all formats, all volumes
make html       # HTML only, all volumes
make epub
make pdf
make clean
```

Or work on a single volume:

```bash
cd books/03-github-actions
./build.sh all          # or: make all
./build.sh pdf          # html | epub | pdf | all
```

Artifacts land in `books/<volume>/output/` as
`<Book_Title_With_Underscores>.{html,epub,pdf}` — for example
`books/01-docker/output/Docker_for_DevOps_Engineers.pdf`.

Repository-wide checks and asset regeneration:

```bash
make check                      # anchors, internal links, part lists, labs, metadata
python3 tools/check.py          # same, with a per-volume line of detail
python3 tools/make_covers.py    # rebuild all ten EPUB covers
python3 tools/make_covers.py 04-ansible   # just one
```

The HTML output is a single self-contained file with embedded CSS. The PDF gets a full-bleed
dark title page, a table of contents with real page numbers, running headers, and chapters that
start on fresh pages. The EPUB is EPUB 3 with the cover embedded.

On Windows, run the build from Git Bash or WSL, because `build.sh` is a POSIX shell script.
WeasyPrint also needs GTK/Pango available, which is the usual cause of a failing PDF build on
Windows.

## Build artifacts are not committed

`output/` is git-ignored in every volume: it is reproducible with `./build.sh all` and would
otherwise go stale with each edit. Generate the formats you need locally, and push a tag
(`git tag v2026.10 && git push origin v2026.10`) when you want a downloadable edition: the
`release` workflow builds all ten volumes from that commit and attaches the HTML, EPUB, and
PDF files to a GitHub Release.

Each release carries 30 individual files (three per volume) plus one archive,
`00-DevOps_Handbook_Series_<tag>.zip`, which holds the same 30 files with one folder per volume —
the single-click option on the releases page.

GitHub orders a release's assets alphabetically and gives no way to change that, so the release
workflow puts the series order into the asset names: `00-` for the archive and `01-` through `10-`
for the volumes. Inside the archive only the folders are numbered
(`01-Docker_for_DevOps_Engineers/Docker_for_DevOps_Engineers.pdf`), which keeps the extracted tree
in series order; local build output keeps the plain names everywhere. For scripts, either the
archive or the loose files come down in one command: `gh release download v2026.10 -D dist`
fetches everything, and `-p '*.epub'` narrows it to one format.

## Editing conventions

- **File order.** The build globs `manuscript/*.md` in alphabetical order, so every file carries
  a two-digit prefix (`03-chapter-1-…`). Inserting a chapter means renumbering the prefixes after
  it, or giving it the next free prefix.
- **One H1 per file.** Each chapter, part divider, and appendix starts with a single `#` heading.
  Heading numbering ("Chapter 4", "4.2") is written directly in the text, so no Pandoc
  `--number-sections` is involved.
- **Stable anchors.** Chapters, parts, labs, and appendices carry explicit IDs — `{#ch7}`,
  `{#part2}`, `{#lab3}`, `{#appA}` — and cross-references link to them as `[Ch. 7](#ch7)`. Keep
  the anchors stable when renaming files so in-book links keep working.
- **Part dividers.** Every Part I / Part II divider lists its chapters as links to those anchors
  (`- [Chapter 7 - Storage and Volumes](#ch7)`), so the list is a second table of contents. A new
  chapter needs an entry in its divider; `tools/check.py` fails if the two disagree.
- **See also.** Every chapter ends with a `**See also:**` line of live links to the chapters a
  reader should visit next. Appendices do not need one.
- **Labs.** A lab is a `::: {.lab}` div whose first line is `### Lab N - Title {#labN}`; the
  numbers run from 1 in every volume and `tools/check.py` fails if they skip or drift from their
  anchor. Short drills and audit checks use their own ids (`{#drill1}`, …) and stay out of the
  lab numbering.
- **Callouts.** Fenced divs: `::: {.note}` for best practice, `::: {.warn}` for watch-outs, and
  `::: {.lab}` for hands-on labs.
- **Metadata.** Title, subtitle, series, volume number, description, and keywords live in each
  volume's `build/metadata.yaml`. It is the only place a book's title should be edited, and
  `tools/check.py` fails if `volume` or `volume-slug` disagrees with the folder name.
- **Theme.** Colours and typography live in `build/style.css` (screen), `build/print.css` (paged
  media/PDF), and `build/epub.css` (e-readers). Text changes never need a CSS change.
- **Covers.** `build/epub-cover.png` is a tracked asset generated by `tools/make_covers.py` —
  one script, one layout grid, ten palettes — so the covers stay consistent and rebuild on Linux,
  macOS, and Windows without editing font paths.

## Accuracy

All volumes were written against October 2026 releases. Each volume states the exact versions it
was verified against in its preface, and [VERSIONS.md](VERSIONS.md) collects them in one table so
a future revision knows what to re-check. Tooling moves quickly: corrections and issue reports are
welcome, ideally scoped to one volume per pull request so the review stays focused.

## License

The series is licensed under [Creative Commons Attribution 4.0 International](LICENSE) (CC BY 4.0).
You may copy, redistribute, remix, and build on the text, commercially or not, as long as you give
appropriate credit. A minimal attribution:

> DevOps Handbook Series, *Docker for DevOps Engineers*, CC BY 4.0,
> https://github.com/<owner>/devops-handbook-series

Code snippets inside the books are meant to be copied into your own projects; CC BY 4.0 already
covers that, and no separate code license is applied.

