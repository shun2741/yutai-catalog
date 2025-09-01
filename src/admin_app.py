from __future__ import annotations
import csv
import html
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict

from flask import Flask, request, redirect, url_for


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


app = Flask(__name__)


ALLOWED_VOUCHER_TYPES = ["食事", "買い物", "レジャー", "その他"]


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def write_csv(path: Path, rows: List[Dict[str, str]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def append_row_csv(path: Path, row: Dict[str, str], fieldnames: List[str]) -> None:
    rows = read_csv(path)
    # simple duplicate check by id
    if any(r.get("id") == row.get("id") for r in rows):
        raise ValueError(f"ID already exists: {row.get('id')}")
    rows.append(row)
    write_csv(path, rows, fieldnames)


@app.get("/")
def index():
    return (
        "<h1>Yutai Catalog Admin</h1>"
        "<ul>"
        f"<li><a href='{html.escape(url_for('list_companies'))}'>Companies</a></li>"
        f"<li><a href='{html.escape(url_for('list_chains'))}'>Chains</a></li>"
        f"<li><a href='{html.escape(url_for('osm_import_form'))}'>Stores: OSM Import (experimental)</a></li>"
        "</ul>"
    )


# Companies


@app.get("/companies")
def list_companies():
    rows = read_csv(DATA / "companies.csv")
    rows = sorted(rows, key=lambda r: r.get("id", ""))
    head = "<h2>Companies</h2><p><a href='/companies/new'>Add company</a></p>"
    if not rows:
        return head + "<p>No companies yet.</p>"
    th = "".join(
        f"<th>{html.escape(h)}</th>"
        for h in ["id", "name", "ticker", "chainIds", "voucherTypes", "notes"]
    )
    trs = []
    for r in rows:
        tds = "".join(
            f"<td>{html.escape(r.get(k, ''))}</td>"
            for k in ["id", "name", "ticker", "chainIds", "voucherTypes", "notes"]
        )
        trs.append(f"<tr>{tds}</tr>")
    table = f"<table border='1' cellspacing='0' cellpadding='6'><tr>{th}</tr>{''.join(trs)}</table>"
    return head + table


@app.get("/companies/new")
def new_company():
    opts = "".join(
        f"<label><input type='checkbox' name='voucherTypes' value='{html.escape(v)}'> {html.escape(v)}</label> "
        for v in ALLOWED_VOUCHER_TYPES
    )
    return (
        "<h2>Add Company</h2>"
        "<form method='post' action='/companies/new'>"
        "<div>ID <input name='id' required></div>"
        "<div>Name <input name='name' required></div>"
        "<div>Ticker <input name='ticker' placeholder='(optional)'></div>"
        f"<div>Voucher Types {opts}</div>"
        "<div>Notes <input name='notes' placeholder='(optional)'></div>"
        "<div><button type='submit'>Add</button></div>"
        "</form>"
        "<p><a href='/companies'>Back</a></p>"
    )


@app.post("/companies/new")
def create_company():
    vid = request.form.get("id", "").strip()
    name = request.form.get("name", "").strip()
    ticker = request.form.get("ticker", "").strip()
    vts = request.form.getlist("voucherTypes")
    notes = request.form.get("notes", "").strip()
    if not vid or not name:
        return "Missing id or name", 400
    row = {
        "id": vid,
        "name": name,
        "ticker": ticker,
        # As per policy, chainIds is managed via chains.csv (leave empty)
        "chainIds": "",
        "voucherTypes": ",".join(vts),
        "notes": notes,
    }
    try:
        append_row_csv(DATA / "companies.csv", row, ["id", "name", "ticker", "chainIds", "voucherTypes", "notes"])
    except ValueError as e:
        return f"<p>Error: {html.escape(str(e))}</p><p><a href='/companies'>Back</a></p>", 400
    return redirect(url_for("list_companies"))


# Chains


@app.get("/chains")
def list_chains():
    rows = read_csv(DATA / "chains.csv")
    rows = sorted(rows, key=lambda r: r.get("id", ""))
    head = "<h2>Chains</h2><p><a href='/chains/new'>Add chain</a></p>"
    if not rows:
        return head + "<p>No chains yet.</p>"
    th = "".join(
        f"<th>{html.escape(h)}</th>"
        for h in ["id", "displayName", "category", "companyIds", "voucherTypes", "tags", "url"]
    )
    trs = []
    for r in rows:
        tds = "".join(
            f"<td>{html.escape(r.get(k, ''))}</td>"
            for k in ["id", "displayName", "category", "companyIds", "voucherTypes", "tags", "url"]
        )
        trs.append(f"<tr>{tds}</tr>")
    table = f"<table border='1' cellspacing='0' cellpadding='6'><tr>{th}</tr>{''.join(trs)}</table>"
    return head + table


@app.get("/chains/new")
def new_chain():
    # Suggest existing companyIds for convenience
    comps = read_csv(DATA / "companies.csv")
    comp_ids = ",".join(sorted([c.get("id", "") for c in comps if c.get("id")]))
    vt_opts = "".join(
        f"<label><input type='checkbox' name='voucherTypes' value='{html.escape(v)}'> {html.escape(v)}</label> "
        for v in ALLOWED_VOUCHER_TYPES
    )
    return (
        "<h2>Add Chain</h2>"
        "<form method='post' action='/chains/new'>"
        "<div>ID <input name='id' required placeholder='chain-xxxx'></div>"
        "<div>Display Name <input name='displayName' required></div>"
        "<div>Category <input name='category' value='飲食'></div>"
        f"<div>Company IDs <input name='companyIds' placeholder='comp-... (comma separated)'> <small>existing: {html.escape(comp_ids)}</small></div>"
        f"<div>Voucher Types {vt_opts}</div>"
        "<div>Tags <input name='tags' placeholder='comma separated'></div>"
        "<div>URL <input name='url' placeholder='https://...'></div>"
        "<div><button type='submit'>Add</button></div>"
        "</form>"
        "<p><a href='/chains'>Back</a></p>"
    )


@app.post("/chains/new")
def create_chain():
    rid = request.form.get("id", "").strip()
    display = request.form.get("displayName", "").strip()
    category = request.form.get("category", "その他").strip() or "その他"
    company_ids = request.form.get("companyIds", "").strip()
    vts = request.form.getlist("voucherTypes")
    tags = request.form.get("tags", "").strip()
    url = request.form.get("url", "").strip()
    if not rid or not display:
        return "Missing id or displayName", 400
    row = {
        "id": rid,
        "displayName": display,
        "category": category,
        "companyIds": company_ids,
        "voucherTypes": ",".join(vts),
        "tags": tags,
        "url": url,
    }
    try:
        append_row_csv(DATA / "chains.csv", row, ["id", "displayName", "category", "companyIds", "voucherTypes", "tags", "url"])
    except ValueError as e:
        return f"<p>Error: {html.escape(str(e))}</p><p><a href='/chains'>Back</a></p>", 400
    return redirect(url_for("list_chains"))


# Stores: OSM import (experimental)


@app.get("/stores/osm_import")
def osm_import_form():
    chains = read_csv(DATA / "chains.csv")
    chain_opts = "".join(
        f"<option value='{html.escape(c['id'])}'>{html.escape(c['id'])} : {html.escape(c.get('displayName',''))}</option>"
        for c in sorted(chains, key=lambda x: x.get('id',''))
        if c.get("id")
    )
    return (
        "<h2>OSM Import (experimental)</h2>"
        "<form method='post' action='/stores/osm_import'>"
        "<div>Name Regex <input name='name_regex' value='ステーキ宮' required></div>"
        f"<div>Assign chainId <select name='chainId' required>{chain_opts}</select></div>"
        "<div>Exclude words (comma) <input name='exclude' value='駐車場,宮川'></div>"
        "<div><button type='submit'>Search & Import</button></div>"
        "</form>"
        "<p><a href='/'>Back</a></p>"
    )


def _overpass_query(name_regex: str) -> List[dict]:
    q = (
        f"[out:json][timeout:60];"
        f"area[\"name:ja\"=\"日本\"][admin_level=2];"
        f"(node[\"name\"~\"{name_regex}\"](area);"
        f" way[\"name\"~\"{name_regex}\"](area);"
        f" relation[\"name\"~\"{name_regex}\"](area););"
        f"out center tags;"
    )
    url = "https://overpass-api.de/api/interpreter?data=" + urllib.parse.quote(q)
    with urllib.request.urlopen(url) as r:
        data = r.read()
    obj = __import__("json").loads(data)
    return obj.get("elements", [])


@app.post("/stores/osm_import")
def osm_import_action():
    name_regex = request.form.get("name_regex", "").strip()
    chain_id = request.form.get("chainId", "").strip()
    exclude = [w.strip() for w in request.form.get("exclude", "").split(",") if w.strip()]
    if not name_regex or not chain_id:
        return "Missing name_regex or chainId", 400

    els = _overpass_query(name_regex)
    now = datetime.now(timezone.utc).isoformat()

    def ok_name(name: str) -> bool:
        if not name:
            return False
        for w in exclude:
            if w in name:
                return False
        return True

    def row_from_osm(e: dict) -> dict | None:
        t = e.get("type"); eid = e.get("id")
        tags = e.get("tags", {})
        name = tags.get("name", "").strip()
        branch = tags.get("branch")
        if branch and branch not in name:
            name = f"{name} {branch}"
        if not ok_name(name):
            return None
        if t == "node":
            lat = e.get("lat"); lon = e.get("lon")
        else:
            c = e.get("center") or {}
            lat = c.get("lat"); lon = c.get("lon")
        if lat is None or lon is None:
            return None
        sid = f"store-{chain_id.split('-',1)[-1]}-osm-{t}-{eid}"
        return {
            "id": sid,
            "chainId": chain_id,
            "name": name,
            "address": "",
            "lat": str(lat),
            "lng": str(lon),
            "tags": "",
            "updatedAt": now,
        }

    rows = [r for r in (row_from_osm(e) for e in els) if r]

    # de-duplicate by id against existing stores
    stores_path = DATA / "stores.csv"
    stores = read_csv(stores_path)
    existing_ids = {r.get("id") for r in stores}
    new_rows = [r for r in rows if r["id"] not in existing_ids]

    if not new_rows:
        return (
            f"<p>No new stores found for pattern: {html.escape(name_regex)}</p>"
            f"<p><a href='{html.escape(url_for('osm_import_form'))}'>Back</a></p>"
        )

    # Append and write back with header
    fieldnames = ["id", "chainId", "name", "address", "lat", "lng", "tags", "updatedAt"]
    stores.extend(new_rows)
    write_csv(stores_path, stores, fieldnames)

    return (
        f"<p>Imported {len(new_rows)} stores. </p>"
        f"<p><a href='{html.escape(url_for('osm_import_form'))}'>Back</a></p>"
    )


if __name__ == "__main__":
    # Development server
    app.run(debug=True)

