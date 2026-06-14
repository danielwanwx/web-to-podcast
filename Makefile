PYTHON ?= python3
VENV ?= .venv
CLI := $(VENV)/bin/web-to-podcast

.PHONY: bootstrap bootstrap-browser test doctor smoke clean publish

bootstrap:
	PYTHON=$(PYTHON) WEB_TO_PODCAST_VENV=$(VENV) scripts/bootstrap.sh

bootstrap-browser:
	PYTHON=$(PYTHON) WEB_TO_PODCAST_VENV=$(VENV) scripts/bootstrap.sh --browser

test:
	PYTHONPATH=src $(PYTHON) -m pytest -q

doctor:
	PYTHONPATH=src $(PYTHON) -m web_to_podcast.cli doctor

smoke:
	rm -rf output/local-smoke
	PYTHONPATH=src $(PYTHON) -m web_to_podcast.cli run --config examples/local_markdown.json --force
	PYTHONPATH=src $(PYTHON) -m web_to_podcast.cli status --output-dir output/local-smoke

clean:
	rm -rf .venv output .pytest_cache .ruff_cache build dist *.egg-info src/*.egg-info
	find src tests -type d -name __pycache__ -prune -exec rm -rf {} +

publish:
	scripts/publish_github.sh $(REMOTE)
