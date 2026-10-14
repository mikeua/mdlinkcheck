# Changelog

## 0.2.0 (2026-10-14)

- Auto-detect Docusaurus, Vocs, VitePress and MkDocs sites, so route-style links (`/guide/intro`, `./intro`) resolve
  without `--site-root`. Disable with `--no-detect-sites`.
- Relative links on a site's `index` pages resolve from the parent folder, matching how the page is served.

## 0.1.0 (2026-10-13)

First release.

- Checks relative file links, `#anchors` (GitHub slug rules), and file-name case.
- `text`, `github` and `json` output; GitHub Action and pre-commit hook.
- `--site-root` for docs sites that use extensionless or `/route` links.
