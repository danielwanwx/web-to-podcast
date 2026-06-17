# Open Source Release Checklist

Use this checklist before making the repository public or publishing a release.

## Content and Credentials

- No real cookies, Playwright storage-state files, bearer tokens, API keys,
  account identifiers, or private URLs are committed.
- No voice samples, generated WAV/M4A/MP3 files, scraped pages, translated
  third-party text, or private notes are committed.
- Examples use `example.com`, local sample files, or content that is clearly
  safe to redistribute.
- The git history has been reviewed for accidental secrets. Rotate any exposed
  secret; deleting it from the latest commit is not enough.

## Project Metadata

- `LICENSE` is present and matches package metadata.
- `README.md` states the project status, intended use, limitations, and legal
  boundaries.
- `docs/legal-and-safety.md` is linked from the README.
- `SECURITY.md` describes how to report vulnerabilities or accidental secret
  exposure.
- `CONTRIBUTING.md` tells contributors not to include restricted content,
  generated audio, credentials, cookies, or unauthorized voice samples.

## GitHub Settings

- Enable secret scanning and push protection for the repository when available.
- Enable Dependabot alerts and version updates if you want automated dependency
  maintenance.
- Require CI to pass before merging external pull requests.
- Review pull requests for legal and safety issues, not only for code quality.

## Release Notes

- State that generated outputs are the user's responsibility.
- Do not include third-party content, translations, or generated audio unless
  you have distribution rights.
- Keep examples generic and reproducible without private accounts.
