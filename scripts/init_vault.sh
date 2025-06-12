#!/usr/bin/env bash
# Initializes Vault dev server with necessary secrets for local development.
set -euo pipefail

: "${VAULT_ADDR:=http://vault:8200}"  # default matches docker-compose vault service
: "${VAULT_TOKEN:=root}"              # dev root token
: "${GEMINI_API_KEY:=replace_me}"     # export before running for real key
: "${PROXY_LIST:=}"                   # optional proxy list comma-separated

# Wait until Vault is up
until curl -s ${VAULT_ADDR}/v1/sys/health > /dev/null; do
  echo "Waiting for Vault at ${VAULT_ADDR}..."
  sleep 2
done

echo "Writing secrets to Vault..."

vault login -no-print ${VAULT_TOKEN}

echo "Writing real-estate secrets"
vault kv put secret/real-estate GEMINI_API_KEY="${GEMINI_API_KEY}" PROXY_LIST="${PROXY_LIST}"

echo "Vault secrets populated."
