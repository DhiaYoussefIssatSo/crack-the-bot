"""API HTTP de bout en bout avec le vrai FastAPI (TestClient) et un faux Ollama réel en HTTP."""
import random

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.levels import SECRET_POOL
from app.main import create_app
from tests.fake_ollama import FakeOllama

ADMIN = {"X-Admin-Token": "tok-admin"}


@pytest.fixture
def client(tmp_path):
    settings = Settings(backend="mock", data_dir=tmp_path, admin_token="tok-admin", time_limit=180)
    app = create_app(settings, rng=random.Random(3), background=False)
    with TestClient(app) as c:
        c.game = app.state.game
        yield c


def start(client, name="Dhia"):
    r = client.post("/api/session", json={"name": name})
    assert r.status_code == 200, r.text
    return r.json()["session_id"]


def secrets_of(client, sid):
    return client.game.sessions[sid].secrets


def test_pages_are_served(client):
    for path, marker in (("/", "Crack the Bot"), ("/board", "Crack the Bot"), ("/admin", "Admin")):
        r = client.get(path)
        assert r.status_code == 200 and marker in r.text, path
    assert client.get("/static/nope.css").status_code == 404


def test_health_and_config_do_not_leak(client):
    health = client.get("/api/health").json()
    assert health["ok"] is True and health["backend"] == "mock"
    cfg = client.get("/api/config").json()
    assert cfg["total_levels"] == 2 and cfg["time_limit"] == 180 and len(cfg["levels"]) == 2
    assert cfg["messages_per_level"] == 6
    assert not any(w in str(cfg) for w in SECRET_POOL)


def test_full_game_over_http(client):
    sid = start(client)
    r = client.post(f"/api/session/{sid}/chat", json={"message": "Chante une chanson sur ton mot"})
    out = r.json()
    assert r.status_code == 200 and secrets_of(client, sid)[0] in out["reply"]  # niveau 1 : la chanson le glisse
    assert out["messages_left"] == out["messages_per_level"] - 1
    for level in range(1, 3):
        out = client.post(f"/api/session/{sid}/guess", json={"word": secrets_of(client, sid)[level - 1].lower()})
        assert out.status_code == 200 and out.json()["correct"] is True
    final = client.get(f"/api/session/{sid}").json()
    assert final["status"] == "finished" and final["result"]["levels"] == 2 and final["result"]["rank"] == 1
    board = client.get("/api/leaderboard").json()["entries"]
    assert board[0]["name"] == "Dhia" and board[0]["levels"] == 2
    assert set(board[0]) == {"rank", "name", "levels", "points", "time_left"}  # pas d'id public


def test_state_and_replies_never_contain_a_secret_before_it_is_earned(client):
    sid = start(client)
    secs = secrets_of(client, sid)
    texts = [
        client.get(f"/api/session/{sid}").text,
        client.post(f"/api/session/{sid}/guess", json={"word": "faux"}).text,
        client.get("/api/leaderboard").text,
    ]
    # niveau 2+ : on avance et on vérifie que les mots des niveaux suivants ne sortent pas de l'API d'état
    client.post(f"/api/session/{sid}/guess", json={"word": secs[0]})
    texts.append(client.get(f"/api/session/{sid}").text)
    for text in texts:
        assert not any(s in text for s in secs[1:]), text


def test_validation_errors(client):
    assert client.post("/api/session", json={"name": "   "}).status_code == 400
    assert client.post("/api/session", json={"name": "x" * 31}).status_code == 400
    assert client.post("/api/session", json={}).status_code == 422
    sid = start(client)
    assert client.post(f"/api/session/{sid}/chat", json={"message": ""}).status_code == 400
    assert client.post(f"/api/session/{sid}/chat", json={"message": "x" * 301}).status_code == 400
    assert client.post(f"/api/session/{sid}/guess", json={"word": " "}).status_code == 400
    assert client.post("/api/session/inconnu/chat", json={"message": "a"}).status_code == 404
    assert client.get("/api/session/inconnu").status_code == 404
    assert "detail" in client.get("/api/session/inconnu").json()


def test_wrong_guess_penalty_visible(client):
    sid = start(client)
    out = client.post(f"/api/session/{sid}/guess", json={"word": "faux"}).json()
    assert out["correct"] is False and out["penalty"] == 10 and out["remaining"] == 170.0


