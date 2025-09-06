from __future__ import annotations
import html
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from flask import Blueprint, request, redirect, url_for
from urllib.parse import quote

from .common import (
    DATA,
    read_csv,
    write_csv,
    update_row_csv,
    delete_row_csv,
    page,
)

bp = Blueprint("stores", __name__)


@bp.get("/stores")
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
        "<span style='margin-left:auto'>"
        "<a class='btn secondary' href='/stores/osm_import'>OSM import</a>"
        "</span>"
        "</form>"
    )
    if not rows:
        return page("Stores", head + "<p>No stores yet.</p></div>")
    th = "".join(f"<th>{html.escape(h)}</th>" for h in ["id","chainId","name","lat","lng","updatedAt"]) + "<th></th>"
    trs = []
    for r in rows[:2000]:
        actions = (
            f"<a class='btn secondary' href='/stores/{html.escape(r.get('id',''))}/edit'>Edit</a> "
            f"<form method='post' action='/stores/{html.escape(r.get('id',''))}/delete' style='display:inline' onsubmit='return confirmDelete()'>"
            "<button class='btn danger' type='submit'>Delete</button></form>"
        )
        data_cells = [r.get("id",""), r.get("chainId",""), r.get("name",""), r.get("lat",""), r.get("lng",""), r.get("updatedAt","")]
        encoded = quote(actions, safe='')
        row_html = "".join(f"<td>{html.escape(c)}</td>" for c in data_cells) + f"<td data-raw='{encoded}'></td>"
        trs.append("<tr>" + row_html + "</tr>")
    table = f"<table><tr>{th}</tr>{''.join(trs)}</table></div>"
    return page("Stores", html.unescape(head + table))


# (Scrape import removed by request)


@bp.get("/stores/<sid>/edit")
def edit_store(sid: str):
    rows = read_csv(DATA / "stores.csv")
    rec = next((r for r in rows if r.get("id") == sid), None)
    if not rec:
        return page("Error", "<div class='panel'><p>Store not found</p></div>"), 404
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


@bp.post("/stores/<sid>/edit")
def update_store(sid: str):
    chain_id = request.form.get("chainId","" ).strip()
    name = request.form.get("name", "").strip()
    address = request.form.get("address", "").strip()
    lat = request.form.get("lat", "").strip()
    lng = request.form.get("lng", "").strip()
    tags = request.form.get("tags", "").strip()
    updated_at = request.form.get("updatedAt", "").strip() or datetime.now(timezone.utc).isoformat()
    if not (chain_id and name):
        return page("Error", "<div class='panel'><p>Missing chainId or name</p></div>"), 400
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
        return page("Error", "<div class='panel'><p>Store not found</p></div>"), 404
    return redirect(url_for("stores.list_stores"))


@bp.post("/stores/<sid>/delete")
def delete_store(sid: str):
    ok = delete_row_csv(DATA / "stores.csv", sid, ["id","chainId","name","address","lat","lng","tags","updatedAt"])
    if not ok:
        return page("Error", "<div class='panel'><p>Store not found</p></div>"), 404
    return redirect(url_for("stores.list_stores"))


@bp.post("/stores/delete")
def delete_store_quick():
    sid = (request.form.get("id") or "").strip()
    if not sid:
        return page("Error", "<div class='panel'><p>ID が空です</p></div>"), 400
    ok = delete_row_csv(DATA / "stores.csv", sid, ["id","chainId","name","address","lat","lng","tags","updatedAt"])
    if not ok:
        return page("Error", "<div class='panel'><p>Store not found</p></div>"), 404
    return redirect(url_for('dashboard.index'))


@bp.post("/stores/edit_redirect")
def edit_store_redirect():
    sid = (request.form.get("id") or "").strip()
    if not sid:
        return page("Error", "<div class='panel'><p>ID が空です</p></div>"), 400
    rows = read_csv(DATA / "stores.csv")
    rec = next((r for r in rows if r.get("id") == sid), None)
    if not rec:
        return page("Error", "<div class='panel'><p>Store not found</p></div>"), 404
    return redirect(url_for('stores.edit_store', sid=sid))


