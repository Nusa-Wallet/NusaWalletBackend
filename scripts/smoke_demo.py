"""End-to-end smoke check for the NusaWallet demo stack.

Run after AI and backend services are up:
    python scripts/smoke_demo.py
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class SmokeConfig:
    backend_url: str
    ai_url: str
    email: str
    password: str
    timeout: float


def _get_json(client: httpx.Client, url: str, **kwargs: Any) -> dict:
    response = client.get(url, **kwargs)
    response.raise_for_status()
    return response.json()


def _post_json(client: httpx.Client, url: str, payload: dict, **kwargs: Any) -> dict:
    response = client.post(url, json=payload, **kwargs)
    response.raise_for_status()
    return response.json()


def _wait_for_health(client: httpx.Client, name: str, url: str, timeout: float) -> None:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            body = _get_json(client, f"{url}/health")
            if body.get("status") == "ok":
                print(f"[ok] {name} health: {body}")
                return
            last_error = f"unexpected body {body}"
        except Exception as exc:  # noqa: BLE001 - diagnostic script
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(f"{name} did not become healthy: {last_error}")


def run(config: SmokeConfig) -> None:
    with httpx.Client(timeout=10.0) as client:
        _wait_for_health(client, "backend", config.backend_url, config.timeout)
        _wait_for_health(client, "ai", config.ai_url, config.timeout)

        token = _post_json(
            client,
            f"{config.backend_url}/auth/login",
            {"email": config.email, "password": config.password},
        )["access_token"]
        auth = {"Authorization": f"Bearer {token}"}
        print(f"[ok] login: {config.email}")

        wallets = _get_json(client, f"{config.backend_url}/wallets", headers=auth)
        print(f"[ok] wallets: {len(wallets)} currencies")

        link = _post_json(
            client,
            f"{config.backend_url}/payment-links",
            {"currency": "SGD", "amount": 125, "note": "Smoke demo payment"},
            headers=auth,
        )
        checkout_url = f"{config.backend_url}{link['url']}"
        checkout = client.get(checkout_url)
        checkout.raise_for_status()
        if "NusaWallet Sandbox Checkout" not in checkout.text:
            raise RuntimeError("public checkout did not render expected page")
        print(f"[ok] public checkout: {checkout_url}")

        paid = _post_json(
            client,
            f"{config.backend_url}/payment-links/{link['code']}/pay",
            {"payer_name": "Smoke Client", "origin_country": "SG"},
        )
        print(f"[ok] sandbox pay: {paid['status']} risk={paid.get('risk_level')}")

        advisory = _get_json(
            client,
            f"{config.backend_url}/insights/fx-advisory",
            headers=auth,
            params={"base": "SGD", "quote": "IDR", "amount": 125},
        )
        print(
            "[ok] fx advisory: "
            f"{advisory.get('pair')} {advisory.get('action')} "
            f"confidence={advisory.get('confidence')}"
        )

        conversion = _post_json(
            client,
            f"{config.backend_url}/settlement/convert",
            {
                "from_currency": "SGD",
                "to_currency": "IDR",
                "amount": 125,
                "convert_percentage": 40,
                "idempotency_key": "smoke-demo-sgd-idr-40",
            },
            headers=auth,
        )
        retry = _post_json(
            client,
            f"{config.backend_url}/settlement/convert",
            {
                "from_currency": "SGD",
                "to_currency": "IDR",
                "amount": 125,
                "convert_percentage": 40,
                "idempotency_key": "smoke-demo-sgd-idr-40",
            },
            headers=auth,
        )
        if retry["transaction_id"] != conversion["transaction_id"] or not retry["idempotent"]:
            raise RuntimeError("conversion idempotency retry did not return the original transaction")
        print(
            "[ok] conversion: "
            f"tx={conversion['transaction_id']} out={conversion['amount_out']} "
            "retry=idempotent"
        )


def parse_args() -> SmokeConfig:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-url", default="http://localhost:8000")
    parser.add_argument("--ai-url", default="http://localhost:8001")
    parser.add_argument("--email", default="demo@nusawallet.id")
    parser.add_argument("--password", default="password123")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    return SmokeConfig(
        backend_url=args.backend_url.rstrip("/"),
        ai_url=args.ai_url.rstrip("/"),
        email=args.email,
        password=args.password,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    try:
        run(parse_args())
    except Exception as exc:  # noqa: BLE001 - script should print concise diagnostics
        print(f"[fail] {exc}", file=sys.stderr)
        sys.exit(1)
