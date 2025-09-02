from __future__ import annotations
import html
from flask import Blueprint, request, redirect, url_for

from .common import (
    DATA,
    ALLOWED_VOUCHER_TYPES,
    read_csv,
    write_csv,
    append_row_csv,
    update_row_csv,
    delete_row_csv,
    page,
)

bp = Blueprint("companies", __name__)


@bp.get("/companies")
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
        actions = (
            f"<a class='btn secondary' href='/companies/{html.escape(r.get('id',''))}/edit'>Edit</a> "
            f"<form method='post' action='/companies/{html.escape(r.get('id',''))}/delete' style='display:inline' onsubmit='return confirmDelete()'>"
            "<button class='btn danger' type='submit'>Delete</button></form>"
        )
        cells = [r.get("id", ""), r.get("name", ""), r.get("ticker", ""), r.get("chainIds", ""), r.get("voucherTypes", ""), r.get("notes", ""), actions]
        tds = "".join(f"<td>{html.escape(c)}</td>" for c in cells)
        trs.append(f"<tr>{tds}</tr>")
    table = f"<table><tr>{th}<th></th></tr>{''.join(trs)}</table></div>"
    return page("Companies", head + table)


@bp.get("/companies/new")
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


@bp.post("/companies/new")
def create_company():
    vid = request.form.get("id", "").strip()
    name = request.form.get("name", "").strip()
    ticker = request.form.get("ticker", "").strip()
    vts = request.form.getlist("voucherTypes")
    notes = request.form.get("notes", "").strip()
    if not vid or not name:
        return page("Error", "<div class='panel'><p>Missing id or name</p></div>"), 400
    row = {
        "id": vid,
        "name": name,
        "ticker": ticker,
        "chainIds": "",
        "voucherTypes": ",".join(vts),
        "notes": notes,
    }
    try:
        append_row_csv(DATA / "companies.csv", row, ["id", "name", "ticker", "chainIds", "voucherTypes", "notes"])
    except ValueError as e:
        return page("Error", f"<div class='panel'><p>{html.escape(str(e))}</p></div>"), 400
    return redirect(url_for("companies.list_companies"))


@bp.get("/companies/<vid>/edit")
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


@bp.post("/companies/<vid>/edit")
def update_company(vid: str):
    name = request.form.get("name", "").strip()
    ticker = request.form.get("ticker", "").strip()
    vts = request.form.getlist("voucherTypes")
    notes = request.form.get("notes", "").strip()
    if not name:
        return page("Error", "<div class='panel'><p>Missing name</p></div>"), 400
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
    return redirect(url_for("companies.list_companies"))


@bp.post("/companies/<vid>/delete")
def delete_company(vid: str):
    chains = read_csv(DATA / "chains.csv")
    refs = [c for c in chains if vid in [s.strip() for s in (c.get("companyIds","") or "").split(",") if s.strip()]]
    if refs:
        msg = "この会社はチェーンから参照されています。先に chains.csv の companyIds から外してください。"
        return page("Blocked", f"<div class='panel'><p>{html.escape(msg)}</p><p><a class='btn secondary' href='/companies'>Back</a></p></div>"), 400
    ok = delete_row_csv(DATA / "companies.csv", vid, ["id", "name", "ticker", "chainIds", "voucherTypes", "notes"])
    if not ok:
        return page("Not Found", f"<div class='panel'><p>Company not found: {html.escape(vid)}</p></div>"), 404
    return redirect(url_for("companies.list_companies"))

