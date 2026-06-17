# Legal and Safety Guidelines

This project is a local-first software pipeline. It does not provide legal
advice, and the maintainers cannot determine whether a specific source, site,
voice sample, output, or jurisdiction is safe for your use case. When in doubt,
ask the rights holder or get qualified legal advice before processing or
publishing content.

## Allowed Use

Use the pipeline only when you have the rights and authorization needed to:

- access the source material;
- copy it into local working files;
- transform, translate, summarize, or reformat it;
- synthesize speech from it;
- store the generated artifacts; and
- share or publish the resulting audio, if you plan to distribute it.

Good default examples include your own writing, public-domain material,
open-licensed material whose license allows the intended use, internal material
your organization authorizes you to process, and private study material that you
are allowed to download and transform for personal use.

## Prohibited Use

Do not use this project to:

- bypass paywalls, login protections, DRM, rate limits, bot controls, or access
  restrictions;
- violate a website's terms, robots guidance, or acceptable-use rules;
- redistribute copyrighted source pages, translations, or generated audio
  without permission;
- process private, confidential, regulated, or personal data without the
  required authorization;
- use someone else's voice, likeness, name, or identity without consent;
- impersonate a person, imply endorsement, or hide that audio is synthetic;
- commit cookies, bearer tokens, API keys, storage-state files, voice samples,
  scraped pages, generated translations, or generated audio to git.

## Source Site Hygiene

For web sources:

- prefer explicit URL lists over broad crawls;
- keep request rates conservative with `request_delay_seconds`;
- use `content_selector` and `remove_selectors` to avoid collecting unrelated
  page content;
- preserve enough source metadata to audit where outputs came from;
- stop immediately if a site blocks, rate limits, or asks automated clients not
  to access the content;
- keep generated artifacts private unless you have distribution rights.

Authenticated access should only use your own authorized account or an account
you are explicitly permitted to automate. A Playwright `storage_state` file can
contain active cookies and session credentials, so treat it like a secret.

## Voice and Synthetic Audio

Only use voice samples that you own or have explicit permission to use for
synthetic speech. If you distribute generated audio, label it clearly when
required or appropriate, and do not imply that a real person spoke or endorsed
the content unless that is true and authorized.

The pipeline includes optional leakage checks for voice reference material, but
those checks are defensive aids. They do not prove consent, identity rights, or
compliance.

## Repository Hygiene

The project `.gitignore` excludes common sensitive and generated artifacts, but
maintainers and contributors are still responsible for checking their changes.
Before committing or publishing:

- run `git status --short` and inspect new files;
- search for credentials, cookies, tokens, private URLs, and personal data;
- keep examples generic and based on `example.com` or local sample files;
- do not add generated audio or translated third-party content as fixtures;
- rotate any credential that was ever committed, even if it was later removed.

## Maintainer Policy

Maintainers may close issues, pull requests, examples, or discussions that ask
for help bypassing access controls, copying restricted content, misusing a
person's voice, or handling secrets unsafely. Security issues should be reported
privately using the repository security policy.
