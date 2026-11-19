# Education Discovery — Cloud deployment preparation

**Status:** deployable staging package; NOT deployed and NOT production-hardened. No live crawls or institution data are included.

## Railway (recommended for first staging deployment)
1. Connect the Railway app in ChatGPT (requires your authorization). If it supports project creation/deployment, use it; otherwise create a Railway project in your own account.
2. Create a **PostgreSQL** database service in that project.
3. Create an application service from this source (push to your own private GitHub repository and select it as source, or deploy with Railway CLI). The included Dockerfile and `railway.json` provide build and health check configuration.
4. Set `DATABASE_URL` in the application service to the Railway PostgreSQL connection reference (use Railway's variable reference UI, not a pasted password). Set `ENABLE_ADMIN=false`. `PORT` is supplied by Railway.
5. Run `python init_db.py` **once** in an environment connected to the database, before using the site. It creates the `edu` schema and tables. The `/health` endpoint only verifies that the HTTP server responds; it does not test DB connectivity.
6. Generate a public domain in Railway. Open `/` to view the website. Initially the list will be empty until real crawled data are ingested.
7. For crawling, run `python batch.py --csv institutions.csv --workers 2 --limit 10` on an authorized worker with network access, then `python pipeline.py --input output` with `DATABASE_URL`. Review robots.txt and site terms. This is **not** a scheduled worker yet.

## Security boundaries
- Admin endpoints are **disabled by default** for internet-facing deployment. Do not set `ENABLE_ADMIN=true` on a public service: the single shared token is insufficient for production authentication. Admin review requires a future private/admin service with proper authentication.
- Do not upload `.env` files or passwords to GitHub or ChatGPT. Use Railway secret variables.
- Do not collect student PII, tracking identifiers, or CRM data with this staging version. Consent, access controls, audit trails, and data retention are not yet implemented.
- Avoid interpreting keyword-extracted snippets as verified facts. Comparisons show only approved data.

## Known limitations
- No database readiness check, production admin identity system, crawler job queue, scheduled refresh, AI normalization, data governance, or proven live crawl.
- The existing crawler is a proof of concept and is not suitable for high-volume operation without further reliability work.
- No actual Railway project or public URL exists until your account is connected and deployment is authorized.

## Render alternative (if Railway connection fails)
1. Connect your Render account in ChatGPT, or create a private GitHub repository with this package and choose **New > Blueprint** in Render.
2. The included `render.yaml` defines one Free Docker web service in Singapore.
3. Set `DATABASE_URL` to the Internal Database URL of the existing `education-platform-db` in the Render dashboard. Keep the connection string out of GitHub and chat.
4. Run `python init_db.py` once from an authorized environment with database connectivity to initialize the schema. The web service starts even if the schema is not yet initialized, but the data API will return 503.
5. Visit `/health` to confirm the web process is responding, then `/api/institutions` to check database access. Empty `[]` is expected before crawling.

## Operational note
This rebuild adds a second cloud-provider configuration and smoke tests. It does not establish an authenticated cloud connection, provision a database, or deploy a public URL by itself.
