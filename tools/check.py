#!/usr/bin/env python3
"""Structural checks for the DevOps Handbook Series.

Run from anywhere:  python3 tools/check.py
Exits non-zero on the first problem found, so CI can use it directly.

What it verifies, per volume:
  * every chapter / appendix H1 carries an explicit {#chN} / {#appX} anchor,
    and numbering is continuous
  * every Part divider carries {#partN} for its position and its entries are
    links that cover all chapters in order
  * every lab heading is `### Lab N - … {#labN}`, numbered from 1 without gaps
  * no explicit anchor is declared twice inside a volume
  * no Markdown file contains Persian/Arabic script
  * every chapter ends with a **See also:** line
  * every internal link (same-file anchor, other-file anchor, relative path)
    resolves, and every external link is well formed
  * fenced code blocks are balanced
  * build/*.yaml exists, parses, and the css / metadata / cover paths it
    references exist
  * build/metadata.yaml parses and its series / volume / slug match the
    directory it lives in
"""
from __future__ import annotations

import pathlib
import re
import sys

try:
    import yaml
except ImportError:  # pragma: no cover - environment problem, not content
    sys.exit("error: PyYAML is required (`pip install pyyaml`)")

ROOT = pathlib.Path(__file__).resolve().parent.parent
BOOKS = ROOT / "books"

HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
EXPLICIT_ID = re.compile(r"\s*\{#([\w:.-]+)\}\s*$")
LINK = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE = re.compile(r"^\s*(```|~~~)")
CHAPTER_TITLE = re.compile(r"^Chapter (\d+) - ")
APPENDIX_TITLE = re.compile(r"^Appendix ([A-Z]) - ")
DIVIDER_TITLE = re.compile(r"^Part\s+[IVX]+\b")
DIVIDER_ITEM = re.compile(r"^- \[?Chapter (\d+)")
LAB_TITLE = re.compile(r"^Lab (\d+)\s*[-–—]\s")
PERSIAN = re.compile(r"[\u0600-\u06FF]")


def auto_identifier(text: str) -> str:
    """Pandoc's automatic heading identifier, close enough to verify links."""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)   # links, images
    text = re.sub(r"[`*_~]+", "", text)                       # emphasis, code marks
    text = re.sub(r"\[[^\]]*\]\{[^}]*\}", "", text)           # footnotes
    first_letter = next((i for i, ch in enumerate(text) if ch.isalpha()), None)
    if first_letter is None:
        return "section"
    text = text[first_letter:]
    text = re.sub(r"[^\w\-.\s]", "", text, flags=re.UNICODE)
    return re.sub(r"\s+", "-", text).lower()


