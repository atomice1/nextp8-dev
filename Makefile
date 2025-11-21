all: dep_check bsp sqlux femto8 loader sdcard

.PHONY: dep_check
dep_check:
	if ! which m68k-elf-gcc >/dev/null 2>&1; then \
		echo >&2 "Ensure m68k-elf-gcc is in your PATH."; \
		exit 1; \
	fi

.PHONY: bsp
bsp:
	$(MAKE) -C nextp8-bsp clean all

.PHONY: sqlux
sqlux:
	$(MAKE) -C sQLux-nextp8

.PHONY: femto8
femto8:
	$(MAKE) -C femto8-nextp8 NEXTP8_BSP=$(CURDIR)/nextp8-bsp PLATFORM=nextp8 clean all

.PHONY: loader
loader:
	$(MAKE) -C nextp8-loader NEXTP8_BSP=$(CURDIR)/nextp8-bsp clean all

.PHONY: sdcard
sdcard:
	cd sQLux-nextp8 && ../scripts/make-sdcard.sh
