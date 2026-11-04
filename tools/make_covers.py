#!/usr/bin/env python3
"""Generate the EPUB cover for every volume of the series.

One script, one grid, ten covers. Each volume only supplies its title,
subtitle, capability lines and palette; the layout and the font lookup are
shared, so the covers stay consistent and can be rebuilt on Linux, macOS or
Windows without editing paths.

Usage:
    python3 tools/make_covers.py            # all volumes
    python3 tools/make_covers.py 04-ansible # just one

Requires Pillow (`pip install pillow`) and a system sans/serif font family
(DejaVu, Liberation, Carlito, Arial or Segoe UI - first match wins).
"""
from __future__ import annotations

import pathlib
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
W, H = 1600, 2560
MARGIN = 120

# slug: (title lines, subtitle lines, meta lines, palette)
# palette order: background, accent, title, subtitle, meta, footer
BOOKS: dict[str, tuple[list[str], list[str], list[str], tuple[str, ...]]] = {
    "01-docker": (
        ["Docker for", "DevOps Engineers"],
        ["A Practical Handbook from", "First Principles to Production"],
        ["Docker Engine v29 \u00b7 BuildKit \u00b7 Compose v2", "First Edition \u00b7 October 2026"],
        ("#0D1B2A", "#2496ED", "#F2F8FD", "#D3E5F5", "#9FC0DC", "#86A9C8"),
    ),
    "02-kubernetes": (
        ["Kubernetes for", "DevOps Engineers"],
        ["A Practical Handbook from", "First Principles to Advanced Operations"],
        ["Kubernetes v1.37 \u00b7 kind \u00b7 kubeadm \u00b7 Helm 4", "First Edition \u00b7 October 2026"],
        ("#0E2A47", "#58A6E8", "#EAF3FC", "#C2D6E8", "#A8BDD2", "#7E93A8"),
    ),
    "03-github-actions": (
        ["GitHub Actions", "for DevOps Engineers"],
        ["A Practical Handbook from", "First Commit to Production Automation"],
        ["Node 24 \u00b7 OIDC \u00b7 Reusable Workflows \u00b7 ARC 0.15", "First Edition \u00b7 October 2026"],
        ("#0D1117", "#2F81F7", "#EAF2FB", "#C6D8EC", "#A9BDD3", "#7C8FA5"),
    ),
    "04-ansible": (
        ["Ansible for", "DevOps Engineers"],
        ["A Practical Handbook from First Playbook", "to Fleet-Scale Automation"],
        [
            "ansible-core 2.21 \u00b7 Community Package 14",
            "Execution Environments \u00b7 AWX \u00b7 Event-Driven Ansible",
            "First Edition \u00b7 October 2026",
        ],
        ("#14100F", "#FF5A47", "#F7EDE9", "#E8CFC8", "#C9AFA8", "#9A8079"),
    ),
    "05-terraform": (
        ["Terraform for", "DevOps Engineers"],
        ["A Practical Handbook from First Plan", "to Production-Scale Infrastructure as Code"],
        [
            "Terraform 1.17 \u00b7 HCP Terraform \u00b7 OpenTofu 1.13",
            "HCL \u00b7 State \u00b7 Modules \u00b7 Testing \u00b7 CI/CD",
            "First Edition \u00b7 October 2026",
        ],
        ("#151021", "#9E7CF0", "#F2EDFA", "#D8CBF2", "#BCB0D9", "#968CAF"),
    ),
    "06-prometheus-grafana": (
        ["Prometheus & Grafana", "for DevOps Engineers"],
        ["Metrics, Dashboards, and Alerting", "for Production Systems"],
        [
            "Prometheus 3.15 \u00b7 Alertmanager 0.34 \u00b7 Grafana 13",
            "PromQL \u00b7 Service Discovery \u00b7 Unified Alerting",
            "First Edition \u00b7 October 2026",
        ],
        ("#1B1611", "#E6522C", "#F9F0E7", "#EFD9C8", "#D3B49E", "#A68872"),
    ),
    "07-elastic-stack": (
        ["Elastic Stack", "for DevOps Engineers"],
        ["Search, Logs, and Observability", "with Elasticsearch, Kibana, and Elastic Agent"],
        [
            "Elasticsearch 9.5 \u00b7 Kibana 9.5 \u00b7 Logstash 9.5",
            "Query DSL \u00b7 ES|QL \u00b7 ILM \u00b7 Fleet \u00b7 Snapshots",
            "First Edition \u00b7 October 2026",
        ],
        ("#0F2531", "#00BFB3", "#ECF7F5", "#BFE0DC", "#93C4BE", "#6E9E99"),
    ),
    "08-aws": (
        ["AWS", "for DevOps Engineers"],
        ["Compute, Networking, and Automation", "on Amazon Web Services"],
        [
            "EC2 \u00b7 VPC \u00b7 S3 \u00b7 RDS \u00b7 EKS \u00b7 Lambda",
            "IAM \u00b7 CloudWatch \u00b7 Terraform \u00b7 GitHub Actions",
            "First Edition \u00b7 October 2026",
        ],
        ("#232F3E", "#FF9900", "#FFF8EF", "#D6E0EB", "#A6B7C9", "#899BB0"),
    ),
    "09-azure-gcp": (
        ["Azure & GCP", "for DevOps Engineers"],
        ["A Practical Handbook for", "Multi-Cloud Delivery"],
        [
            "Bicep \u00b7 AKS \u00b7 Functions \u00b7 VNet \u00b7 Blob",
            "gcloud \u00b7 GKE \u00b7 Cloud Run \u00b7 Compute Engine",
            "First Edition \u00b7 October 2026",
        ],
        ("#102A43", "#4DA3E8", "#F2F8FD", "#D6E0EB", "#A6B7C9", "#8FA6BC"),
    ),
    "10-devsecops": (
        ["DevSecOps", "for DevOps Engineers"],
        ["A Practical Handbook for", "Securing the Pipeline"],
        [
            "Vault \u00b7 Gitleaks \u00b7 Semgrep \u00b7 Trivy",
            "Cosign \u00b7 SBOM \u00b7 Kyverno \u00b7 Falco \u00b7 ZAP",
            "First Edition \u00b7 October 2026",
        ],
        ("#12261F", "#3ECF8E", "#F0FAF5", "#D4E4DC", "#A0BAAD", "#8BA598"),
    ),
}

