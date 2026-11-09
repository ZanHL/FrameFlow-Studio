# Third-party code and assets

## MoneyPrinterTurbo

- Upstream: https://github.com/harry0703/MoneyPrinterTurbo
- Snapshot: local 1.3.10 source checkout based on commit `8b0206be2c7977e3bc3cf25ff99a2adc3c9c65f9`.
- License: MIT, retained verbatim in `vendor/moneyprinterturbo/LICENSE`.
- Scope: media engine `app/`, default config template, bundled default fonts and music.
- Integrity: imported source/resource SHA-256 hashes in `vendor/moneyprinterturbo/MANIFEST.json`.
- Local adapters: `studio/engine/`, `studio/integrations/`. These are maintained by this application.

No upstream user configuration, API credentials, generated files, virtual environment,
WebUI, or git metadata has been imported. Fonts and music retain their original upstream
attribution and applicable terms; the MIT notice identifies the upstream code license.
Python dependencies and their versions are recorded in `pyproject.toml` and `uv.lock`.
