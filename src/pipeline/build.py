from __future__ import annotations
import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from .models import Catalog, Company, Chain, Store


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
DIST = ROOT / "dist"


def today() -> str:
    d = datetime.now(timezone.utc)
    return f"{d.year:04d}-{d.month:02d}-{d.day:02d}"


def read_csv(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def list_from_csv(v: str) -> List[str]:
    if not v:
        return []
    return [s.strip() for s in str(v).split(",") if s.strip()]


def build_catalog() -> Catalog:
    # Read raw CSV rows first
    companies_rows = read_csv(DATA / "companies.csv")
    chains_rows = read_csv(DATA / "chains.csv")
    stores_rows = read_csv(DATA / "stores.csv")

    # Build chains first (source of truth for company<->chain relation)
    chains = [
        Chain(
            id=r.get("id", ""),
            displayName=r.get("displayName", ""),
            category=r.get("category", "その他"),
            companyIds=list_from_csv(r.get("companyIds", "")),
            voucherTypes=list_from_csv(r.get("voucherTypes", "")),
            tags=list_from_csv(r.get("tags", "")),
            url=r.get("url") or None,
        )
        for r in chains_rows
        if r.get("id") and r.get("displayName")
    ]

    # Build companyId -> [chainId] reverse index from chains
    comp_to_chain_ids: dict[str, List[str]] = {}
    for ch in chains:
        for comp_id in ch.companyIds:
            comp_to_chain_ids.setdefault(comp_id, []).append(ch.id)
    # Keep chainIds lists stable (sorted) for diff friendliness
    for k, v in comp_to_chain_ids.items():
        comp_to_chain_ids[k] = sorted(set(v))

    # Build companies, overriding chainIds from reverse index (ignore CSV chainIds)
    comps = [
        Company(
            id=r.get("id", ""),
            name=r.get("name", ""),
            ticker=r.get("ticker") or None,
            chainIds=comp_to_chain_ids.get(r.get("id", ""), []),
            voucherTypes=list_from_csv(r.get("voucherTypes", "")),
            notes=r.get("notes") or None,
        )
        for r in companies_rows
        if r.get("id") and r.get("name")
    ]

    stores = [
        Store(
            id=r.get("id", ""),
            chainId=r.get("chainId", ""),
            name=r.get("name", ""),
            address=r.get("address", "") or "",
            lat=float(r.get("lat", "0")),
            lng=float(r.get("lng", "0")),
            tags=list_from_csv(r.get("tags", "")),
            updatedAt=r.get("updatedAt") or datetime.now(timezone.utc).isoformat(),
        )
        for r in stores_rows
        if r.get("id") and r.get("chainId") and r.get("name")
    ]

    version = today()
    return Catalog(version=version, companies=comps, chains=chains, stores=stores)


def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> None:
    DIST.mkdir(parents=True, exist_ok=True)
    catalog = build_catalog()
    filename = f"catalog-{catalog.version}.json"
    out_json = DIST / filename

    data = json.dumps(json.loads(catalog.model_dump_json()), ensure_ascii=False, indent=2)
    out_json.write_text(data, encoding="utf-8")

    h = sha256_hex(data.encode("utf-8"))
    manifest_path = DIST / "catalog-manifest.json"
    manifest = {"version": catalog.version, "hash": h, "url": filename}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Generated:", out_json)
    print("Updated:", manifest_path)


if __name__ == "__main__":
    main()
