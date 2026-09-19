# EOP Tech & Development Contracts

Collects **software / dashboard / portal / development** tenders and contracts from Bulgaria’s public procurement portal [ЦАИС ЕОП](https://app.eop.bg/today) and stores a curated dataset in this repo.

## What’s here

| Path | Purpose |
| --- | --- |
| `data/tech-development.json` | Curated tenders + contracts (deduped, scored) |
| `data/tech-development.csv` | Same data for spreadsheets |
| `data/tech-development.md` | Top matches digest |
| `eop_collector/` | Collector agent (public NX1 JSON API) |
| `web/` | Browse UI for the dataset |

Source UI: [Today](https://app.eop.bg/today) · [Search](https://app.eop.bg/today/reporting/search)

## Browse the results

```bash
cd web
npm install
npm run dev
```

Open [EOP Tech Contracts](http://127.0.0.1:43127).

## Contact dataset

Enrich every procurement with tender + buyer contact persons (name, email, phone, address):

```bash
python3 eop_collector/enrich_contacts.py
```

Outputs:

| File | Contents |
| --- | --- |
| `data/tech-development-contacts.json` | Full rows + contacts |
| `data/tech-development-contacts.csv` | Spreadsheet of all rows |
| `data/contact-list.csv` | Deduped contact people for outreach |
| `data/tech-development-contacts.md` | Digest |

Caches under `data/cache/` so re-runs only fetch missing IDs.

## Re-run the collector

```bash
python3 eop_collector/collect.py --max-pages 2 --page-size 50
./scripts/collect-eop.sh
```

It queries:

- Quick search keywords (софтуер, портал, платформа, CRM, ERP, дигитализация, …)
- Advanced tenders by IT CPV codes (`72000000`, `72200000`, `72230000`, `48000000`, …)
- Awarded contracts by the same keywords/CPVs

Then keeps items that look like **development / systems / web / software** work (not pure hardware toner carts).

API used (public, no login):

`POST https://service.eop.bg/NX1Service.svc/GetQuickSearchResult`  
`POST https://service.eop.bg/NX1Service.svc/GetPublishedTendersAdvancedSearchResult`  
`POST https://service.eop.bg/NX1Service.svc/GetContractsAdvancedSearchResult`  
`POST https://service.eop.bg/NX1Service.svc/GetPublishedTenderDetails`  
`POST https://service.eop.bg/NX1Service.svc/GetPublicBuyerProfileBasicInformation`

## Hermes (optional)

This environment also has [Hermes Agent](https://hermes-agent.nousresearch.com) installed under `~/.hermes/`. See `scripts/open-hermes.sh`.
