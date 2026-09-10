"""Static assets must never serve a stale bundle after deploy (ACP 78200 UAT).

The polling/CTA fixes were deployed and correct, yet the owner's browser ran
the pre-fix app.js because /static/* carried no Cache-Control and the manual
?v= pin was left stale. Every static response must now revalidate, and the
HTML must not pin a version that predates current app.js.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from prior.app import app

STATIC_DIR = Path("src/prior/static")


def test_static_assets_force_revalidation():
    client = TestClient(app)
    for path in ("/static/app.js", "/static/styles.css"):
        res = client.get(path)
        assert res.status_code == 200, path
        assert res.headers.get("cache-control") == "no-cache", path


def test_pages_remain_nostore():
    client = TestClient(app)
    for path in ("/", "/app", "/memory", "/proof"):
        res = client.get(path)
        assert res.status_code == 200
        assert "no-store" in res.headers.get("cache-control", "")


def test_index_pin_is_not_the_stale_release_value():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert "v=8ee56ef" not in html, "stale cache-buster from the pre-poll-fix era"
    assert "app.js?v=" in html and "styles.css?v=" in html
