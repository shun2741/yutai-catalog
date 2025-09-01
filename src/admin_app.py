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
        <a href="$stores_osm">Stores (OSM)</a>
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
        "  </div>"
        "  <div class='panel'>"
        "    <h2>Chains</h2>"
        f"    <p><b>{len(chs)}</b> chains registered</p>"
        f"    <p><a class='btn' href='{html.escape(url_for('list_chains'))}'>Manage Chains</a></p>"
        "  </div>"
        "</div>"
        "<div class='panel' style='margin-top:16px'>"
        "  <h2>Stores (experimental)</h2>"
        f"  <p><b>{len(stores)}</b> stores. Import from OSM by name pattern.</p>"
        f"  <p><a class='btn secondary' href='{html.escape(url_for('osm_import_form'))}'>OSM Import</a></p>"
        "</div>"
    )
    return page("Dashboard", body)


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
        return "Missing name", 400
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
        return "Missing displayName", 400
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
        "<div class='actions'><button class='btn' type='submit' name='action' value='preview'>Search & Preview</button></div>"
        "</form>"
        "</div>"
    )
    return page("OSM Import", body)


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
    if not name_regex or not chain_id:
        return page("Error", "<div class='panel'><p>Missing name_regex or chainId</p></div>"), 400

    els = _overpass_query(name_regex)
    now = datetime.now(timezone.utc).isoformat()
    rows = [r for r in (row_from_osm_element(e, chain_id, exclude, now) for e in els) if r]

    stores = read_csv(DATA / "stores.csv")
    existing_ids = {r.get("id") for r in stores}
    new_rows = [r for r in rows if r["id"] not in existing_ids]
    dup_count = len(rows) - len(new_rows)

    if not rows:
        return page("OSM Import", "<div class='panel'><p>一致する候補が見つかりませんでした。</p></div>")

    # Build preview table
    th = "".join(f"<th>{html.escape(h)}</th>" for h in ["Select", "id", "name", "lat", "lng"])
    trs = []
    for r in new_rows:
        cb = f"<input type='checkbox' name='sel' value='{html.escape(r['_sel'])}' checked>"
        cells = [cb, r["id"], r["name"], r["lat"], r["lng"]]
        tds = "".join(f"<td>{html.escape(c)}</td>" for c in cells)
        trs.append(f"<tr>{tds}</tr>")
    info = (
        f"<p><b>{len(rows)}</b> candidates found. "
        f"<b>{len(new_rows)}</b> new, <span class='help'>{dup_count} duplicates skipped.</span></p>"
    )
    form = (
        "<div class='panel'>"
        f"<h2>Preview: {html.escape(name_regex)}</h2>"
        + info +
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
        f"<p><a class='btn secondary' href='{html.escape(url_for('osm_import_form'))}'>Back</a></p>"
        "</div>"
    )
    return page("OSM Import Done", body)


if __name__ == "__main__":
    # Development server
    app.run(debug=True)