class Book:
    def __init__(self, path: pathlib.Path) -> None:
        self.path = path
        self.name = path.name
        self.slug = path.name.split("-", 1)[1]
        self.index = int(path.name.split("-", 1)[0])
        self.errors: list[str] = []
        self.files = sorted((path / "manuscript").glob("*.md"))
        self.anchors: dict[str, set[str]] = {}
        self.text: dict[pathlib.Path, str] = {}
        self.links: dict[pathlib.Path, list[tuple[int, str, str]]] = {}
        # per-file structural facts
        self.chapters: dict[int, pathlib.Path] = {}
        self.appendices: dict[str, pathlib.Path] = {}
        self.dividers: list[pathlib.Path] = []
        self.preface: pathlib.Path | None = None
        # (path, line, level, heading text, explicit id) in manuscript order
        self.headings: list[tuple[pathlib.Path, int, int, str, str | None]] = []
        # (path, line, lab number, explicit id)
        self.labs: list[tuple[pathlib.Path, int, int, str | None]] = []

    def fail(self, message: str) -> None:
        self.errors.append(message)

    def rel(self, path: pathlib.Path) -> str:
        return str(path.relative_to(ROOT))

    # ------------------------------------------------------------------ parse
    def parse(self) -> None:
        for path in self.files:
            raw = path.read_text(encoding="utf-8")
            self.text[path] = raw
            anchors: set[str] = set()
            links: list[tuple[int, str, str]] = []
            fences = 0
            for number, line in enumerate(raw.split("\n"), start=1):
                if FENCE.match(line):
                    fences += 1
                    continue
                if fences % 2:
                    continue
                heading = HEADING.match(line)
                if heading:
                    body = heading.group(2).strip()
                    explicit = EXPLICIT_ID.search(body)
                    text = EXPLICIT_ID.sub("", body).strip()
                    anchors.add(explicit.group(1) if explicit
                                else auto_identifier(text))
                    self.headings.append((path, number, len(heading.group(1)),
                                          text, explicit.group(1) if explicit else None))
                for target in LINK.finditer(line):
                    links.append((number, target.group(1), target.group(2)))
            if fences % 2:
                self.fail(f"{self.rel(path)}: unbalanced code fences ({fences})")
            self.anchors[path] = anchors
            self.links[path] = links

    # -------------------------------------------------------------- structure
    def classify(self) -> None:
        for path in self.files:
            first = self.text[path].split("\n", 1)[0]
            title = re.sub(r"^#+\s*", "", first)
            chapter = CHAPTER_TITLE.match(title)
            appendix = APPENDIX_TITLE.match(title)
            if chapter:
                number = int(chapter.group(1))
                if number in self.chapters:
                    self.fail(f"{self.rel(path)}: duplicate Chapter {number}")
                self.chapters[number] = path
                if not EXPLICIT_ID.search(title):
                    self.fail(f"{self.rel(path)}: chapter H1 has no {{#chN}} anchor")
                elif not title.rstrip().endswith(f"{{#ch{number}}}"):
                    self.fail(f"{self.rel(path)}: chapter anchor does not match its number")
            elif appendix:
                letter = appendix.group(1)
                self.appendices[letter] = path
                if not title.rstrip().endswith(f"{{#app{letter}}}"):
                    self.fail(f"{self.rel(path)}: appendix H1 needs {{#app{letter}}}")
            elif DIVIDER_TITLE.match(title):
                self.dividers.append(path)
            elif path.name.startswith("01-preface"):
                self.preface = path
        for path, line_no, _level, text, explicit in self.headings:
            lab = LAB_TITLE.match(text)
            if lab:
                self.labs.append((path, line_no, int(lab.group(1)), explicit))

    def check_chapter_order(self) -> None:
        numbers = sorted(self.chapters)
        if numbers != list(range(1, len(numbers) + 1)):
            self.fail(f"chapter numbers are not continuous: {numbers}")
        letters = sorted(self.appendices)
        expected = [chr(ord("A") + i) for i in range(len(letters))]
        if letters != expected:
            self.fail(f"appendix letters are not continuous: {letters}")

    def check_dividers(self) -> None:
        seen: list[int] = []
        if not self.dividers:
            self.fail("no Part divider found in manuscript/")
        for position, divider in enumerate(self.dividers, start=1):
            title = self.text[divider].split("\n", 1)[0].rstrip()
            if not title.endswith(f"{{#part{position}}}"):
                self.fail(f"{self.rel(divider)}: part divider needs {{#part{position}}}")
            entries = [line for line in self.text[divider].split("\n")
                       if line.startswith("- ")]
            if not entries:
                self.fail(f"{self.rel(divider)}: no chapter list")
            for line in entries:
                if not line.startswith("- ["):
                    self.fail(f"{self.rel(divider)}: entry is not a link: {line[:60]}")
                    continue
                match = DIVIDER_ITEM.match(line)
                if match:
                    seen.append(int(match.group(1)))
        if seen != sorted(self.chapters):
            self.fail(f"Part dividers cover {seen}, manuscript has {sorted(self.chapters)}")

    def check_labs(self) -> None:
        numbers = [number for _path, _line, number, _id in self.labs]
        if numbers != list(range(1, len(numbers) + 1)):
            self.fail(f"lab numbers are not continuous from 1: {numbers}")
        for path, line_no, number, explicit in self.labs:
            if explicit != f"lab{number}":
                self.fail(f"{self.rel(path)}:{line_no}: Lab {number} needs {{#lab{number}}}")

    def check_anchor_ids(self) -> None:
        seen: dict[str, pathlib.Path] = {}
        for path, line_no, _level, _text, explicit in self.headings:
            if not explicit:
                continue
            if explicit in seen:
                self.fail(f"{self.rel(path)}:{line_no}: duplicate anchor {{#{explicit}}} "
                          f"(first declared in {self.rel(seen[explicit])})")
            else:
                seen[explicit] = path

    def check_see_also(self) -> None:
        for number, path in sorted(self.chapters.items()):
            if "**See also:**" not in self.text[path]:
                self.fail(f"{self.rel(path)}: chapter {number} has no **See also:** line")

    def check_links(self) -> None:
        all_anchors = set().union(*self.anchors.values()) if self.anchors else set()
        for path, links in self.links.items():
            for line_no, label, target in links:
                where = f"{self.rel(path)}:{line_no}"
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                if target.startswith("#"):
                    if target[1:] not in all_anchors:
                        self.fail(f"{where}: broken anchor {target}")
                    continue
                file_part, _, anchor = target.partition("#")
                resolved = (path.parent / file_part).resolve()
                if not resolved.exists():
                    self.fail(f"{where}: missing file {target}")
                elif anchor:
                    target_anchors = self.anchors.get(resolved)
                    if target_anchors is None:
                        self.fail(f"{where}: anchor {anchor} in a non-manuscript file")
                    elif anchor not in target_anchors:
                        self.fail(f"{where}: broken anchor {target}")

    # ------------------------------------------------------------------ build
    def check_build(self) -> None:
        for required in ("build.sh", "Makefile", "README.md", "build/metadata.yaml"):
            if not (self.path / required).is_file():
                self.fail(f"missing {required}")
        for yaml_file in sorted((self.path / "build").glob("*.yaml")):
            try:
                config = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            except yaml.YAMLError as exc:
                self.fail(f"{self.rel(yaml_file)}: invalid YAML ({exc.__class__.__name__})")
                continue
            if not isinstance(config, dict):
                continue
            for key in ("css", "metadata-file", "cover-image"):
                value = config.get(key)
                if isinstance(value, str) and not (self.path / value).is_file():
                    self.fail(f"{self.rel(yaml_file)}: {key} path missing: {value}")

        meta_path = self.path / "build" / "metadata.yaml"
        if not meta_path.is_file():
            return
        try:
            meta = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            return  # already reported
        if not isinstance(meta, dict):
            self.fail("build/metadata.yaml is not a mapping")
            return
        for key in ("title", "subtitle", "author", "series", "volume", "date", "lang"):
            if not meta.get(key):
                self.fail(f"build/metadata.yaml: missing {key}")
        if str(meta.get("volume")) != str(self.index):
            self.fail(f"build/metadata.yaml: volume {meta.get('volume')} != directory {self.index}")
        if meta.get("volume-slug") != self.slug:
            self.fail(f"build/metadata.yaml: volume-slug {meta.get('volume-slug')} != {self.slug}")

    # ------------------------------------------------------------------- main
    def run(self) -> list[str]:
        self.parse()
        self.classify()
        self.check_chapter_order()
        self.check_dividers()
        self.check_labs()
        self.check_anchor_ids()
        self.check_see_also()
        self.check_links()
        self.check_build()
        return self.errors


