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

Builds the image locally for linux/amd64 (free-trial subscriptions cannot run ACR Tasks, so `--source` builds are out), pushes it to the `btsmt2026acr` registry, creates or updates the app, prints the public URL and curls `/healthz`. Re-run after every change you want live; the tag is the current commit. Secrets (`BTS_FOUNDRY_API_KEY`, `BTS_COSMOS_KEY`) are stored as Container Apps secrets, not as plain env vars. The first deploy warns that the app "must be restarted in order for secret changes to take effect"; the final `az containerapp update` creates a new revision, which picks them up. If `/api/matches/{id}/insights` only ever returns `source: template`, run `az containerapp revision restart`.

Current deployment: <https://bts.ashygrass-da897bf3.eastus2.azurecontainerapps.io>.

## Cosmos DB (profiles)

User profiles (audience, language, followed club) persist in an Azure Cosmos DB NoSQL account with the free tier (1,000 RU/s, 25 GB), one per subscription:

```bash
az cosmosdb create --name bts-cosmos-mt2026 --resource-group bts-rg \
  --locations regionName=eastus2 failoverPriority=0 --enable-free-tier true \
  --kind GlobalDocumentDB --default-consistency-level Session
az cosmosdb show --name bts-cosmos-mt2026 --resource-group bts-rg --query documentEndpoint -o tsv
az cosmosdb keys list --name bts-cosmos-mt2026 --resource-group bts-rg --query primaryMasterKey -o tsv
```

Put the endpoint and key into `.env` as `BTS_COSMOS_ENDPOINT` and `BTS_COSMOS_KEY`; the app creates the `bts` database and the `profiles` container (partition key `/user_id`) on first use. `infra/deploy.sh` stores the key as the `cosmos-key` secret. Without these variables the app keeps profiles in memory and logs `profiles: in-memory store`.

## Application Insights (agent traces)

Every crew run (agent, model call, tool call) is an OpenTelemetry span. One Application Insights resource receives them; connect it to the Foundry project as well and the same traces show in the Foundry portal under Tracing:

```bash
az extension add --name application-insights --upgrade
az monitor app-insights component create --app bts-insights --location eastus2 \
  --resource-group bts-rg --application-type web
az monitor app-insights component show --app bts-insights --resource-group bts-rg \
  --query connectionString -o tsv
```

Put the value into `.env` as `APPLICATIONINSIGHTS_CONNECTION_STRING`; `infra/deploy.sh` stores it as the `appinsights-cs` secret. Without it the app logs `telemetry: off`. Query the spans with:

```bash
az monitor app-insights query --app bts-insights --resource-group bts-rg --offset 6h \
  --analytics-query "dependencies | where name startswith 'invoke_agent' | project timestamp, name, duration | top 20 by timestamp desc"
```

`--offset` widens the CLI's query window (it defaults to the last hour, whatever the KQL says). Spans from a match at 30× show up within seconds; a 300× burst on the 0.5 vCPU replica saturates the exporter and drops them. The connection string holds several `;`-separated fields: `infra/deploy.sh` reads `.env` line by line for that reason (sourcing it would cut the value at the first `;`).

`BTS_AGENT_MODE=simple` turns the crew off (two prompts instead of four roles) without redeploying anything else.

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
