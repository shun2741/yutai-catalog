#!/usr/bin/env python3
"""
J-Quants token helper (interactive CLI)

- Step 1: Get refreshToken by posting email + password
  POST https://api.jquants.com/v1/token/auth_user

- Step 2: Exchange refreshToken for idToken
  POST https://api.jquants.com/v1/token/auth_refresh?refreshtoken=...

Usage:
  $ python scripts/jquants_token_cli.py
  # or with args
  $ python scripts/jquants_token_cli.py --mail you@example.com --password '****' --json

Environment variables (optional):
  JQ_MAIL, JQ_PASSWORD

Outputs tokens to stdout. With --json prints combined JSON.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from typing import Tuple

import requests


AUTH_USER_URL = "https://api.jquants.com/v1/token/auth_user"
AUTH_REFRESH_URL = "https://api.jquants.com/v1/token/auth_refresh"
UA = {"User-Agent": "yutai-catalog-admin/1.0"}


def get_refresh_token(mail: str, password: str) -> str:
    payload = {"mailaddress": mail, "password": password}
    r = requests.post(AUTH_USER_URL, data=json.dumps(payload), headers={**UA, "Content-Type": "application/json"}, timeout=20)
    r.raise_for_status()
    data = r.json() or {}
    # Typical: {"refreshToken":"..."}
    token = data.get("refreshToken") or data.get("refreshtoken") or data.get("refresh_token")
    if not token:
        raise RuntimeError(f"refreshToken not found in response: {data}")
    return token


def get_id_token(refresh_token: str) -> str:
    url = f"{AUTH_REFRESH_URL}?refreshtoken={refresh_token}"
    r = requests.post(url, headers=UA, timeout=20)
    r.raise_for_status()
    data = r.json() or {}
    # Typical: {"idToken":"..."}
    token = data.get("idToken") or data.get("id_token")
    if not token:
        raise RuntimeError(f"idToken not found in response: {data}")
    return token


def prompt_credentials(default_mail: str | None = None) -> Tuple[str, str]:
    mail = default_mail or input("Mail address: ").strip()
    if not mail:
        print("Mail is required", file=sys.stderr)
        sys.exit(2)
    password_env = os.environ.get("JQ_PASSWORD")
    if password_env:
        password = password_env
    else:
        password = getpass.getpass("Password: ")
    if not password:
        print("Password is required", file=sys.stderr)
        sys.exit(2)
    return mail, password


def main() -> None:
    parser = argparse.ArgumentParser(description="J-Quants token helper")
    parser.add_argument("--mail", default=os.environ.get("JQ_MAIL"), help="Email address (or set JQ_MAIL)")
    parser.add_argument("--password", default=os.environ.get("JQ_PASSWORD"), help="Password (or set JQ_PASSWORD)")
    parser.add_argument("--json", action="store_true", help="Print tokens as a single JSON object")
    args = parser.parse_args()

    mail = args.mail
    password = args.password
    if not mail or not password:
        mail, password = prompt_credentials(default_mail=mail)

    try:
        refresh_token = get_refresh_token(mail, password)
        id_token = get_id_token(refresh_token)
    except requests.HTTPError as e:
        print(f"HTTPError: {e} | body={e.response.text if e.response is not None else ''}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps({"refreshToken": refresh_token, "idToken": id_token}, ensure_ascii=False, indent=2))
    else:
        print("refreshToken:", refresh_token)
        print("idToken:", id_token)


if __name__ == "__main__":
    main()