FONT_DIRS = [
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    "/Library/Fonts",
    "/System/Library/Fonts",
    pathlib.Path.home() / ".fonts" if pathlib.Path.home().joinpath(".fonts").exists() else None,
    pathlib.Path("C:/Windows/Fonts"),
]

# role -> candidate file names, best match first
FONT_CANDIDATES = {
    "bold": ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "Carlito-Bold.ttf",
             "Arial Bold.ttf", "arialbd.ttf", "segoeuib.ttf", "Helvetica.ttc"],
    "serif": ["DejaVuSerif.ttf", "LiberationSerif-Regular.ttf", "Carlito-Regular.ttf",
              "times.ttf", "georgia.ttf", "Georgia.ttf"],
    "italic": ["Carlito-Italic.ttf", "DejaVuSans-Oblique.ttf", "LiberationSans-Italic.ttf",
               "Arial Italic.ttf", "ariali.ttf", "segoeuii.ttf", "Georgia Italic.ttf"],
    "sans": ["DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Carlito-Regular.ttf",
             "arial.ttf", "segoeui.ttf"],
}


def font_index() -> dict[str, pathlib.Path]:
    index: dict[str, pathlib.Path] = {}
    for root in FONT_DIRS:
        if not root or not pathlib.Path(root).is_dir():
            continue
        for path in pathlib.Path(root).rglob("*"):
            if path.suffix.lower() in {".ttf", ".ttc", ".otf"}:
                index.setdefault(path.name.lower(), path)
    return index


INDEX = font_index()


def font(role: str, size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES[role]:
        path = INDEX.get(candidate.lower())
        if path:
            return ImageFont.truetype(str(path), size)
    raise SystemExit(
        f"error: no usable font for {role!r}. Tried: {', '.join(FONT_CANDIDATES[role])}. "
        "Install DejaVu or Liberation fonts (e.g. `apt install fonts-dejavu`)."
    )


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def build(slug: str) -> pathlib.Path:
    title_lines, subtitle_lines, meta_lines, palette = BOOKS[slug]
    bg, accent, title_col, sub_col, meta_col, foot_col = (hex_rgb(c) for c in palette)

    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)
    usable = W - 2 * MARGIN

    def center(text: str, y: int, face: ImageFont.FreeTypeFont, fill, tracking: bool = False) -> int:
        if tracking:
            text = (" " * 2).join(text)
        width = draw.textlength(text, font=face)
        if width > usable:
            raise SystemExit(f"error: {slug}: line too wide ({int(width)}px): {text!r}")
        draw.text(((W - width) / 2, y), text, font=face, fill=fill)
        return y

    def fit_size(lines: list[str], start: int, floor: int = 74) -> int:
        size = start
        while size > floor:
            face = font("bold", size)
            if all(draw.textlength(line, font=face) <= usable for line in lines):
                return size
            size -= 2
        return floor

    draw.rectangle([MARGIN, 150, W - MARGIN, 162], fill=accent)
    center("TECHNICAL HANDBOOK", 420, font("sans", 44), accent, tracking=True)

    size = fit_size(title_lines, start=170)
    title_face = font("bold", size)
    y = 600
    for line in title_lines:
        center(line, y, title_face, title_col)
        y += int(size * 1.36)

    sub_face = font("italic", 56)
    y += 60
    for line in subtitle_lines:
        center(line, y, sub_face, sub_col)
        y += 84

    meta_face = font("serif", 50)
    y = max(y + 90, 1520)
    for line in meta_lines:
        center(line, y, meta_face, meta_col)
        y += 100

    center("Compiled for DevOps Engineering Teams", 2180, font("sans", 42), foot_col)
    draw.rectangle([MARGIN, H - 150, W - MARGIN, H - 138], fill=accent)

    out = ROOT / "books" / slug / "build" / "epub-cover.png"
    img.save(out, optimize=True)
    return out


def main(argv: list[str]) -> int:
    wanted = argv or sorted(BOOKS)
    unknown = [slug for slug in wanted if slug not in BOOKS]
    if unknown:
        print(f"unknown volume(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"known: {', '.join(sorted(BOOKS))}", file=sys.stderr)
        return 2
    for slug in wanted:
        print(f"cover  {build(slug).relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
