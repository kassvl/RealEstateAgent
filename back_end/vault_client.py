"""Simple Vault dev client for fetching secrets."""
import os
import hvac

VAULT_ADDR = os.getenv("VAULT_ADDR", "http://vault:8200")
VAULT_TOKEN = os.getenv("VAULT_TOKEN", "root")

try:
    _client = hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN)
except Exception:
    _client = None  # Vault not available in local dev


def get_secret(key: str, path: str = "secret/data/real-estate") -> str | None:
    """Fetch secret from Vault; if Vault unavailable, fallback to env.

    In local dev (no Vault), returns None so callers can fallback to env vars.
    """
    if _client is None:
        return None
    try:
        if not _client.is_authenticated():
            return None
        secret = _client.secrets.kv.v2.read_secret_version(path=path)
        return secret["data"]["data"].get(key)
    except Exception:
        return None
