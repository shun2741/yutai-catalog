from __future__ import annotations
import html
from flask import Blueprint, request, redirect, url_for
from urllib.parse import quote
import urllib.request
import urllib.parse
import re
import json

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
        "<span style='float:right'>"
        "<a class='btn' href='/companies/new'>Add company</a>"
        "</span>"
        "</form>"
    )
    if not rows:
        return page("Companies", head + "<p>No companies yet.</p></div>")
    th = "".join(
        f"<th>{html.escape(h)}</th>"
        for h in ["id", "name", "ticker", "chainIds", "voucherTypes", "notes", "url"]
    )
    trs = []
    for r in rows:
        actions = (
            f"<a class='btn secondary' href='/companies/{html.escape(r.get('id',''))}/edit'>Edit</a> "
            f"<form method='post' action='/companies/{html.escape(r.get('id',''))}/delete' style='display:inline' onsubmit='return confirmDelete()'>"
            "<button class='btn danger' type='submit'>Delete</button></form>"
        )
        data_cells = [
            r.get("id", ""),
            r.get("name", ""),
            r.get("ticker", ""),
            r.get("chainIds", ""),
            r.get("voucherTypes", ""),
            r.get("notes", ""),
            r.get("url", ""),
        ]
        encoded = quote(actions, safe='')
        tds = "".join(f"<td>{html.escape(c)}</td>" for c in data_cells) + f"<td data-raw='{encoded}'></td>"
        trs.append(f"<tr>{tds}</tr>")
    table = f"<table><tr>{th}<th></th></tr>{''.join(trs)}</table></div>"
    # Some environments escape inner HTML; ensure action buttons render
    return page("Companies", html.unescape(head + table))


# --- Auto import (experimental) ---


@bp.get("/companies/auto_import")
def companies_auto_import_form():
    form = (
        "<div class='panel'><h2>Companies: Auto Import (experimental)</h2>"
        "<form method='post' action='/companies/auto_import'>"
        "<div class='row'>Source URLs (one per line)<br><textarea name='urls' rows='6' style='width:100%;padding:8px 10px;border-radius:8px;border:1px solid rgba(255,255,255,0.15);background:#0c1327;color:#e8ebf1' placeholder='https://example.com/list1\nhttps://example.com/list2'></textarea></div>"
        "<div class='row'>Or paste raw text<br><textarea name='raw' rows='6' style='width:100%;padding:8px 10px;border-radius:8px;border:1px solid rgba(255,255,255,0.15);background:#0c1327;color:#e8ebf1' placeholder='(optional)'></textarea></div>"
        "<div class='row'>Ticker regex (4 digits) & keyword<br><input name='keyword' value='優待' style='width:200px'> <span class='help'>Used to narrow extraction (optional)</span></div>"
        "<div class='actions'><button class='btn' type='submit'>Fetch & Preview</button> <a class='btn secondary' href='/companies'>Back</a></div>"
        "</form></div>"
    )
    return page("Companies Auto Import", form)


def _fetch_text_from_urls(urls: list[str], timeout: int = 20) -> str:
    chunks: list[str] = []
    for u in urls:
        u = u.strip()
        if not u:
            continue
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            try:
                text = data.decode("utf-8", errors="ignore")
            except Exception:
                text = data.decode("shift_jis", errors="ignore")
            chunks.append(text)
        except Exception:
            continue
    return "\n\n".join(chunks)


def _extract_candidates(text: str, keyword: str | None = None) -> list[tuple[str, str]]:
    # Normalize whitespace
    body = re.sub(r"\s+", " ", text)
    # Find all 4-digit tickers
    candidates: set[tuple[str, str]] = set()
    for m in re.finditer(r"(\d{4})", body):
        ticker = m.group(1)
        # Extract nearby window for name heuristics
        start = max(0, m.start() - 60)
        end = min(len(body), m.end() + 60)
        window = body[start:end]
        if keyword and keyword not in window:
            continue
        # Heuristic for company name: contiguous CJK/katakana/hiragana/英字 + 株式会社/HD等含む
        name_match = re.search(r"([\u3040-\u30FF\u4E00-\u9FFFＡ-ＺA-Za-z0-9・ー＆\-]{2,20})", window)
        name = name_match.group(1) if name_match else f"{ticker}"
        # Clean obvious suffixes
        name = name.strip()
        candidates.add((ticker, name))
    # Return sorted unique
    return sorted(candidates)