def check_language(books: list[Book]) -> list[str]:
    """The manuscripts and the series READMEs are written in English only."""
    paths = [ROOT / "README.md", ROOT / "VERSIONS.md"]
    paths += [book.path / "README.md" for book in books]
    paths += [path for book in books for path in book.files]
    errors: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            if PERSIAN.search(line):
                errors.append(f"{path.relative_to(ROOT)}:{number}: Persian/Arabic script "
                              "is not allowed in the English sources")
                break
    return errors


def check_series_readme(books: list[Book]) -> list[str]:
    readme = ROOT / "README.md"
    if not readme.is_file():
        return ["README.md is missing at the repository root"]
    text = readme.read_text(encoding="utf-8")
    return [f"README.md does not mention {book.name}"
            for book in books if book.name not in text]


def main() -> int:
    books = [Book(path) for path in sorted(p for p in BOOKS.iterdir() if p.is_dir())]
    total_errors = 0
    for book in books:
        errors = book.run()
        total_errors += len(errors)
        status = "FAIL" if errors else "ok"
        print(f"{status:4}  {book.name:22} chapters={len(book.chapters):2} "
              f"appendices={len(book.appendices)} dividers={len(book.dividers)} "
              f"labs={len(book.labs):2} "
              f"links={sum(len(v) for v in book.links.values()):3}")
        for error in errors:
            print(f"      - {error}")

    for error in check_series_readme(books):
        total_errors += 1
        print(f"FAIL  {error}")

    for error in check_language(books):
        total_errors += 1
        print(f"FAIL  {error}")

    print(f"\n{len(books)} volumes, {total_errors} problem(s)")
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
