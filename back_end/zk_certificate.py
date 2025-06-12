"""Zero-knowledge like valuation certificate: we hash the valuation payload and (optionally) write it to Ethereum testnet.
For demo purposes, if WEB3_PROVIDER is not set, we just return the hash string."""
import os, json, hashlib, time
from typing import Any

try:
    from web3 import Web3
except ImportError:  # build still works if web3 not installed yet
    Web3 = None  # type: ignore


def _compute_hash(payload: Any) -> str:
    data = json.dumps(payload, sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()


def issue_certificate(payload: dict) -> dict:
    """Hashes payload, optionally stores on-chain, returns dict with hash & tx (if any)."""
    hash_val = _compute_hash(payload)
    provider_url = os.getenv("WEB3_PROVIDER")
    if provider_url and Web3:
        w3 = Web3(Web3.HTTPProvider(provider_url))
        acct = w3.eth.account.from_key(os.getenv("WEB3_PRIVATE_KEY", "0x0"))
        nonce = w3.eth.get_transaction_count(acct.address)
        tx = {
            "to": acct.address,  # self, zero-value tx with data
            "value": 0,
            "gas": 200000,
            "gasPrice": w3.to_wei("10", "gwei"),
            "nonce": nonce,
            "data": Web3.to_bytes(text=hash_val),
        }
        signed = acct.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
        return {"hash": hash_val, "tx": tx_hash.hex()}
    else:
        return {"hash": hash_val, "tx": None, "on_chain": False}
