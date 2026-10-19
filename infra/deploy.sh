#!/usr/bin/env bash
# Deploy Beyond the Scoreline to Azure Container Apps from source (one container).
#
# Prerequisites: `az login` done, an Azure subscription selected, and a .env file with
# BTS_FOUNDRY_ENDPOINT / BTS_FOUNDRY_API_KEY / BTS_FOUNDRY_MODEL (and optionally the
# BTS_COSMOS_* variables). Usage:
#   infra/deploy.sh            # create or update the app, min replicas 0
#   MIN_REPLICAS=1 infra/deploy.sh   # keep one replica warm (judging window)
set -euo pipefail

RG="${RG:-bts-rg}"
LOCATION="${LOCATION:-eastus2}"
APP="${APP:-bts}"
ENV_NAME="${ENV_NAME:-bts-env}"
MIN_REPLICAS="${MIN_REPLICAS:-0}"
ENV_FILE="${ENV_FILE:-.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing $ENV_FILE (copy .env.example)" >&2
  exit 1
fi
# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

az group create --name "$RG" --location "$LOCATION" --output none

# Build from the Dockerfile in the cloud and create/update the app with external ingress.
az containerapp up \
  --name "$APP" \
  --resource-group "$RG" \
  --location "$LOCATION" \
  --environment "$ENV_NAME" \
  --source . \
  --ingress external \
  --target-port 8000 \
  --env-vars \
    "BTS_FOUNDRY_ENDPOINT=${BTS_FOUNDRY_ENDPOINT:-}" \
    "BTS_FOUNDRY_MODEL=${BTS_FOUNDRY_MODEL:-gpt-5-mini}" \
    "BTS_COSMOS_ENDPOINT=${BTS_COSMOS_ENDPOINT:-}" \
    "BTS_COSMOS_DATABASE=${BTS_COSMOS_DATABASE:-bts}" \
    "BTS_LOG_LEVEL=${BTS_LOG_LEVEL:-INFO}"

# Secrets are stored on the app and referenced by env vars; only the ones that exist are set.
SECRETS=()
SECRET_ENVS=()
if [[ -n "${BTS_FOUNDRY_API_KEY:-}" ]]; then
  SECRETS+=("foundry-key=${BTS_FOUNDRY_API_KEY}")
  SECRET_ENVS+=("BTS_FOUNDRY_API_KEY=secretref:foundry-key")
fi
if [[ -n "${BTS_COSMOS_KEY:-}" ]]; then
  SECRETS+=("cosmos-key=${BTS_COSMOS_KEY}")
  SECRET_ENVS+=("BTS_COSMOS_KEY=secretref:cosmos-key")
fi
if (( ${#SECRETS[@]} )); then
  az containerapp secret set --name "$APP" --resource-group "$RG" --output none --secrets "${SECRETS[@]}"
  az containerapp update --name "$APP" --resource-group "$RG" --output none --set-env-vars "${SECRET_ENVS[@]}"
fi
az containerapp update --name "$APP" --resource-group "$RG" --output none \
  --min-replicas "$MIN_REPLICAS" --max-replicas 1 --cpu 0.5 --memory 1.0Gi

FQDN=$(az containerapp show --name "$APP" --resource-group "$RG" --query properties.configuration.ingress.fqdn -o tsv)
echo "deployed: https://$FQDN"
curl -fsS "https://$FQDN/healthz" && echo
