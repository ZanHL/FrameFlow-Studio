# Bundled MoneyPrinterTurbo engine

Source snapshot: local MoneyPrinterTurbo 1.3.10 checkout, based on commit
8b0206be2c7977e3bc3cf25ff99a2adc3c9c65f9. MIT (see LICENSE).
MANIFEST.json records the actual imported files, including local source changes.
The app package is retained together because media services eagerly import one another.
No upstream config.toml, credentials, storage, virtual environment or WebUI is included.
Assets contain stock music and default Chinese/English fonts used by the media pipeline.
Original source and copied asset SHA-256 hashes are recorded in MANIFEST.json.
Local integration belongs in studio/engine and studio/integrations; vendor code is unchanged.
