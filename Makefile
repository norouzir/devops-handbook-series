# Root Makefile — build every volume in the series.
#
#   make            all formats, all volumes
#   make html       HTML only
#   make epub       EPUB only
#   make pdf        PDF only
#   make clean      remove generated artifacts
#   make check      structural checks (anchors, links, dividers, metadata)
#   make covers     regenerate the ten EPUB covers
#
# Each volume is a self-contained Pandoc project with its own Makefile; this one
# only loops over books/* so a single command can build the whole series.

BOOKS := $(sort $(wildcard books/*))

.PHONY: all html epub pdf clean list check covers

all html epub pdf:
	@status=0; \
	for book in $(BOOKS); do \
	  echo "==> $$book"; \
	  $(MAKE) -C $$book $@ || status=1; \
	done; \
	exit $$status

clean:
	@for book in $(BOOKS); do \
	  $(MAKE) -C $$book clean; \
	done

check:
	@python3 tools/check.py

covers:
	@python3 tools/make_covers.py

list:
	@for book in $(BOOKS); do \
	  printf '%s\t%s\n' "$$(basename $$book)" "$$(sed -n 's/^title: //p' $$book/build/metadata.yaml)"; \
	done
