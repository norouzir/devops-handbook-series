#!/usr/bin/env bash
# build.sh — build HTML / PDF / EPUB from the Markdown manuscript.
#
# Usage:  ./build.sh [html|pdf|epub|all]     (default: all)
#
# Requirements:
#   - pandoc >= 2.19 (defaults files, embed-resources)
#   - WeasyPrint for the PDF build (https://weasyprint.org/)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

OUT="$ROOT/output"
mkdir -p "$OUT"
BOOK="DevSecOps_for_DevOps_Engineers"

MANUSCRIPT=(manuscript/*.md)
if [ ! -e "${MANUSCRIPT[0]}" ]; then
  echo "error: no markdown files found in manuscript/" >&2
  exit 1
fi

build_html() {
  echo "==> HTML"
  pandoc "${MANUSCRIPT[@]}" -d build/html.yaml -o "$OUT/$BOOK.html"
  echo "    $OUT/$BOOK.html"
}

build_epub() {
  echo "==> EPUB"
  pandoc "${MANUSCRIPT[@]}" -d build/epub.yaml -o "$OUT/$BOOK.epub"
  echo "    $OUT/$BOOK.epub"
}

build_pdf() {
  echo "==> PDF"
  if ! command -v weasyprint >/dev/null 2>&1; then
    echo "error: weasyprint not found. Install it with:  pip install weasyprint" >&2
    exit 1
  fi
  local tmp="$ROOT/build/.print.html"
  pandoc "${MANUSCRIPT[@]}" -d build/pdf.yaml -o "$tmp"
  weasyprint -q "$tmp" "$OUT/$BOOK.pdf"
  rm -f "$tmp"
  echo "    $OUT/$BOOK.pdf"
}

case "${1:-all}" in
  html) build_html ;;
  pdf)  build_pdf ;;
  epub) build_epub ;;
  all)  build_html; build_epub; build_pdf ;;
  *)    echo "usage: $0 [html|pdf|epub|all]" >&2; exit 2 ;;
esac

echo "done."
