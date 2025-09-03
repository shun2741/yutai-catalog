from __future__ import annotations
import csv
import html
from pathlib import Path
from typing import List, Dict
from flask import url_for
from string import Template

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"

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


HTML_BASE_TMPL = Template(
    """
<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
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
    document.addEventListener('DOMContentLoaded', function(){
      document.querySelectorAll('td[data-raw]').forEach(function(td){
        try{ td.innerHTML = decodeURIComponent(td.getAttribute('data-raw')||''); }catch(e){ /* noop */ }
      });
    });
  </script>
  </head>
<body>
  <div class=\"wrap\">
    <header>
      <h1>Yutai Catalog Admin — Admin v1</h1>
      <nav>
        <a href=\"$root\">Dashboard</a>
        <a href=\"$companies\">Companies</a>
        <a href=\"$chains\">Chains</a>
        <a href=\"/stores\">Stores</a>
        <a href=\"$stores_osm\">Stores (OSM)</a>
        <a href=\"/ops\">Ops</a>
      </nav>
    </header>
    $body
  </div>
  </body>
</html>
"""
)


def page(title: str, body_html: str) -> str:
    return HTML_BASE_TMPL.safe_substitute(
        title=html.escape(title),
        root=html.escape(url_for("dashboard.index")),
        companies=html.escape(url_for("companies.list_companies")),
        chains=html.escape(url_for("chains.list_chains")),
        stores_osm=html.escape(url_for("stores.osm_import_form")),
        body=body_html,
    )
