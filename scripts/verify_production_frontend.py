import hashlib
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright

base = "https://prior.103-195-188-198.sslip.io"
client = httpx.Client(base_url=base, timeout=15.0)

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

files = [
    ("index.html", Path("src/prior/static/index.html"), "/"),
    ("styles.css", Path("src/prior/static/styles.css"), "/static/styles.css?v=e48ab83"),
    ("app.js", Path("src/prior/static/app.js"), "/static/app.js?v=e48ab83"),
]

for name, local_path, prod_url in files:
    local_hash = sha256_file(local_path)
    resp = client.get(prod_url)
    prod_hash = sha256_bytes(resp.content)
    match = local_hash == prod_hash
    print(f"=== {name} ===")
    print(f"Local SHA256:      {local_hash}")
    print(f"Production SHA256: {prod_hash}")
    print(f"Match:             {match}")
    print(f"Status:            {resp.status_code}")
    print(f"Headers:           {dict(resp.headers)}")
    print()

health = client.get("/api/health").json()
print("HEALTH BUILD COMMIT:", health.get("build_commit"))
print("HEALTH OVERALL:", health.get("overall"))

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(base + "/", wait_until="networkidle")
    page.screenshot(path="evidence/prod_verified_1440.png")
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path="evidence/prod_verified_390.png")
    
    bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
    color = page.evaluate("getComputedStyle(document.body).color")
    bg_image = page.evaluate("getComputedStyle(document.body).backgroundImage")
    cta_bg = page.evaluate('getComputedStyle(document.querySelector(".button-primary, button.primary, .btn-primary, .button")).backgroundColor')
    
    print("COMPUTED BODY BG:", bg)
    print("COMPUTED BODY COLOR:", color)
    print("COMPUTED BODY BG IMAGE:", bg_image)
    print("COMPUTED CTA BG:", cta_bg)
    browser.close()
print("SCREENSHOTS CAPTURED OK")
