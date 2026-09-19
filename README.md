# EOP Tech & Development Contracts

Collects **software / dashboard / portal / development** tenders and contracts from Bulgaria’s public procurement portal [ЦАИС ЕОП](https://app.eop.bg/today) and stores a curated dataset in this repo — with **active status**, **budget scope**, **English titles/descriptions**, and buyer **contacts**.

## What’s here

| Path | Purpose |
| --- | --- |
| `data/tech-development.json` | Curated tenders + contracts (deduped, scored, status/budget) |
| `data/tech-development-contacts.json` | Same + contacts + English fields (used by the web UI) |
| `data/tech-development*.csv` / `.md` | Spreadsheet + digest exports |
| `data/cache/translations.json` | Cached BG→EN translations (committed for reuse) |
| `eop_collector/` | Collector + enrich agents (public NX1 JSON API) |
| `web/` | Browse UI (Vercel root directory) |
| `.github/workflows/weekly-collect.yml` | Scheduled re-collect (Mon + Fri) |

Source UI: [Today](https://app.eop.bg/today) · [Search](https://app.eop.bg/today/reporting/search)

## Browse the results

```bash
cd web
npm install
npm run dev
```

Open [http://127.0.0.1:43127](http://127.0.0.1:43127).

The UI defaults to **English** title/description when available, shows an **Active / Closed / Awarded** badge, a clear **budget scope** line, and supports an **Active only** filter. Contact person fields remain visible on each row.

Vercel: set the project **Root Directory** to `web/`. `web/vercel.json` rewrites SPA routes to `index.html`.

## Dataset fields (highlights)

| Field | Meaning |
| --- | --- |
| `status` / `is_active` / `status_label` | `active` (open for offers), `closed`, `awarded` (contracts), or `unknown` |
| `budget_amount` / `currency_code` / `budget_scope` | Estimated or contract value with EUR/BGN/USD mapping |
| `title_en` / `description_en` / `contract_subject_en` | English text (fallback: Bulgarian source) |
| `contact_*` | Tender or buyer-profile contact person |

Status prefers EOP `PublishedTenderParticipationStatus` and offer deadlines from search / `GetPublishedTenderDetails`. Currency maps NX1 `CurrencyType` / `TenderCurrency` (`1=EUR`, `2=USD`, `3=BGN`, …).

## Re-run the pipeline

```bash
# 1) Collect
python3 eop_collector/collect.py --max-pages 4 --page-size 50
# or: ./scripts/collect-eop.sh

# 2) Contacts (buyer + tender persons)
python3 eop_collector/enrich_contacts.py --tender-limit 250

# 3) Status, budget, English (cached translations)
python3 eop_collector/enrich_i18n.py --refresh-details --tender-limit 400
```

Translation uses, in order when available:

1. `OPENAI_API_KEY` (optional)
2. [MyMemory](https://mymemory.translated.net/) free API (default; set `MYMEMORY_EMAIL` for a higher quota)
3. LibreTranslate (`LIBRETRANSLATE_URL`, optional)

Results are cached in `data/cache/translations.json`. Active and high-score items are translated first.

## Weekly GitHub Action

Workflow: `.github/workflows/weekly-collect.yml`

| | |
| --- | --- |
| **Schedule** | **Monday and Friday `06:00 UTC`** (≈ **09:00 Europe/Sofia** in summer / EEST; ≈ 08:00 in winter / EET) |
| **Manual** | Actions → “Weekly EOP collect” → Run workflow |
| **Steps** | `collect.py` → `enrich_contacts.py` → `enrich_i18n.py` → commit updated `data/*` and `web/public/data/*` to the default branch |

### Enabling the workflow (permissions)

1. Repo **Settings → Actions → General**: allow GitHub Actions to create commits / allow Actions.
2. Default `GITHUB_TOKEN` needs **`contents: write`** (the workflow sets `permissions: contents: write`).
3. If the default branch is **protected**, either:
   - allow GitHub Actions to bypass the restriction, or
   - add a PAT / fine-grained token with `contents: write` as secret `GH_PAT` and change the checkout `token` + push remote to use it, or
   - switch the final step to open a PR instead of pushing to `main`.
4. Optional secrets/vars for better translations: `OPENAI_API_KEY`, `MYMEMORY_EMAIL`, `LIBRETRANSLATE_URL`, `TRANSLATE_PROVIDER`.

## API used (public, no login)

`POST https://service.eop.bg/NX1Service.svc/GetQuickSearchResult`  
`POST https://service.eop.bg/NX1Service.svc/GetPublishedTendersAdvancedSearchResult`  
`POST https://service.eop.bg/NX1Service.svc/GetContractsAdvancedSearchResult`  
`POST https://service.eop.bg/NX1Service.svc/GetPublishedTenderDetails`  
`POST https://service.eop.bg/NX1Service.svc/GetPublicBuyerProfileBasicInformation`

## Hermes (optional)

This environment also has [Hermes Agent](https://hermes-agent.nousresearch.com) installed under `~/.hermes/`. See `scripts/open-hermes.sh`.
