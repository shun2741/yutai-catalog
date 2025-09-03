from __future__ import annotations
import html
from flask import Blueprint, request, redirect, url_for

from .common import (
    DATA,
    ALLOWED_VOUCHER_TYPES,
    read_csv,
    append_row_csv,
    update_row_csv,
    delete_row_csv,
    page,
)

bp = Blueprint("chains", __name__)


@bp.get("/chains")
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
        actions = (
            f"<a class='btn secondary' href='/chains/{html.escape(r.get('id',''))}/edit'>Edit</a> "
            f"<form method='post' action='/chains/{html.escape(r.get('id',''))}/delete' style='display:inline' onsubmit='return confirmDelete()'>"
            "<button class='btn danger' type='submit'>Delete</button></form>"
        )
        data_cells = [r.get("id", ""), r.get("displayName", ""), r.get("category", ""), comp_labels, r.get("voucherTypes", ""), r.get("tags", ""), r.get("url", "")]
        row_html = "".join(f"<td>{html.escape(c)}</td>" for c in data_cells) + f"<td>{actions}</td>"
        trs.append("<tr>" + row_html + "</tr>")
    table = f"<table><tr>{th}<th></th></tr>{''.join(trs)}</table></div>"
    return page("Chains", head + table)


@bp.get("/chains/new")
def new_chain():
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


@bp.post("/chains/new")
def create_chain():
    rid = request.form.get("id", "").strip()
    display = request.form.get("displayName", "").strip()
    category = request.form.get("category", "その他").strip() or "その他"
    company_ids = request.form.get("companyIds", "").strip()
    vts = request.form.getlist("voucherTypes")
    tags = request.form.get("tags", "").strip()
    url = request.form.get("url", "").strip()
    if not rid or not display:
        return page("Error", "<div class='panel'><p>Missing id or displayName</p></div>"), 400
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
        return page("Error", f"<div class='panel'><p>{html.escape(str(e))}</p></div>"), 400
    return redirect(url_for("chains.list_chains"))


@bp.get("/chains/<rid>/edit")
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


@bp.post("/chains/<rid>/edit")
def update_chain(rid: str):
    display = request.form.get("displayName", "").strip()
    category = request.form.get("category", "").strip() or "その他"
    comp_ids = request.form.getlist("companyIds")
    vts = request.form.getlist("voucherTypes")
    tags = request.form.get("tags", "").strip()
    url = request.form.get("url", "").strip()
    if not display:
        return page("Error", "<div class='panel'><p>Missing displayName</p></div>"), 400
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
    return redirect(url_for("chains.list_chains"))


@bp.post("/chains/<rid>/delete")
def delete_chain(rid: str):
    stores = read_csv(DATA / "stores.csv")
    refs = [s for s in stores if s.get("chainId") == rid]
    if refs:
        msg = "このチェーンには店舗データが紐づいています。先に stores.csv の該当行を削除してください。"
        return page("Blocked", f"<div class='panel'><p>{html.escape(msg)}</p><p><a class='btn secondary' href='/chains'>Back</a></p></div>"), 400
    ok = delete_row_csv(DATA / "chains.csv", rid, ["id", "displayName", "category", "companyIds", "voucherTypes", "tags", "url"])
    if not ok:
        return page("Not Found", f"<div class='panel'><p>Chain not found: {html.escape(rid)}</p></div>"), 404
    return redirect(url_for("chains.list_chains"))
