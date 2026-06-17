# Contributing

Thanks for improving web-to-podcast. This is a local-first pipeline for lawful
content processing; contributions should preserve that boundary.

## Ground Rules

- Do not commit credentials, cookies, Playwright storage-state files, API keys,
  private URLs, account identifiers, or personal data.
- Do not commit voice samples, generated audio, scraped pages, translated
  third-party text, or copyrighted fixtures unless they are clearly licensed for
  redistribution in this repository.
- Keep examples generic. Prefer `example.com`, local sample files, or
  open-licensed/public-domain material with attribution.
- Do not add features or documentation whose purpose is to bypass paywalls,
  access controls, site restrictions, bot controls, or rate limits.
- Do not add voice features that encourage impersonation or use of a person's
  voice without consent.

## Development

Set up a development environment:

```bash
scripts/bootstrap.sh
source .venv/bin/activate
```

Run the smoke tests:

```bash
PYTHONPATH=src python -m pytest
```

For optional integrations, install only what you need:

```bash
scripts/bootstrap.sh --browser
scripts/bootstrap.sh --extract
scripts/bootstrap.sh --tts
scripts/bootstrap.sh --asr
```

## Pull Requests

Before opening a pull request:

- run tests relevant to your change;
- inspect `git status --short` for accidental generated files;
- confirm examples and docs do not include restricted content;
- update README/docs when behavior or setup changes;
- describe any new network, scraping, authentication, or audio-generation
  behavior clearly.

Maintainers may decline changes that create legal, privacy, safety, or security
risk even if the code works.
