from __future__ import annotations
import html
from flask import Blueprint, url_for, request, redirect

from .common import read_csv, DATA, page, delete_row_csv

bp = Blueprint("dashboard", __name__)


@bp.get("/")
def index():
    comps = read_csv(DATA / "companies.csv")
    chs = read_csv(DATA / "chains.csv")
    stores = read_csv(DATA / "stores.csv")
    body = (
        "<div class='grid'>"
        "  <div class='panel'>"
        "    <h2>Companies</h2>"
        f"    <p><b>{len(comps)}</b> companies registered</p>"
        f"    <p><a class='btn' href='{html.escape(url_for('companies.list_companies'))}'>Manage Companies</a></p>"
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
        f"    <p><a class='btn' href='{html.escape(url_for('chains.list_chains'))}'>Manage Chains</a></p>"
        "    <form method='post' action='/chains/delete' onsubmit='return confirmDelete()' style='margin-top:8px'>"
        "      <div class='row'>Quick Delete by ID<br>"
        "        <input name='id' placeholder='chain-xxxx' required style='max-width:260px'>"
        "      </div>"
        "      <div class='actions'><button class='btn danger' type='submit'>Delete Chain</button></div>"
        "    </form>"
        "  </div>"
        "</div>"
        "<div class='panel' style='margin-top:16px'>"
        "  <h2>Stores</h2>"
        f"  <p><b>{len(stores)}</b> stores. Import from OSM by name pattern.</p>"
        f"  <p><a class='btn' href='/stores'>Manage Stores</a> "
        f"<a class='btn secondary' href='{html.escape(url_for('stores.osm_import_form'))}'>OSM Import</a> "
        f"<a class='btn secondary' href='/ops'>Build & Deploy</a></p>"
        "    <form method='post' action='/stores/delete' onsubmit='return confirmDelete()' style='margin-top:8px'>"
        "      <div class='row'>Quick Delete Store by ID<br>"
        "        <input name='id' placeholder='store-...' required style='max-width:360px'>"
        "      </div>"
        "      <div class='actions'><button class='btn danger' type='submit'>Delete Store</button></div>"
        "    </form>"
        "    <form method='post' action='/stores/edit_redirect' style='margin-top:8px'>"
        "      <div class='row'>Quick Edit Store by ID<br>"
        "        <input name='id' placeholder='store-...' required style='max-width:360px'>"
        "      </div>"
        "      <div class='actions'><button class='btn secondary' type='submit'>Open Edit</button></div>"
        "    </form>"
        "</div>"
    )
    return page("Dashboard", body)