def _overpass_query(name_regex: str, timeout_sec: int = 120, endpoint: str = "auto") -> list[dict]:
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


@bp.get("/stores/osm_import")
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


@bp.post("/stores/osm_import")
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
    def row_from_osm_element(e: dict) -> dict | None:
        t = e.get("type"); eid = e.get("id")
        tags = e.get("tags", {})
        name = (tags.get("name", "") or "").strip()
        branch = tags.get("branch")
        if branch and branch not in name:
            name = f"{name} {branch}"
        if not name:
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
    rows = [r for r in (row_from_osm_element(e) for e in els) if r]
    stores = read_csv(DATA / "stores.csv")
    existing_ids = {r.get("id") for r in stores}
    new_rows = [r for r in rows if r["id"] not in existing_ids]
    dup_count = len(rows) - len(new_rows)
    if not rows:
        return page("OSM Import", "<div class='panel'><p>一致する候補が見つかりませんでした。</p></div>")
    th = "".join(f"<th>{html.escape(h)}</th>" for h in ["Select", "id", "name", "lat", "lng"])
    trs = []
    for r in new_rows:
        cb = f"<input type='checkbox' name='sel' value='{html.escape(r['_sel'])}' checked>"
        text_cells = [str(r["id"]), str(r["name"]), str(r["lat"]), str(r["lng"])]
        tds = "<td>" + cb + "</td>" + "".join(f"<td>{html.escape(c)}</td>" for c in text_cells)
        trs.append(f"<tr>{tds}</tr>")
    import json as _json
    leaflet = (
        "<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css' crossorigin=''/>"
        "<script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js' crossorigin=''></script>"
    )
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
        f"<p><b>{len(rows)}</b> candidates found. <b>{len(new_rows)}</b> new, <span class='help'>{dup_count} duplicates skipped.</span></p>"
        + leaflet + map_div + map_js +
        "<form method='post' action='/stores/osm_import/commit'>"
        f"<input type='hidden' name='name_regex' value='{html.escape(name_regex)}'>"
        f"<input type='hidden' name='chainId' value='{html.escape(chain_id)}'>"
        f"<input type='hidden' name='exclude' value='{html.escape(','.join(exclude))}'>"
        f"<table><tr>{th}</tr>{''.join(trs)}</table>"
        "<div class='actions'><button class='btn' type='submit'>Import Selected</button> "
        f"<a class='btn secondary' href='{html.escape(url_for('stores.osm_import_form'))}'>Back</a></div>"
        "</form>"
        "</div>"
    )
    return page("OSM Import Preview", form)


@bp.post("/stores/osm_import/commit")
def osm_import_commit():
    name_regex = request.form.get("name_regex", "").strip()
    chain_id = request.form.get("chainId", "").strip()
    exclude = [w.strip() for w in request.form.get("exclude", "").split(",") if w.strip()]
    sels = request.form.getlist("sel")
    if not (name_regex and chain_id and sels):
        return page("Error", "<div class='panel'><p>Missing parameters or no selection.</p></div>"), 400
    els = _overpass_query(name_regex)
    now = datetime.now(timezone.utc).isoformat()
    idx = {f"{e.get('type')}-{e.get('id')}": e for e in els}
    def row_from_osm_element(e: dict) -> dict | None:
        t = e.get("type"); eid = e.get("id")
        tags = e.get("tags", {})
        name = (tags.get("name", "") or "").strip()
        if t == "node":
            lat = e.get("lat"); lon = e.get("lon")
        else:
            c = e.get("center") or {}
            lat = c.get("lat"); lon = c.get("lon")
        if not name or lat is None or lon is None:
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
    chosen = [idx[s] for s in sels if s in idx]
    rows = [r for r in (row_from_osm_element(e) for e in chosen) if r]
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
        f"<p><a class='btn secondary' href='{html.escape(url_for('stores.osm_import_form'))}'>Import more</a> "
        f"<a class='btn' href='/stores'>Go to Stores</a></p>"
        "</div>"
    )
    return page("OSM Import Done", body)
