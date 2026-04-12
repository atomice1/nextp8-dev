all: venv dep_check bsp sqlux femto8 loader release sdcard

.PHONY: dep_check
dep_check: venv
	if ! which m68k-elf-gcc >/dev/null 2>&1; then \
		echo >&2 "Ensure m68k-elf-gcc is in your PATH."; \
		exit 1; \
	fi

.PHONY: bsp
bsp: dep_check
	$(MAKE) -C nextp8-bsp clean all

.PHONY: sqlux
sqlux:
	$(MAKE) -C sQLux-nextp8 NEXTP8_BSP=$(CURDIR)/nextp8-bsp

.PHONY: femto8
femto8: dep_check bsp
	$(MAKE) -C femto8-nextp8 NEXTP8_BSP=$(CURDIR)/nextp8-bsp PLATFORM=nextp8 clean all

.PHONY: loader
loader: dep_check bsp
	$(MAKE) -C nextp8-loader NEXTP8_BSP=$(CURDIR)/nextp8-bsp clean all

.PHONY: release
release: femto8 loader
	./scripts/make-release.sh nextp8_"$$(python3 scripts/gen-version.py)".zip

.PHONY: sdcard
sdcard: venv release
	. venv/bin/activate &&  ./scripts/make-sdcard.py --output sQLux-nextp8/sdcard.img --release-zip nextp8_"$$(python3 scripts/gen-version.py)".zip --cart-dir carts --cart-dir femto8-nextp8/carts --cart-dir femto8-nextp8/tests

venv:
	python3 -m venv venv
	python3 -m pip install setuptools==81
	python3 -m pip install -r scripts/requirements.txt