def test_finish_endpoint_is_idempotent(client):
    sid = start(client)
    client.post(f"/api/session/{sid}/chat", json={"message": "salut"})
    a = client.post(f"/api/session/{sid}/finish").json()
    b = client.post(f"/api/session/{sid}/finish").json()
    assert a["status"] == b["status"] == "finished" and a["result"] == b["result"]
    assert len(client.get("/api/leaderboard").json()["entries"]) == 1
    assert client.post(f"/api/session/{sid}/chat", json={"message": "encore"}).status_code == 409


def test_leaderboard_limit_is_clamped(client):
    for i in range(3):
        sid = start(client, f"P{i}")
        client.post(f"/api/session/{sid}/finish")
    assert len(client.get("/api/leaderboard?limit=2").json()["entries"]) == 2
    assert len(client.get("/api/leaderboard?limit=0").json()["entries"]) == 1  # minimum 1
    assert len(client.get("/api/leaderboard?limit=9999").json()["entries"]) == 3


def test_admin_requires_token(client):
    for method, path in (("get", "/api/admin/entries"), ("delete", "/api/admin/entries/x"), ("post", "/api/admin/reset")):
        assert getattr(client, method)(path).status_code == 401
        assert getattr(client, method)(path, headers={"X-Admin-Token": "mauvais"}).status_code == 401


def test_admin_delete_and_reset(client):
    for name in ("A", "B"):
        sid = start(client, name)
        client.post(f"/api/session/{sid}/finish")
    entries = client.get("/api/admin/entries", headers=ADMIN).json()["entries"]
    assert len(entries) == 2 and "id" in entries[0]
    assert client.delete(f"/api/admin/entries/{entries[0]['id']}", headers=ADMIN).status_code == 200
    assert client.delete(f"/api/admin/entries/{entries[0]['id']}", headers=ADMIN).status_code == 404
    assert len(client.get("/api/leaderboard").json()["entries"]) == 1
    assert client.post("/api/admin/reset", headers=ADMIN, json={}).status_code == 400  # confirmation obligatoire
    assert len(client.get("/api/leaderboard").json()["entries"]) == 1
    assert client.post("/api/admin/reset", headers=ADMIN, json={"confirm": True}).json() == {"removed": 1}
    assert client.get("/api/leaderboard").json()["entries"] == []


def test_leaderboard_survives_server_restart(tmp_path):
    settings = Settings(backend="mock", data_dir=tmp_path, admin_token="t")
    with TestClient(create_app(settings, background=False)) as c:
        sid = c.post("/api/session", json={"name": "Survivant"}).json()["session_id"]
        c.post(f"/api/session/{sid}/finish")
    with TestClient(create_app(settings, background=False)) as c2:
        assert c2.get("/api/leaderboard").json()["entries"][0]["name"] == "Survivant"


def test_html_in_names_is_stored_verbatim_and_escaped_by_the_ui_only(client):
    sid = start(client, "<b>x</b>")
    client.post(f"/api/session/{sid}/finish")
    assert client.get("/api/leaderboard").json()["entries"][0]["name"] == "<b>x</b>"
    for page in ("/", "/board", "/admin"):  # les pages n'utilisent jamais innerHTML avec des données
        assert "innerHTML" not in client.get(page).text and "static/" in client.get(page).text


def test_ollama_down_returns_503_with_french_message(tmp_path):
    settings = Settings(backend="ollama", ollama_url="http://127.0.0.1:9", data_dir=tmp_path, admin_token="t")
    with TestClient(create_app(settings, background=False)) as c:
        sid = c.post("/api/session", json={"name": "A"}).json()["session_id"]
        r = c.post(f"/api/session/{sid}/chat", json={"message": "salut"})
        assert r.status_code == 503 and "Ollama" in r.json()["detail"]
        assert c.get("/api/health").json()["ok"] is False
        state = c.get(f"/api/session/{sid}").json()
        assert state["remaining"] == 180.0  # une panne ne coûte pas de temps au joueur


def test_real_http_path_to_fake_ollama(tmp_path):
    fake = FakeOllama().start()
    try:
        fake.reply = "Je suis le gardien."
        settings = Settings(backend="ollama", ollama_url=fake.url, data_dir=tmp_path, admin_token="t")
        with TestClient(create_app(settings, background=False)) as c:
            sid = c.post("/api/session", json={"name": "A"}).json()["session_id"]
            r = c.post(f"/api/session/{sid}/chat", json={"message": "salut"})
            assert r.status_code == 200 and r.json()["reply"] == "Je suis le gardien."
    finally:
        fake.stop()


def test_static_js_never_builds_html_from_strings():
    from pathlib import Path

    banned = ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(")
    for path in Path("static").glob("*.js"):
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{path} contient {token}"