@bp.post("/companies/auto_import")
def companies_auto_import_preview():
    urls_raw = (request.form.get("urls") or "").strip()
    raw_text = (request.form.get("raw") or "").strip()
    keyword = (request.form.get("keyword") or "").strip() or None
    urls = [u.strip() for u in urls_raw.splitlines() if u.strip()]
    text = raw_text or _fetch_text_from_urls(urls)
    if not text:
        return page("Error", "<div class='panel'><p>No input text or fetch failed.</p><p><a class='btn secondary' href='/companies/auto_import'>Back</a></p></div>"), 400
    cands = _extract_candidates(text, keyword)
    # Compare with existing
    existing = read_csv(DATA / "companies.csv")
    existing_ids = {r.get("id") for r in existing}
    existing_tickers = {r.get("ticker") for r in existing}
    rows = []
    for ticker, name in cands:
        cid = f"comp-{ticker}"
        dup = (cid in existing_ids) or (ticker in existing_tickers)
        rows.append((cid, name, ticker, dup))
    th = "".join(f"<th>{h}</th>" for h in ["Select", "id", "name", "ticker", "status"])
    trs = []
    for cid, name, ticker, dup in rows:
        cb = "" if dup else f"<input type='checkbox' name='sel' value='{html.escape(cid)}' checked>"
        status = "duplicate" if dup else "new"
        tds = "".join(f"<td>{html.escape(x)}</td>" for x in [cid, name, ticker, status])
        trs.append(f"<tr><td>{cb}</td>{tds}</tr>")
    form = (
        "<div class='panel'>"
        "<h2>Preview: Companies Auto Import</h2>"
        f"<form method='post' action='/companies/auto_import/commit'>"
        f"<input type='hidden' name='keyword' value='{html.escape(keyword or '')}'>"
        f"<input type='hidden' name='urls' value='{html.escape(urls_raw)}'>"
        f"<input type='hidden' name='raw' value='{html.escape(raw_text)}'>"
        f"<table><tr>{th}</tr>{''.join(trs)}</table>"
        "<div class='actions'><button class='btn' type='submit'>Import Selected</button> <a class='btn secondary' href='/companies/auto_import'>Back</a></div>"
        "</form>"
        "</div>"
    )
    return page("Companies Auto Import Preview", form)


@bp.post("/companies/auto_import/commit")
def companies_auto_import_commit():
    sels = request.form.getlist("sel")
    if not sels:
        return page("Error", "<div class='panel'><p>No selection.</p><p><a class='btn secondary' href='/companies/auto_import'>Back</a></p></div>"), 400
    existing = read_csv(DATA / "companies.csv")
    existing_ids = {r.get("id") for r in existing}
    existing_tickers = {r.get("ticker") for r in existing}
    added = 0
    for cid in sels:
        m = re.match(r"comp-(\d{4})$", cid)
        if not m:
            continue
        ticker = m.group(1)
        # name fallback = ticker
        name = ticker
        row = {"id": cid, "name": name, "ticker": ticker, "chainIds": "", "voucherTypes": "その他", "notes": ""}
        if cid in existing_ids or ticker in existing_tickers:
            continue
        existing.append(row)
        existing_ids.add(cid)
        existing_tickers.add(ticker)
        added += 1
    write_csv(
        DATA / "companies.csv",
        existing,
        ["id", "name", "ticker", "chainIds", "voucherTypes", "notes", "url"],
    )
    body = (
        "<div class='panel'>"
        f"<p>Imported <b>{added}</b> companies.</p>"
        "<p class='help'>Names default to ticker if not detected. Please edit as needed.</p>"
        "<p><a class='btn' href='/companies'>Go to Companies</a></p>"
        "</div>"
    )
    return page("Companies Auto Import Done", body)


# --- J-Quants import (experimental) ---


JQ_LISTED_URL = "https://api.jquants.com/v1/listed/info"


