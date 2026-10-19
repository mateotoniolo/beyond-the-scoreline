# Deployment: Azure Container Apps

One container (FastAPI + built web UI) on Azure Container Apps, consumption plan, external ingress on port 8000. `infra/deploy.sh` builds the image from the repo's Dockerfile in Azure and creates or updates the app.

## Once

1. Azure free account (credit card, USD 200 for 30 days). Opened on or after 2026-10-19 it covers the judging window (until 2026-11-10 23:59 PT).
2. `brew install azure-cli && az login`, then `az account set --subscription <id>` if you have several.
3. Foundry resource and `gpt-5-mini` deployment (see `docs/FOUNDRY.md`), Cosmos DB free-tier account (NoSQL API), both written into `.env`.

## Deploy

```bash
infra/deploy.sh
```

Prints the public URL and curls `/healthz`. Re-run after every change you want live. Secrets (`BTS_FOUNDRY_API_KEY`, `BTS_COSMOS_KEY`) are stored as Container Apps secrets, not as plain env vars.

## Judging window

From 2026-10-27 to 2026-11-11 keep one replica warm so a judge never waits for a cold start:

```bash
MIN_REPLICAS=1 infra/deploy.sh
```

A single 0.5 vCPU / 1 GiB replica for two weeks is slightly above the monthly free grant; the overage is small. Before that, `MIN_REPLICAS=0` scales to zero at no cost.

## Verify from the outside

Open the URL in a private window, play seed 11 at 30×, and confirm insights show `Foundry` and `verified`. Check `az containerapp logs show --name bts --resource-group bts-rg --follow` for `LLM: Microsoft Foundry model gpt-5-mini` at start-up.

## Tear down (after 2026-11-11)

```bash
az group delete --name bts-rg --yes --no-wait
```
