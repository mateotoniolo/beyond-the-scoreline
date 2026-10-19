#!/usr/bin/env bash
# Deploy Beyond the Scoreline to Azure Container Apps (one container).
#
# The image is built locally (Docker, linux/amd64) and pushed to an Azure Container Registry,
# because free-trial subscriptions cannot run ACR Tasks (the `az containerapp up --source` path).
#
# Prerequisites: Docker running, `az login` done, and a .env with BTS_FOUNDRY_ENDPOINT /
# BTS_FOUNDRY_API_KEY / BTS_FOUNDRY_MODEL (optionally BTS_COSMOS_*, BTS_AGENT_MODE and
# APPLICATIONINSIGHTS_CONNECTION_STRING). Usage:
#   infra/deploy.sh                  # build, push, create or update the app, min replicas 0
#   MIN_REPLICAS=1 infra/deploy.sh   # keep one replica warm (judging window)
set -euo pipefail

RG="${RG:-bts-rg}"
LOCATION="${LOCATION:-eastus2}"
APP="${APP:-bts}"
ENV_NAME="${ENV_NAME:-bts-env}"
ACR="${ACR:-btsmt2026acr}"
MIN_REPLICAS="${MIN_REPLICAS:-0}"
ENV_FILE="${ENV_FILE:-.env}"
TAG="${TAG:-$(git rev-parse --short HEAD 2>/dev/null || date +%s)}"
IMAGE="$ACR.azurecr.io/bts:$TAG"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing $ENV_FILE (copy .env.example)" >&2
  exit 1
fi
# Read KEY=VALUE lines verbatim: sourcing the file would cut values at ';' (the Application
# Insights connection string has several) and treat the rest as commands.
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] || continue
  key="${line%%=*}"
  value="${line#*=}"
  if [[ "$value" == \"*\" ]]; then
    value="${value#\"}"; value="${value%\"}"
  else
    value="${value%%[[:space:]]#*}"   # drop an inline comment
    value="${value%"${value##*[![:space:]]}"}"  # and trailing spaces
  fi
  export "$key=$value"
done < "$ENV_FILE"

# The registry's TLS handshake times out now and then; retry the login and the push.
retry() {
  local attempt
  for attempt in 1 2 3 4 5; do
    "$@" && return 0
    echo "attempt $attempt of 5 failed: $1 ${2:-}; retrying in 15 s" >&2
    sleep 15
  done
  return 1
}

az group create --name "$RG" --location "$LOCATION" --output none
az acr create --name "$ACR" --resource-group "$RG" --sku Basic --admin-enabled true --output none
retry az acr login --name "$ACR"

echo "building $IMAGE"
retry docker buildx build --platform linux/amd64 -t "$IMAGE" --push .

ACR_USER=$(az acr credential show --name "$ACR" --query username -o tsv)
ACR_PASS=$(az acr credential show --name "$ACR" --query 'passwords[0].value' -o tsv)

az containerapp up \
  --name "$APP" \
  --resource-group "$RG" \
  --location "$LOCATION" \
  --environment "$ENV_NAME" \
  --image "$IMAGE" \
  --registry-server "$ACR.azurecr.io" \
  --registry-username "$ACR_USER" \
  --registry-password "$ACR_PASS" \
  --ingress external \
  --target-port 8000 \
  --env-vars \
    "BTS_FOUNDRY_ENDPOINT=${BTS_FOUNDRY_ENDPOINT:-}" \
    "BTS_FOUNDRY_MODEL=${BTS_FOUNDRY_MODEL:-gpt-5-mini}" \
    "BTS_AGENT_MODE=${BTS_AGENT_MODE:-}" \
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
if [[ -n "${APPLICATIONINSIGHTS_CONNECTION_STRING:-}" ]]; then
  SECRETS+=("appinsights-cs=${APPLICATIONINSIGHTS_CONNECTION_STRING}")
  SECRET_ENVS+=("APPLICATIONINSIGHTS_CONNECTION_STRING=secretref:appinsights-cs")
fi
if (( ${#SECRETS[@]} )); then
  az containerapp secret set --name "$APP" --resource-group "$RG" --output none --secrets "${SECRETS[@]}"
  az containerapp update --name "$APP" --resource-group "$RG" --output none --set-env-vars "${SECRET_ENVS[@]}"
fi
az containerapp update --name "$APP" --resource-group "$RG" --output none \
  --min-replicas "$MIN_REPLICAS" --max-replicas 1 --cpu 0.5 --memory 1.0Gi

FQDN=$(az containerapp show --name "$APP" --resource-group "$RG" --query properties.configuration.ingress.fqdn -o tsv)
echo "deployed: https://$FQDN"
curl -fsS --max-time 120 "https://$FQDN/healthz" && echo  # a cold start takes about 25 s
