from __future__ import annotations
import csv
import html
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict

from flask import Flask, request, redirect, url_for
import subprocess
import re


# Repository root (admin_app.py is at repo/src)
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


app = Flask(__name__)


ALLOWED_VOUCHER_TYPES = ["食事", "買い物", "レジャー", "その他"]

# --- UI Layout ---
from string import Template

HTML_BASE_TMPL = Template("""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>$title</title>
  <style>
    :root{--bg:#0b1020;--panel:#121a33;--text:#e8ebf1;--muted:#9aa4c7;--accent:#4f7cff;--ok:#2ecc71;--warn:#f39c12;--bad:#e74c3c;}
    html,body{margin:0;padding:0;background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,'Helvetica Neue',Arial,'Noto Sans',sans-serif;}
    a{color:var(--accent);text-decoration:none}
    a:hover{text-decoration:underline}
    .wrap{max-width:1100px;margin:0 auto;padding:24px}
    header{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px}
    nav a{margin-right:12px}
    .panel{background:var(--panel);border-radius:10px;padding:16px 18px;box-shadow:0 1px 0 rgba(255,255,255,0.06) inset}
    h1{font-size:22px;margin:0}
    h2{font-size:18px;margin:12px 0}
    .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
    table{width:100%;border-collapse:collapse}
    th,td{padding:10px 8px;border-bottom:1px solid rgba(255,255,255,0.08)}
    th{color:var(--muted);text-align:left;font-weight:600}
    tr:hover{background:rgba(255,255,255,0.03)}
    .btn{display:inline-block;background:var(--accent);color:white;padding:8px 12px;border-radius:8px;border:0}
    .btn.secondary{background:transparent;color:var(--accent);border:1px solid var(--accent)}
    .btn.danger{background:var(--bad)}
    .row{margin:10px 0}
    input[type=text], input[type=url], input[type=number] {width:100%;padding:8px 10px;border-radius:8px;border:1px solid rgba(255,255,255,0.15);background:#0c1327;color:var(--text)}
    .help{color:var(--muted);font-size:12px}
    form .actions{margin-top:14px}
  </style>
  <script>
    function confirmDelete(){ return confirm('Are you sure you want to delete this item?'); }
  </script>
  </head>
<body>
  <div class="wrap">
    <header>
      <h1>Yutai Catalog Admin</h1>
      <nav>
        <a href="$root">Dashboard</a>
        <a href="$companies">Companies</a>
        <a href="$chains">Chains</a>
        <a href="/stores">Stores</a>
        <a href="$stores_osm">Stores (OSM)</a>
        <a href="/ops">Ops</a>
      </nav>
    </header>
    $body
  </div>
</body>
</html>
""")


def page(title: str, body_html: str) -> str:
    return HTML_BASE_TMPL.safe_substitute(
        title=html.escape(title),
        root=html.escape(url_for("index")),
        companies=html.escape(url_for("list_companies")),
        chains=html.escape(url_for("list_chains")),
        stores_osm=html.escape(url_for("osm_import_form")),
        body=body_html,
    )


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


def update_row_csv(path: Path, row_id: str, updates: Dict[str, str], fieldnames: List[str]) -> bool:
    rows = read_csv(path)
    changed = False
    for r in rows:
        if r.get("id") == row_id:
            r.update(updates)
            changed = True
            break
    if changed:
        write_csv(path, rows, fieldnames)
    return changed


def delete_row_csv(path: Path, row_id: str, fieldnames: List[str]) -> bool:
    rows = read_csv(path)
    new_rows = [r for r in rows if r.get("id") != row_id]
    if len(new_rows) == len(rows):
        return False
    write_csv(path, new_rows, fieldnames)
    return True

# ---- Validation helpers ----
ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-_:]*$")


def validate_id(kind: str, value: str) -> str | None:
    if not value:
        return f"{kind} ID が空です"
    if not ID_RE.match(value):
        return f"{kind} ID は英小文字/数字/-/_/: のみ使用可能です"
    return None


def validate_lat_lng(lat: str, lng: str) -> str | None:
    try:
        la = float(lat)
        lo = float(lng)
    except Exception:
        return "緯度/経度は数値で入力してください"
    if not (-90 <= la <= 90 and -180 <= lo <= 180):
        return "緯度/経度の範囲が不正です"
    return None


def error_panel(msg: str, back_href: str) -> str:
    return page("Error", f"<div class='panel'><p>{html.escape(msg)}</p><p><a class='btn secondary' href='{html.escape(back_href)}'>Back</a></p></div>")