@bp.get("/companies/jquants")
def companies_jquants_form():
    form = (
        "<div class='panel'><h2>Companies: J-Quants Import (experimental)</h2>"
        "<form method='post' action='/companies/jquants'>"
        "<div class='row'>Bearer Token (idToken)<br><input name='token' placeholder='eyJ... (idToken; optional if using email/password or refreshToken)' style='width:100%'></div>"
        "<div class='row'>— または —</div>"
        "<div class='row'>Email / Password から取得<br>"
        "Email <input name='mail' placeholder='you@example.com' style='width:280px'> "
        "Password <input type='password' name='password' placeholder='********' style='width:220px'> "
        "</div>"
        "<div class='row'>Refresh Token から取得<br><input name='refresh' placeholder='refreshToken (optional)' style='width:100%'></div>"
        "<div class='row'>Filter (optional)<br>"
        "Code prefix <input name='prefix' placeholder='e.g. 13' style='width:120px'> "
        "Market <input name='market' placeholder='PRIME/STANDARD/GROWTH' style='width:220px'> "
        "</div>"
        "<div class='actions'><button class='btn' type='submit'>Fetch & Preview</button> <a class='btn secondary' href='/companies'>Back</a></div>"
        "</form>"
        "<p class='help'>注: この画面はアクセストークンをそのまま送信します。セキュリティのため、使い終わったらトークンをローテーションしてください。</p>"
        "</div>"
    )
    return page("Companies J-Quants Import", form)


