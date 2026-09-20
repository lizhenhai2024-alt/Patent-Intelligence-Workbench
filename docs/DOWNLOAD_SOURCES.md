# Download source policy

V1 does not scrape official patent websites when a stable public automation API is not documented.

## EP

Automated primary source: EPO European Publication Server.

The server provides direct PDF/A access for EP A/B publications and has a documented REST/web-service interface.

## JP

- J-PlatPat: official publication PDF access, modeled as MANUAL.
- JPO Patent Information Retrieval API: REGISTERED API for Japanese application metadata and application documents. It is not modeled as a direct gazette-PDF endpoint in V1.
- Cross-jurisdiction family data remains handled by the family provider layer.

## CN

- CNIPA Patent Publication System: official publication/full-text download, modeled as MANUAL.
- CNIPA IP Data Public Service System: registered route for larger-scale data acquisition.

V1 does not reverse-engineer ephemeral CNIPA browser endpoints.

## WO

- WIPO PATENTSCOPE: official PDF access, modeled as MANUAL.
- WIPO PCT data/document services: modeled as LICENSED programmatic access.

PATENTSCOPE web pages are not robot-scraped by V1.

## Automated fallback

Google Patents remains the general automated fallback for publication PDFs where available.

The download manager records structured official fallback hints when all automated providers fail, so the UI and family manifest can direct the user to the authoritative source rather than returning a dead-end error.