@app.get("/")
def index():
    comps = read_csv(DATA / "companies.csv")
    chs = read_csv(DATA / "chains.csv")
    stores = read_csv(DATA / "stores.csv")
    body = (
        "<div class='grid'>"
        "  <div class='panel'>"
        "    <h2>Companies</h2>"
        f"    <p><b>{len(comps)}</b> companies registered</p>"
        f"    <p><a class='btn' href='{html.escape(url_for('list_companies'))}'>Manage Companies</a></p>"
        "    <form method='post' action='/companies/delete' onsubmit='return confirmDelete()' style='margin-top:8px'>"
        "      <div class='row'>Quick Delete by ID<br>"
        "        <input name='id' placeholder='comp-xxxx' required style='max-width:260px'>"
        "      </div>"
        "      <div class='actions'><button class='btn danger' type='submit'>Delete Company</button></div>"
        "    </form>"
        "  </div>"
        "  <div class='panel'>"
        "    <h2>Chains</h2>"
        f"    <p><b>{len(chs)}</b> chains registered</p>"
        f"    <p><a class='btn' href='{html.escape(url_for('list_chains'))}'>Manage Chains</a></p>"
        "    <form method='post' action='/chains/delete' onsubmit='return confirmDelete()' style='margin-top:8px'>"
        "      <div class='row'>Quick Delete by ID<br>"
        "        <input name='id' placeholder='chain-xxxx' required style='max-width:260px'>"
        "      </div>"
        "      <div class='actions'><button class='btn danger' type='submit'>Delete Chain</button></div>"
        "    </form>"
        "  </div>"
        "</div>"
        "<div class='panel' style='margin-top:16px'>"
        "  <h2>Stores (experimental)</h2>"
        f"  <p><b>{len(stores)}</b> stores. Import from OSM by name pattern.</p>"
        f"  <p><a class='btn' href='/stores'>Manage Stores</a> "
        f"<a class='btn secondary' href='{html.escape(url_for('osm_import_form'))}'>OSM Import</a> "
        f"<a class='btn secondary' href='/ops'>Build & Deploy</a></p>"
        "</div>"
    )
    return page("Dashboard", body)


@app.post("/companies/delete")
def delete_company_quick():
    vid = (request.form.get("id") or "").strip()
    if not vid:
        return error_panel("ID が空です", url_for('index')), 400
    # reuse same safe check as list page
    chains = read_csv(DATA / "chains.csv")
    refs = [c for c in chains if vid in [s.strip() for s in (c.get("companyIds","") or "").split(",") if s.strip()]]
    if refs:
        msg = "この会社はチェーンから参照されています。先に chains.csv の companyIds から外してください。"
        return error_panel(msg, url_for('index')), 400
    ok = delete_row_csv(DATA / "companies.csv", vid, ["id", "name", "ticker", "chainIds", "voucherTypes", "notes"])
    if not ok:
        return error_panel("Company not found", url_for('index')), 404
    return redirect(url_for('index'))


@app.post("/chains/delete")
def delete_chain_quick():
    rid = (request.form.get("id") or "").strip()
    if not rid:
        return error_panel("ID が空です", url_for('index')), 400
    stores = read_csv(DATA / "stores.csv")
    refs = [s for s in stores if s.get("chainId") == rid]
    if refs:
        msg = "このチェーンには店舗データが紐づいています。先に stores.csv の該当行を削除してください。"
        return error_panel(msg, url_for('index')), 400
    ok = delete_row_csv(DATA / "chains.csv", rid, ["id", "displayName", "category", "companyIds", "voucherTypes", "tags", "url"])
    if not ok:
        return error_panel("Chain not found", url_for('index')), 404
    return redirect(url_for('index'))


# ---- Stores: list/search/edit/delete ----


