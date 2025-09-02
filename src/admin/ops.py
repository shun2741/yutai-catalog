from __future__ import annotations
import html
import subprocess
from flask import Blueprint, request

from .common import ROOT, page

bp = Blueprint("ops", __name__)


def run_cmd(cmd: list[str], env: dict | None = None, cwd: str | None = None) -> tuple[int, str]:
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=cwd)
        out = (cp.stdout or "") + ("\n" + cp.stderr if cp.stderr else "")
        return cp.returncode, out
    except Exception as e:
        return 1, str(e)


@bp.get("/ops")
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


@bp.post("/ops")
def ops_run():
    from os import environ
    do_build = request.form.get("do_build") is not None
    do_commit = request.form.get("do_commit") is not None
    do_push = request.form.get("do_push") is not None
    msg = request.form.get("msg", "Admin build").strip() or "Admin build"
    logs = []
    code = 0
    env = dict(environ)
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

