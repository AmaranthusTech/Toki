PYTHON ?= python3
VENV_DIR ?= .venv
VENV_PYTHON := $(VENV_DIR)/bin/python
OFFLINE_VERIFY ?= 1

.PHONY: venv test lint fmt bench
.PHONY: setup setup-online setup-offline

venv:
	$(PYTHON) -m venv $(VENV_DIR)
	$(VENV_PYTHON) -m pip install -U pip
	$(VENV_PYTHON) -m pip install -e ".[dev]"

setup: setup-online

setup-online:
	$(PYTHON) -m venv $(VENV_DIR)
	$(VENV_PYTHON) -m pip install -U pip
	$(VENV_PYTHON) -m pip install -e ".[dev,compare,api]"
	PYTHON=$(VENV_PYTHON) ./scripts/apply_patches.sh

setup-offline:
	@test -x $(VENV_PYTHON) || (echo "ERROR: $(VENV_PYTHON) not found. Run make setup-online once in a networked env." && exit 1)
	PYTHON=$(VENV_PYTHON) ./scripts/apply_patches.sh
	$(VENV_PYTHON) -m shintoki --format json doctor --ephemeris-path data/de440s.bsp
	@if [ "$(OFFLINE_VERIFY)" = "0" ]; then \
		echo "setup-offline: OFFLINE_VERIFY=0 -> skip pytest and repro"; \
	else \
		$(VENV_PYTHON) -m pytest -q; \
		$(VENV_PYTHON) scripts/repro_jcal_2033.py; \
	fi

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .

fmt:
	$(PYTHON) -m black .

bench:
	$(PYTHON) -m shintoki bench-smoke