@app.get("/stores")
def list_stores():
    rows = read_csv(DATA / "stores.csv")
    rows = sorted(rows, key=lambda r: r.get("id", ""))
    q = (request.args.get("q") or "").strip()
    chain = (request.args.get("chainId") or "").strip()
    if q:
        qq = q.lower()
        rows = [r for r in rows if qq in (r.get("id","")+" "+r.get("name","")+" "+r.get("address","")) .lower()]
    if chain:
        rows = [r for r in rows if r.get("chainId") == chain]
    chains = read_csv(DATA / "chains.csv")
    chain_opts = "<option value=''>All chains</option>" + "".join(
        f"<option value='{html.escape(c['id'])}' {'selected' if c['id']==chain else ''}>{html.escape(c['id'])} : {html.escape(c.get('displayName',''))}</option>"
        for c in sorted(chains, key=lambda x: x.get('id','')) if c.get('id')
    )
    head = (
        "<div class='panel'><h2>Stores</h2>"
        "<form method='get' style='margin:8px 0; display:flex; gap:8px; align-items:center'>"
        f"<input type='text' name='q' placeholder='Search id/name/address' value='{html.escape(q)}' style='flex:1'>"
        f"<select name='chainId' style='padding:8px 10px;border-radius:8px;border:1px solid rgba(255,255,255,0.15);background:#0c1327;color:#e8ebf1'>{chain_opts}</select>"
        "<button class='btn secondary' type='submit'>Search</button>"
        "<a class='btn secondary' href='/stores'>Clear</a>"
        "</form>"
    )
    if not rows:
        return page("Stores", head + "<p>No stores yet.</p></div>")
    th = "".join(f"<th>{html.escape(h)}</th>" for h in ["id","chainId","name","lat","lng","updatedAt"]) + "<th></th>"
    trs = []
    for r in rows[:2000]:  # cap rendering
        actions = (
            f"<a class='btn secondary' href='/stores/{html.escape(r.get('id',''))}/edit'>Edit</a> "
            f"<form method='post' action='/stores/{html.escape(r.get('id',''))}/delete' style='display:inline' onsubmit='return confirmDelete()'>"
            "<button class='btn danger' type='submit'>Delete</button></form>"
        )
        cells = [r.get("id",""), r.get("chainId",""), r.get("name",""), r.get("lat",""), r.get("lng",""), r.get("updatedAt",""), actions]
        trs.append("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in cells) + "</tr>")
    table = f"<table><tr>{th}</tr>{''.join(trs)}</table></div>"
    return page("Stores", head + table)


@app.get("/stores/<sid>/edit")
def edit_store(sid: str):
    rows = read_csv(DATA / "stores.csv")
    rec = next((r for r in rows if r.get("id") == sid), None)
    if not rec:
        return error_panel("Store not found", url_for('list_stores')), 404
    chains = read_csv(DATA / "chains.csv")
    opt = "".join(
        f"<option value='{html.escape(c['id'])}' {'selected' if c['id']==rec.get('chainId') else ''}>{html.escape(c['id'])} : {html.escape(c.get('displayName',''))}</option>"
        for c in sorted(chains, key=lambda x: x.get('id','')) if c.get('id')
    )
    form = (
        f"<div class='panel'><h2>Edit Store: {html.escape(sid)}</h2>"
        f"<form method='post' action='/stores/{html.escape(sid)}/edit'>"
        f"<div class='row'>ID<br><input value='{html.escape(sid)}' disabled></div>"
        f"<div class='row'>Chain<br><select name='chainId' required style='width:100%;padding:8px 10px;border-radius:8px;border:1px solid rgba(255,255,255,0.15);background:#0c1327;color:#e8ebf1'>{opt}</select></div>"
        f"<div class='row'>Name<br><input name='name' required value='{html.escape(rec.get('name',''))}'></div>"
        f"<div class='row'>Address<br><input name='address' value='{html.escape(rec.get('address',''))}'></div>"
        f"<div class='row'>Lat<br><input name='lat' value='{html.escape(rec.get('lat',''))}'></div>"
        f"<div class='row'>Lng<br><input name='lng' value='{html.escape(rec.get('lng',''))}'></div>"
        f"<div class='row'>Tags<br><input name='tags' value='{html.escape(rec.get('tags',''))}'></div>"
        f"<div class='row'>UpdatedAt<br><input name='updatedAt' value='{html.escape(rec.get('updatedAt',''))}'></div>"
        "<div class='actions'><button class='btn' type='submit'>Save</button> <a class='btn secondary' href='/stores'>Cancel</a></div>"
        "</form></div>"
    )
    return page("Edit Store", form)


@app.post("/stores/<sid>/edit")
def update_store(sid: str):
    chain_id = request.form.get("chainId","" ).strip()
    name = request.form.get("name", "").strip()
    address = request.form.get("address", "").strip()
    lat = request.form.get("lat", "").strip()
    lng = request.form.get("lng", "").strip()
    tags = request.form.get("tags", "").strip()
    updated_at = request.form.get("updatedAt", "").strip() or datetime.now(timezone.utc).isoformat()
    if not (chain_id and name):
        return error_panel("Missing chainId or name", url_for('list_stores')), 400
    err = validate_lat_lng(lat, lng)
    if err:
        return error_panel(err, url_for('list_stores')), 400
    ok = update_row_csv(
        DATA / "stores.csv",
        sid,
        {
            "chainId": chain_id,
            "name": name,
            "address": address,
            "lat": lat,
            "lng": lng,
            "tags": tags,
            "updatedAt": updated_at,
        },
        ["id","chainId","name","address","lat","lng","tags","updatedAt"],
    )
    if not ok:
        return error_panel("Store not found", url_for('list_stores')), 404
    return redirect(url_for("list_stores"))


@app.post("/stores/<sid>/delete")
def delete_store(sid: str):
    ok = delete_row_csv(DATA / "stores.csv", sid, ["id","chainId","name","address","lat","lng","tags","updatedAt"])
    if not ok:
        return error_panel("Store not found", url_for('list_stores')), 404
    return redirect(url_for("list_stores"))


# Companies


@app.get("/companies")
def list_companies():
    rows = read_csv(DATA / "companies.csv")
    rows = sorted(rows, key=lambda r: r.get("id", ""))
    q = (request.args.get("q") or "").strip()
    if q:
        qq = q.lower()
        rows = [r for r in rows if qq in (r.get("id","")+" "+r.get("name","")+" "+r.get("ticker","")) .lower()]
    head = (
        "<div class='panel'><h2>Companies</h2>"
        "<form method='get' style='margin:8px 0'>"
        f"<input type='text' name='q' placeholder='Search id/name/ticker' value='{html.escape(q)}' style='max-width:320px'> "
        "<button class='btn secondary' type='submit'>Search</button> "
        "<a class='btn secondary' href='/companies'>Clear</a> "
        "<a class='btn' href='/companies/new' style='float:right'>Add company</a>"
        "</form>"
    )
    if not rows:
        return page("Companies", head + "<p>No companies yet.</p></div>")
    th = "".join(
        f"<th>{html.escape(h)}</th>"
        for h in ["id", "name", "ticker", "chainIds", "voucherTypes", "notes"]
    )
    trs = []
    for r in rows:
        del_form = (
            f"<form method='post' action='/companies/{html.escape(r.get('id',''))}/delete' style='display:inline' onsubmit='return confirmDelete()'>"
            "<button class='btn danger' type='submit'>Delete</button></form>"
        )
        actions = f"<a class='btn secondary' href='/companies/{html.escape(r.get('id',''))}/edit'>Edit</a> " + del_form
        cells = [r.get("id", ""), r.get("name", ""), r.get("ticker", ""), r.get("chainIds", ""), r.get("voucherTypes", ""), r.get("notes", ""), actions]
        tds = "".join(f"<td>{html.escape(c)}</td>" for c in cells)
        trs.append(f"<tr>{tds}</tr>")
    table = f"<table><tr>{th}<th></th></tr>{''.join(trs)}</table></div>"
    return page("Companies", head + table)


@app.get("/companies/new")
def new_company():
    opts = "".join(
        f"<label><input type='checkbox' name='voucherTypes' value='{html.escape(v)}'> {html.escape(v)}</label> "
        for v in ALLOWED_VOUCHER_TYPES
    )
    form = (
        "<div class='panel'><h2>Add Company</h2>"
        "<form method='post' action='/companies/new'>"
        "<div class='row'>ID<br><input name='id' required placeholder='comp-xxxx'></div>"
        "<div class='row'>Name<br><input name='name' required></div>"
        "<div class='row'>Ticker<br><input name='ticker' placeholder='(optional)'></div>"
        f"<div class='row'>Voucher Types<br>{opts}</div>"
        "<div class='row'>Notes<br><input name='notes' placeholder='(optional)'></div>"
        "<div class='actions'><button class='btn' type='submit'>Add</button> <a class='btn secondary' href='/companies'>Cancel</a></div>"
        "</form></div>"
    )
    return page("Add Company", form)


@app.post("/companies/new")
def create_company():
    vid = request.form.get("id", "").strip()
    name = request.form.get("name", "").strip()
    ticker = request.form.get("ticker", "").strip()
    vts = request.form.getlist("voucherTypes")
    notes = request.form.get("notes", "").strip()
    if not vid or not name:
        return error_panel("Missing id or name", url_for('list_companies')), 400
    err = validate_id("Company", vid)
    if err:
        return error_panel(err, url_for('list_companies')), 400
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
        return error_panel(str(e), url_for('list_companies')), 400
    return redirect(url_for("list_companies"))


# Chains


@app.get("/chains")
def list_chains():
    rows = read_csv(DATA / "chains.csv")
    rows = sorted(rows, key=lambda r: r.get("id", ""))
    q = (request.args.get("q") or "").strip()
    if q:
        qq = q.lower()
        rows = [r for r in rows if qq in (r.get("id","")+" "+r.get("displayName","")).lower()]
    head = (
        "<div class='panel'><h2>Chains</h2>"
        "<form method='get' style='margin:8px 0'>"
        f"<input type='text' name='q' placeholder='Search id/name' value='{html.escape(q)}' style='max-width:320px'> "
        "<button class='btn secondary' type='submit'>Search</button> "
        "<a class='btn secondary' href='/chains'>Clear</a> "
        "<a class='btn' href='/chains/new' style='float:right'>Add chain</a>"
        "</form>"
    )
    if not rows:
        return page("Chains", head + "<p>No chains yet.</p></div>")
    th = "".join(
        f"<th>{html.escape(h)}</th>"
        for h in ["id", "displayName", "category", "companyIds", "voucherTypes", "tags", "url"]
    )
    comps = {c.get("id"): c.get("name", "") for c in read_csv(DATA / "companies.csv")}
    trs = []
    for r in rows:
        comp_ids = [s.strip() for s in r.get("companyIds", "").split(",") if s.strip()]
        comp_labels = ", ".join(filter(None, [comps.get(cid, cid) for cid in comp_ids]))
        del_form = (
            f"<form method='post' action='/chains/{html.escape(r.get('id',''))}/delete' style='display:inline' onsubmit='return confirmDelete()'>"
            "<button class='btn danger' type='submit'>Delete</button></form>"
        )
        actions = f"<a class='btn secondary' href='/chains/{html.escape(r.get('id',''))}/edit'>Edit</a> " + del_form
        cells = [r.get("id", ""), r.get("displayName", ""), r.get("category", ""), comp_labels, r.get("voucherTypes", ""), r.get("tags", ""), r.get("url", ""), actions]
        trs.append("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in cells) + "</tr>")
    table = f"<table><tr>{th}<th></th></tr>{''.join(trs)}</table></div>"
    return page("Chains", head + table)


@app.get("/chains/new")
def new_chain():
    # Suggest existing companyIds for convenience
    comps = read_csv(DATA / "companies.csv")
    comp_ids = ",".join(sorted([c.get("id", "") for c in comps if c.get("id")]))
    vt_opts = "".join(
        f"<label><input type='checkbox' name='voucherTypes' value='{html.escape(v)}'> {html.escape(v)}</label> "
        for v in ALLOWED_VOUCHER_TYPES
    )
    form = (
        "<div class='panel'><h2>Add Chain</h2>"
        "<form method='post' action='/chains/new'>"
        "<div class='row'>ID<br><input name='id' required placeholder='chain-xxxx'></div>"
        "<div class='row'>Display Name<br><input name='displayName' required></div>"
        "<div class='row'>Category<br><input name='category' value='飲食'></div>"
        f"<div class='row'>Company IDs<br><input name='companyIds' placeholder='comp-... (comma separated)'><div class='help'>existing: {html.escape(comp_ids)}</div></div>"
        f"<div class='row'>Voucher Types<br>{vt_opts}</div>"
        "<div class='row'>Tags<br><input name='tags' placeholder='comma separated'></div>"
        "<div class='row'>URL<br><input name='url' placeholder='https://...'></div>"
        "<div class='actions'><button class='btn' type='submit'>Add</button> <a class='btn secondary' href='/chains'>Cancel</a></div>"
        "</form></div>"
    )
    return page("Add Chain", form)


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
        return error_panel("Missing id or displayName", url_for('list_chains')), 400
    err = validate_id("Chain", rid)
    if err:
        return error_panel(err, url_for('list_chains')), 400
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
        return error_panel(str(e), url_for('list_chains')), 400
    return redirect(url_for("list_chains"))


@app.post("/companies/<vid>/delete")
def delete_company(vid: str):
    # Do not allow delete if referenced by any chain
    chains = read_csv(DATA / "chains.csv")
    refs = [c for c in chains if vid in [s.strip() for s in (c.get("companyIds","") or "").split(",") if s.strip()]]
    if refs:
        msg = "この会社はチェーンから参照されています。先に chains.csv の companyIds から外してください。"
        return page("Blocked", f"<div class='panel'><p>{html.escape(msg)}</p><p><a class='btn secondary' href='/companies'>Back</a></p></div>"), 400
    ok = delete_row_csv(DATA / "companies.csv", vid, ["id", "name", "ticker", "chainIds", "voucherTypes", "notes"])
    if not ok:
        return page("Not Found", f"<div class='panel'><p>Company not found: {html.escape(vid)}</p></div>"), 404
    return redirect(url_for("list_companies"))


@app.post("/chains/<rid>/delete")
def delete_chain(rid: str):
    # Do not allow delete if referenced by any store
    stores = read_csv(DATA / "stores.csv")
    refs = [s for s in stores if s.get("chainId") == rid]
    if refs:
        msg = "このチェーンには店舗データが紐づいています。先に stores.csv の該当行を削除してください。"
        return page("Blocked", f"<div class='panel'><p>{html.escape(msg)}</p><p><a class='btn secondary' href='/chains'>Back</a></p></div>"), 400
    ok = delete_row_csv(DATA / "chains.csv", rid, ["id", "displayName", "category", "companyIds", "voucherTypes", "tags", "url"])
    if not ok:
        return page("Not Found", f"<div class='panel'><p>Chain not found: {html.escape(rid)}</p></div>"), 404
    return redirect(url_for("list_chains"))


# --- Edit forms ---


@app.get("/companies/<vid>/edit")
def edit_company(vid: str):
    rows = read_csv(DATA / "companies.csv")
    rec = next((r for r in rows if r.get("id") == vid), None)
    if not rec:
        return page("Not Found", f"<p class='panel'>Company not found: {html.escape(vid)}</p>"), 404
    vts = rec.get("voucherTypes", "").split(",") if rec.get("voucherTypes") else []
    opts = "".join(
        f"<label style='margin-right:8px'><input type='checkbox' name='voucherTypes' value='{html.escape(v)}' {'checked' if v in vts else ''}> {html.escape(v)}</label>"
        for v in ALLOWED_VOUCHER_TYPES
    )
    form = (
        f"<div class='panel'><h2>Edit Company: {html.escape(vid)}</h2>"
        f"<form method='post' action='/companies/{html.escape(vid)}/edit'>"
        f"<div class='row'>ID<br><input value='{html.escape(vid)}' disabled><input type='hidden' name='id' value='{html.escape(vid)}'></div>"
        f"<div class='row'>Name<br><input name='name' value='{html.escape(rec.get('name',''))}' required></div>"
        f"<div class='row'>Ticker<br><input name='ticker' value='{html.escape(rec.get('ticker',''))}'></div>"
        f"<div class='row'>Voucher Types<br>{opts}</div>"
        f"<div class='row'>Notes<br><input name='notes' value='{html.escape(rec.get('notes',''))}'></div>"
        "<div class='help'>chainIds はビルドで自動付与されます（編集不要）。</div>"
        "<div class='actions'><button class='btn' type='submit'>Save</button> <a class='btn secondary' href='/companies'>Cancel</a></div>"
        "</form></div>"
    )
    return page(f"Edit {vid}", form)


@app.post("/companies/<vid>/edit")
def update_company(vid: str):
    name = request.form.get("name", "").strip()
    ticker = request.form.get("ticker", "").strip()
    vts = request.form.getlist("voucherTypes")
    notes = request.form.get("notes", "").strip()
    if not name:
        return error_panel("Missing name", url_for('list_companies')), 400
    ok = update_row_csv(
        DATA / "companies.csv",
        vid,
        {
            "name": name,
            "ticker": ticker,
            "voucherTypes": ",".join(vts),
            "notes": notes,
        },
        ["id", "name", "ticker", "chainIds", "voucherTypes", "notes"],
    )
    if not ok:
        return page("Not Found", f"<p class='panel'>Company not found: {html.escape(vid)}</p>"), 404
    return redirect(url_for("list_companies"))


@app.get("/chains/<rid>/edit")
def edit_chain(rid: str):
    rows = read_csv(DATA / "chains.csv")
    rec = next((r for r in rows if r.get("id") == rid), None)
    if not rec:
        return page("Not Found", f"<p class='panel'>Chain not found: {html.escape(rid)}</p>"), 404
    comps = read_csv(DATA / "companies.csv")
    comp_ids = [c.get("id") for c in comps if c.get("id")]
    selected_comp_ids = set([s.strip() for s in rec.get("companyIds", "").split(",") if s.strip()])
    comp_checks = "".join(
        f"<label style='margin-right:8px'><input type='checkbox' name='companyIds' value='{html.escape(cid)}' {'checked' if cid in selected_comp_ids else ''}> {html.escape(cid)}</label>"
        for cid in comp_ids
    )
    vts = rec.get("voucherTypes", "").split(",") if rec.get("voucherTypes") else []
    vt_opts = "".join(
        f"<label style='margin-right:8px'><input type='checkbox' name='voucherTypes' value='{html.escape(v)}' {'checked' if v in vts else ''}> {html.escape(v)}</label>"
        for v in ALLOWED_VOUCHER_TYPES
    )
    form = (
        f"<div class='panel'><h2>Edit Chain: {html.escape(rid)}</h2>"
        f"<form method='post' action='/chains/{html.escape(rid)}/edit'>"
        f"<div class='row'>ID<br><input value='{html.escape(rid)}' disabled><input type='hidden' name='id' value='{html.escape(rid)}'></div>"
        f"<div class='row'>Display Name<br><input name='displayName' value='{html.escape(rec.get('displayName',''))}' required></div>"
        f"<div class='row'>Category<br><input name='category' value='{html.escape(rec.get('category','')) or 'その他'}'></div>"
        f"<div class='row'>Company IDs<br>{comp_checks}</div>"
        f"<div class='row'>Voucher Types<br>{vt_opts}</div>"
        f"<div class='row'>Tags<br><input name='tags' value='{html.escape(rec.get('tags',''))}'></div>"
        f"<div class='row'>URL<br><input name='url' value='{html.escape(rec.get('url',''))}'></div>"
        "<div class='actions'><button class='btn' type='submit'>Save</button> <a class='btn secondary' href='/chains'>Cancel</a></div>"
        "</form></div>"
    )
    return page(f"Edit {rid}", form)


@app.post("/chains/<rid>/edit")
def update_chain(rid: str):
    display = request.form.get("displayName", "").strip()
    category = request.form.get("category", "").strip() or "その他"
    comp_ids = request.form.getlist("companyIds")
    vts = request.form.getlist("voucherTypes")
    tags = request.form.get("tags", "").strip()
    url = request.form.get("url", "").strip()
    if not display:
        return error_panel("Missing displayName", url_for('list_chains')), 400
    ok = update_row_csv(
        DATA / "chains.csv",
        rid,
        {
            "displayName": display,
            "category": category,
            "companyIds": ",".join(comp_ids),
            "voucherTypes": ",".join(vts),
            "tags": tags,
            "url": url,
        },
        ["id", "displayName", "category", "companyIds", "voucherTypes", "tags", "url"],
    )
    if not ok:
        return page("Not Found", f"<p class='panel'>Chain not found: {html.escape(rid)}</p>"), 404
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
    body = (
        "<div class='panel'>"
        "<h2>OSM Import (experimental)</h2>"
        "<form method='post' action='/stores/osm_import'>"
        "<div class='row'>Name Regex<br><input name='name_regex' value='ステーキ宮' required></div>"
        f"<div class='row'>Assign chainId<br><select name='chainId' required style='width:100%;padding:8px 10px;border-radius:8px;border:1px solid rgba(255,255,255,0.15);background:#0c1327;color:#e8ebf1'>{chain_opts}</select></div>"
        "<div class='row'>Exclude words (comma)<br><input name='exclude' value='駐車場,宮川'></div>"
        "<div class='row'>Overpass endpoint<br>"
        "<select name='endpoint' style='width:100%;padding:8px 10px;border-radius:8px;border:1px solid rgba(255,255,255,0.15);background:#0c1327;color:#e8ebf1'>"
        "<option value='auto' selected>Auto (try multiple)</option>"
        "<option value='https://overpass-api.de/api/interpreter'>overpass-api.de</option>"
        "<option value='https://z.overpass-api.de/api/interpreter'>z.overpass-api.de</option>"
        "<option value='https://overpass.kumi.systems/api/interpreter'>overpass.kumi.systems</option>"
        "</select></div>"
        "<div class='row'>Timeout (sec)<br><input name='timeout' type='number' value='120'></div>"
        "<div class='actions'><button class='btn' type='submit' name='action' value='preview'>Search & Preview</button></div>"
        "</form>"
        "</div>"
    )
    return page("OSM Import", body)


def _overpass_query(name_regex: str, timeout_sec: int = 120, endpoint: str = "auto") -> List[dict]:
    q = (
        f"[out:json][timeout:{int(timeout_sec)}];"
        f"area[\"name:ja\"=\"日本\"][admin_level=2];"
        f"(node[\"name\"~\"{name_regex}\"](area);"
        f" way[\"name\"~\"{name_regex}\"](area);"
        f" relation[\"name\"~\"{name_regex}\"](area););"
        f"out center tags;"
    )
    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://z.overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]
    tries = [endpoint] if endpoint and endpoint != "auto" else endpoints
    last_err = None
    for ep in tries:
        try:
            url = ep + "?data=" + urllib.parse.quote(q)
            with urllib.request.urlopen(url, timeout=timeout_sec + 15) as r:
                data = r.read()
            obj = __import__("json").loads(data)
            return obj.get("elements", [])
        except Exception as e:
            last_err = e
            continue
    raise last_err if last_err else RuntimeError("Overpass query failed")


def row_from_osm_element(e: dict, chain_id: str, exclude: List[str], now: str) -> dict | None:
    def ok_name(name: str) -> bool:
        if not name:
            return False
        for w in exclude:
            if w and w in name:
                return False
        return True
    t = e.get("type"); eid = e.get("id")
    tags = e.get("tags", {})
    name = (tags.get("name", "") or "").strip()
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
        "_sel": f"{t}-{eid}",
    }


@app.post("/stores/osm_import")
def osm_import_action():
    name_regex = request.form.get("name_regex", "").strip()
    chain_id = request.form.get("chainId", "").strip()
    exclude = [w.strip() for w in request.form.get("exclude", "").split(",") if w.strip()]
    endpoint = request.form.get("endpoint", "auto").strip() or "auto"
    try:
        timeout_sec = int(request.form.get("timeout", "120"))
    except Exception:
        timeout_sec = 120
    if not name_regex or not chain_id:
        return page("Error", "<div class='panel'><p>Missing name_regex or chainId</p></div>"), 400
    try:
        els = _overpass_query(name_regex, timeout_sec=timeout_sec, endpoint=endpoint)
    except Exception as e:
        msg = f"Overpass API error: {str(e)}. エンドポイントやタイムアウトを変更して再試行してください。"
        return page("Overpass Error", f"<div class='panel'><p>{html.escape(msg)}</p></div>"), 502
    now = datetime.now(timezone.utc).isoformat()
    rows = [r for r in (row_from_osm_element(e, chain_id, exclude, now) for e in els) if r]

    stores = read_csv(DATA / "stores.csv")
    existing_ids = {r.get("id") for r in stores}
    new_rows = [r for r in rows if r["id"] not in existing_ids]
    dup_count = len(rows) - len(new_rows)

    if not rows:
        return page("OSM Import", "<div class='panel'><p>一致する候補が見つかりませんでした。</p></div>")

    # Build preview table + map
    th = "".join(f"<th>{html.escape(h)}</th>" for h in ["Select", "id", "name", "lat", "lng"])
    trs = []
    for r in new_rows:
        cb = f"<input type='checkbox' name='sel' value='{html.escape(r['_sel'])}' checked>"
        text_cells = [str(r["id"]), str(r["name"]), str(r["lat"]), str(r["lng"])]
        tds = "<td>" + cb + "</td>" + "".join(f"<td>{html.escape(c)}</td>" for c in text_cells)
        trs.append(f"<tr>{tds}</tr>")
    info = (
        f"<p><b>{len(rows)}</b> candidates found. "
        f"<b>{len(new_rows)}</b> new, <span class='help'>{dup_count} duplicates skipped.</span></p>"
    )
    # Leaflet assets
    leaflet = (
        "<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css' crossorigin=''/>"
        "<script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js' crossorigin=''></script>"
    )
    # JS markers array
    import json as _json
    markers = _json.dumps([
        {"name": r["name"], "lat": float(r["lat"]), "lng": float(r["lng"])} for r in new_rows
    ], ensure_ascii=False)
    map_div = "<div id='map' style='height:420px;margin:10px 0;border-radius:8px;'></div>"
    map_js = f"""
    <script>
      (function(){{
        var markers = {markers};
        var map = L.map('map');
        var tiles = L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ maxZoom: 19, attribution: '&copy; OpenStreetMap' }});
        tiles.addTo(map);
        var group = L.featureGroup();
        markers.forEach(function(m){{
          var mk = L.marker([m.lat, m.lng]).bindPopup(m.name);
          mk.addTo(group);
        }});
        group.addTo(map);
        try {{ map.fitBounds(group.getBounds().pad(0.2)); }} catch(e) {{ map.setView([35.0,135.0], 5); }}
      }})();
    </script>
    """.replace('{markers}', html.escape(markers))

    form = (
        "<div class='panel'>"
        f"<h2>Preview: {html.escape(name_regex)}</h2>"
        + info +
        leaflet +
        map_div +
        map_js +
        "<form method='post' action='/stores/osm_import/commit'>"
        f"<input type='hidden' name='name_regex' value='{html.escape(name_regex)}'>"
        f"<input type='hidden' name='chainId' value='{html.escape(chain_id)}'>"
        f"<input type='hidden' name='exclude' value='{html.escape(','.join(exclude))}'>"
        f"<table><tr>{th}</tr>{''.join(trs)}</table>"
        "<div class='actions'><button class='btn' type='submit'>Import Selected</button> "
        f"<a class='btn secondary' href='{html.escape(url_for('osm_import_form'))}'>Back</a></div>"
        "</form>"
        "</div>"
    )
    return page("OSM Import Preview", form)


@app.post("/stores/osm_import/commit")
def osm_import_commit():
    name_regex = request.form.get("name_regex", "").strip()
    chain_id = request.form.get("chainId", "").strip()
    exclude = [w.strip() for w in request.form.get("exclude", "").split(",") if w.strip()]
    sels = request.form.getlist("sel")
    if not (name_regex and chain_id and sels):
        return page("Error", "<div class='panel'><p>Missing parameters or no selection.</p></div>"), 400
    els = _overpass_query(name_regex)
    now = datetime.now(timezone.utc).isoformat()
    # map sel key to element
    idx = {f"{e.get('type')}-{e.get('id')}": e for e in els}
    chosen = [idx[s] for s in sels if s in idx]
    rows = [r for r in (row_from_osm_element(e, chain_id, exclude, now) for e in chosen) if r]
    stores_path = DATA / "stores.csv"
    stores = read_csv(stores_path)
    existing_ids = {r.get("id") for r in stores}
    new_rows = [r for r in rows if r["id"] not in existing_ids]
    fieldnames = ["id", "chainId", "name", "address", "lat", "lng", "tags", "updatedAt"]
    if new_rows:
        stores.extend(new_rows)
    write_csv(stores_path, stores, fieldnames)
    body = (
        "<div class='panel'>"
        f"<p>Imported <b>{len(new_rows)}</b> stores (selected: {len(sels)}).</p>"
        f"<p><a class='btn secondary' href='{html.escape(url_for('osm_import_form'))}'>Import more</a> "
        f"<a class='btn' href='/stores'>Go to Stores</a></p>"
        "</div>"
    )
    return page("OSM Import Done", body)


# ---- Ops: Build / Commit / Push ----


def run_cmd(cmd: list[str], env: dict | None = None, cwd: str | None = None) -> tuple[int, str]:
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=cwd)
        out = (cp.stdout or "") + ("\n" + cp.stderr if cp.stderr else "")
        return cp.returncode, out
    except Exception as e:
        return 1, str(e)


