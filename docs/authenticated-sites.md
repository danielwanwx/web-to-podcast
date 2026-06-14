# Authenticated Sites

Some learning portals render content only after login. Use the Playwright
renderer with a storage-state JSON file for these sources.

1. Install browser support.

   ```bash
   scripts/bootstrap.sh --browser
   ```

2. Create a storage-state file with your own browser session. One simple way is
   to use Playwright's codegen tool:

   ```bash
   mkdir -p auth
   .venv/bin/python -m playwright codegen https://example.com \
     --save-storage auth/storage-state.json
   ```

   Log in in the opened browser window, then close it after the state is saved.

3. Point your config to the state file.

   ```yaml
   source:
     renderer: playwright
     storage_state: auth/storage-state.json
     content_selector: article
     title_selector: h1
     request_delay_seconds: 0.5
   ```

4. Check before running a long job.

   ```bash
   web-to-podcast doctor --config my-resource.yaml --strict
   ```

Relative `storage_state` paths are resolved from the config file's directory.

Do not commit `auth/` or storage-state files. They can contain login cookies.
