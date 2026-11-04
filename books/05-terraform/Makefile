# Makefile — build HTML / EPUB / PDF from the Markdown manuscript.
BOOK  := Terraform_for_DevOps_Engineers
OUT   := output
SRC   := $(wildcard manuscript/*.md)
PANDOC := pandoc

.PHONY: all html epub pdf clean

all: html epub pdf

html: $(OUT)/$(BOOK).html
epub: $(OUT)/$(BOOK).epub
pdf:  $(OUT)/$(BOOK).pdf

$(OUT)/$(BOOK).html: $(SRC) build/html.yaml build/style.css build/metadata.yaml | $(OUT)
	$(PANDOC) $(SRC) -d build/html.yaml -o $@

$(OUT)/$(BOOK).epub: $(SRC) build/epub.yaml build/epub.css build/metadata.yaml build/epub-cover.png | $(OUT)
	$(PANDOC) $(SRC) -d build/epub.yaml -o $@

$(OUT)/$(BOOK).pdf: $(SRC) build/pdf.yaml build/style.css build/print.css build/metadata.yaml | $(OUT)
	$(PANDOC) $(SRC) -d build/pdf.yaml -o build/.print.html
	weasyprint -q build/.print.html $@
	rm -f build/.print.html

$(OUT):
	mkdir -p $(OUT)

clean:
	rm -f $(OUT)/$(BOOK).html $(OUT)/$(BOOK).epub $(OUT)/$(BOOK).pdf build/.print.html
