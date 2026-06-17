# Security Policy

## Supported Versions

This project is currently alpha software. Security fixes target the default
branch until versioned releases are introduced.

## Reporting a Vulnerability

Please do not open a public issue for vulnerabilities, leaked credentials, or
private data exposure. Report security issues privately through GitHub Security
Advisories if available for this repository, or contact the maintainer through
the repository owner profile.

Include:

- affected version or commit;
- operating system and Python version;
- a minimal reproduction that does not include real credentials, cookies,
  storage-state files, voice samples, private source content, or generated
  audio;
- impact and any known workaround.

## Secrets and Generated Content

If you accidentally commit a secret, cookie, storage-state file, voice sample,
scraped page, generated translation, or generated audio file:

1. Remove it from the repository.
2. Rotate or revoke any exposed credential immediately.
3. Treat generated or third-party content exposure as a data incident and handle
   it according to the applicable owner, organization, or legal requirements.

The `.gitignore` blocks common generated and sensitive files, but it is not a
complete data-loss-prevention system.