@app.get("/ops")
def ops_page():
    body = (
        "<div class='panel'><h2>Build & Deploy</h2>"
        "<form method='post' action='/ops'>"
        "<div class='row'>Commit message<br><input name='msg' value='Admin build'></div>"
        "<div class='row'><label><input type='checkbox' name='do_build' checked> Build catalog</label></div>"
        "<div class='row'><label><input type='checkbox' name='do_commit' checked> Git commit</label></div>"
        "<div class='row'><label><input type='checkbox' name='do_push' checked> Git push</label></div>"
        "<div class='actions'><button class='btn' type='submit'>Run</button> <a class='btn secondary' href='/'>Cancel</a></div>"
        "</form></div>"
    )
    return page("Ops", body)


@app.post("/ops")
def ops_run():
    do_build = request.form.get("do_build") is not None
    do_commit = request.form.get("do_commit") is not None
    do_push = request.form.get("do_push") is not None
    msg = request.form.get("msg", "Admin build").strip() or "Admin build"
    logs = []
    code = 0
    env = dict(**{k: v for k, v in dict(**{**__import__('os').environ}).items()})
    env["PYTHONPATH"] = str((ROOT / "src").resolve())
    if do_build:
        c, out = run_cmd(["python", "-m", "pipeline.build"], env=env, cwd=str(ROOT))
        logs.append(f"$ python -m pipeline.build\n{html.escape(out)}")
        code |= c
    if do_commit:
        c1, o1 = run_cmd(["git", "add", "-A"], cwd=str(ROOT))
        c2, o2 = run_cmd(["git", "commit", "-m", msg], cwd=str(ROOT))
        logs.append(f"$ git add -A\n{html.escape(o1)}\n$ git commit -m '{html.escape(msg)}'\n{html.escape(o2)}")
        code |= (c1 or 0)
        code |= (c2 or 0)
    if do_push:
        c3, o3 = run_cmd(["git", "push", "origin", "main"], cwd=str(ROOT))
        logs.append(f"$ git push origin main\n{html.escape(o3)}")
        code |= (c3 or 0)
    pre = "<pre style='white-space:pre-wrap; background:#0c1327; padding:12px; border-radius:8px;'>" + "\n\n".join(logs) + "</pre>"
    status = "OK" if code == 0 else "Completed with errors"
    body = f"<div class='panel'><h2>Ops Result: {status}</h2>{pre}<p><a class='btn secondary' href='/ops'>Back</a></p></div>"
    return page("Ops Result", body)


if __name__ == "__main__":
    # Development server
    app.run(debug=True)