def _jq_fetch_listed(token: str) -> list[dict]:
    if not token:
        return []
    req = urllib.request.Request(JQ_LISTED_URL, headers={"Authorization": f"Bearer {token}", "User-Agent": "yutai-admin/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read().decode("utf-8", errors="ignore")
    try:
        obj = json.loads(data)
    except Exception:
        return []
    # common payload shape: {"info":[{"Code":"1301","CompanyName":"...","Market":"PRIME"}, ...]}
    arr = obj.get("info") or obj.get("results") or obj.get("data") or []
    out = []
    for it in arr:
        code = str(it.get("Code") or it.get("code") or "").strip()
        name = str(it.get("CompanyName") or it.get("companyName") or it.get("Name") or "").strip()
        market = str(it.get("Market") or it.get("market") or "").strip()
        if code:
            out.append({"code": code, "name": name or code, "market": market})
    return out


def _jq_get_refresh_token(mail: str, password: str) -> str:
    url = "https://api.jquants.com/v1/token/auth_user"
    payload = json.dumps({"mailaddress": mail, "password": password}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "yutai-admin/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read().decode("utf-8", errors="ignore")
    obj = json.loads(data or "{}")
    token = obj.get("refreshToken") or obj.get("refreshtoken") or obj.get("refresh_token")
    if not token:
        raise RuntimeError(f"refreshToken not found in response: {obj}")
    return token


def _jq_get_id_from_refresh(refresh_token: str) -> str:
    url = f"https://api.jquants.com/v1/token/auth_refresh?refreshtoken={urllib.parse.quote(refresh_token)}"
    req = urllib.request.Request(url, method="POST", headers={"User-Agent": "yutai-admin/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read().decode("utf-8", errors="ignore")
    obj = json.loads(data or "{}")
    token = obj.get("idToken") or obj.get("id_token")
    if not token:
        raise RuntimeError(f"idToken not found in response: {obj}")
    return token


@bp.post("/companies/jquants")
def companies_jquants_preview():
    token = (request.form.get("token") or "").strip()
    prefix = (request.form.get("prefix") or "").strip()
    market = (request.form.get("market") or "").strip().upper()
    # Optional helpers: mail/password or refresh
    mail = (request.form.get("mail") or "").strip()
    password = (request.form.get("password") or "").strip()
    refresh = (request.form.get("refresh") or "").strip()
    # If no id token provided, try to derive
    if not token:
        try:
            if not refresh and mail and password:
                refresh = _jq_get_refresh_token(mail, password)
            if refresh:
                token = _jq_get_id_from_refresh(refresh)
        except Exception as e:
            msg = f"Failed to obtain token: {e}"
            return page("J-Quants Error", f"<div class='panel'><p>{html.escape(msg)}</p><p><a class='btn secondary' href='/companies/jquants'>Back</a></p></div>"), 502
    try:
        listed = _jq_fetch_listed(token)
    except Exception as e:
        msg = f"J-Quants API error: {e}"
        return page("J-Quants Error", f"<div class='panel'><p>{html.escape(msg)}</p><p><a class='btn secondary' href='/companies/jquants'>Back</a></p></div>"), 502
    if prefix:
        listed = [x for x in listed if x.get("code", "").startswith(prefix)]
    if market:
        listed = [x for x in listed if (x.get("market") or "").upper().startswith(market)]
    existing = read_csv(DATA / "companies.csv")
    existing_ids = {r.get("id") for r in existing}
    existing_tickers = {r.get("ticker") for r in existing}
    rows = []
    for it in listed:
        code = it.get("code")
        name = it.get("name")
        cid = f"comp-{code}"
        dup = (cid in existing_ids) or (code in existing_tickers)
        rows.append((cid, name, code, it.get("market", ""), dup))
    th = "".join(f"<th>{h}</th>" for h in ["Select", "id", "name", "ticker", "market", "status"])
    trs = []
    for cid, name, code, mkt, dup in rows:
        cb = "" if dup else f"<input type='checkbox' name='sel' value='{html.escape(cid)}' checked>"
        status = "duplicate" if dup else "new"
        tds = "".join(f"<td>{html.escape(x)}</td>" for x in [cid, name, code, mkt, status])
        trs.append(f"<tr><td>{cb}</td>{tds}</tr>")
    form = (
        "<div class='panel'>"
        "<h2>Preview: Companies J-Quants Import</h2>"
        f"<form method='post' action='/companies/jquants/commit'>"
        f"<input type='hidden' name='token' value='{html.escape(token)}'>"
        f"<input type='hidden' name='prefix' value='{html.escape(prefix)}'>"
        f"<input type='hidden' name='market' value='{html.escape(market)}'>"
        f"<table><tr>{th}</tr>{''.join(trs)}</table>"
        "<div class='actions'><button class='btn' type='submit'>Import Selected</button> <a class='btn secondary' href='/companies/jquants'>Back</a></div>"
        "</form>"
        "</div>"
    )
    return page("Companies J-Quants Import Preview", form)


@bp.post("/companies/jquants/commit")
def companies_jquants_commit():
    sels = request.form.getlist("sel")
    if not sels:
        return page("Error", "<div class='panel'><p>No selection.</p><p><a class='btn secondary' href='/companies/jquants'>Back</a></p></div>"), 400
    existing = read_csv(DATA / "companies.csv")
    existing_ids = {r.get("id") for r in existing}
    existing_tickers = {r.get("ticker") for r in existing}
    added = 0
    for cid in sels:
        m = re.match(r"comp-(\d{4})$", cid)
        if not m:
            continue
        ticker = m.group(1)
        name = ticker
        row = {"id": cid, "name": name, "ticker": ticker, "chainIds": "", "voucherTypes": "その他", "notes": ""}
        if cid in existing_ids or ticker in existing_tickers:
            continue
        existing.append(row)
        existing_ids.add(cid)
        existing_tickers.add(ticker)
        added += 1
    write_csv(
        DATA / "companies.csv",
        existing,
        ["id", "name", "ticker", "chainIds", "voucherTypes", "notes", "url"],
    )
    body = (
        "<div class='panel'>"
        f"<p>Imported <b>{added}</b> companies from J-Quants.</p>"
        "<p class='help'>Names default to ticker if not supplied by API. Please edit as needed.</p>"
        "<p><a class='btn' href='/companies'>Go to Companies</a></p>"
        "</div>"
    )
    return page("Companies J-Quants Import Done", body)


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
        "<div class='row'>URL<br><input name='url' placeholder='https://... (optional)'></div>"
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
    url_val = request.form.get("url", "").strip()
    if not vid or not name:
        return page("Error", "<div class='panel'><p>Missing id or name</p></div>"), 400
    row = {
        "id": vid,
        "name": name,
        "ticker": ticker,
        "chainIds": "",
        "voucherTypes": ",".join(vts),
        "notes": notes,
        "url": url_val,
    }
    try:
        append_row_csv(
            DATA / "companies.csv",
            row,
            ["id", "name", "ticker", "chainIds", "voucherTypes", "notes", "url"],
        )
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
        f"<div class='row'>URL<br><input name='url' value='{html.escape(rec.get('url',''))}' placeholder='https://... (optional)'></div>"
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
    url_val = request.form.get("url", "").strip()
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
            "url": url_val,
        },
        ["id", "name", "ticker", "chainIds", "voucherTypes", "notes", "url"],
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
    ok = delete_row_csv(
        DATA / "companies.csv",
        vid,
        ["id", "name", "ticker", "chainIds", "voucherTypes", "notes", "url"],
    )
    if not ok:
        return page("Not Found", f"<div class='panel'><p>Company not found: {html.escape(vid)}</p></div>"), 404
    return redirect(url_for("companies.list_companies"))
