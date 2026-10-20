"""Test navigateur du chrono : le serveur doit tourner avec BACKEND=mock TIME_LIMIT=10.

Usage :  python tools/e2e_timeout.py http://127.0.0.1:8766
"""
from __future__ import annotations

import os
import sys
import time

from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip("/")
CHROME = os.environ.get("CHROME_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
problems: list[str] = []


def check(cond: bool, label: str) -> None:
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        problems.append(label)


with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
    ctx = browser.new_context()
    page = ctx.new_page()

    print("[A] le chrono arrive à zéro dans le navigateur")
    page.goto(BASE + "/")
    page.wait_for_selector("#rules li")
    check("0:10" in page.locator("#rules").inner_text(), "règles : 0:10 (TIME_LIMIT=10)")
    page.fill("#name", "Lent")
    page.click("#start-btn")
    page.wait_for_selector("#screen-game:not([hidden])")
    page.fill("#msg", "bonjour")
    page.click("#send-btn")
    page.wait_for_selector(".bubble.guardian")
    t0 = time.time()
    page.wait_for_selector("#screen-end:not([hidden])", timeout=20000)
    waited = time.time() - t0
    check(5 <= waited <= 13, f"l'écran final apparaît tout seul à la fin du temps ({waited:.1f} s après la réponse)")
    check("Temps écoulé" in page.locator("#end-title").inner_text(), "titre : Temps écoulé")
    check(page.locator("#end-points").inner_text() == "0", "0 point")
    page.screenshot(path=sys.argv[2] if len(sys.argv) > 2 else "/tmp/ctb-timeout.png")

    print("[B] le joueur ferme son onglet : le serveur termine la partie seul")
    page2 = ctx.new_page()
    page2.goto(BASE + "/")
    page2.wait_for_selector("#rules li")
    page2.fill("#name", "Fantôme")
    page2.click("#start-btn")
    page2.wait_for_selector("#screen-game:not([hidden])")
    page2.fill("#msg", "salut")
    page2.click("#send-btn")
    page2.wait_for_selector(".bubble.guardian")
    page2.close()
    time.sleep(13)
    names = [e["name"] for e in ctx.request.get(BASE + "/api/leaderboard").json()["entries"]]
    check("Fantôme" in names, f"« Fantôme » est dans le classement sans que personne n'ait cliqué ({names})")
    check(names.count("Lent") == 1, "« Lent » n'est enregistré qu'une seule fois")
    browser.close()

print("\n" + ("TOUT EST OK" if not problems else "ÉCHEC : " + "; ".join(problems)))
sys.exit(1 if problems else 0)
