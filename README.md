# Yutai Catalog Pipeline (Template)

This is a template repository for generating and publishing catalog JSON for the shareholder benefits PWA.

- Input: CSV files (companies.csv, chains.csv, stores.csv)
- Output: dist/catalog-YYYY-MM-DD.json + dist/catalog-manifest.json
- Delivery: GitHub Pages (Actions included)

## Quick start

1. Create a new GitHub repository (e.g., yutai-catalog)
2. Copy all files from this template into the new repo root
3. Commit and push
4. Update `data/*.csv` and push
5. Pages will publish `dist/` at https://<user>.github.io/<repo>/dist
   - Tip: workflows are triggered by any push to `main`.

## CSV format

See `data/*.csv` in this template. Arrays are comma-separated.

## Actions variables

- No secrets needed by default.
- Optional: set `TZ` or other variables as you like.

## License

Private/internal by default. Add a license if you plan to publish.
