import json

from app.leaderboard import Leaderboard


def make(tmp_path):
    return Leaderboard(tmp_path / "lb.json")


def test_ranking_order_levels_then_time_then_arrival(tmp_path):
    lb = make(tmp_path)
    a = lb.add("A", levels=2, points=2100, time_left=100.0)
    b = lb.add("B", levels=3, points=3010, time_left=10.0)
    c = lb.add("C", levels=2, points=2150, time_left=150.0)
    d = lb.add("D", levels=2, points=2150, time_left=150.0)  # égalité parfaite avec C : C est arrivé avant
    order = [e["name"] for e in lb.top()]
    assert order == ["B", "C", "D", "A"]
    assert [e["rank"] for e in lb.top()] == [1, 2, 3, 4]
    assert lb.rank_of(a["id"]) == 4
    assert lb.rank_of(b["id"]) == 1 and lb.rank_of(c["id"]) == 2 and lb.rank_of(d["id"]) == 3
    assert lb.rank_of("inconnu") is None
    assert [e["name"] for e in lb.top(2)] == ["B", "C"]


def test_zero_level_players_rank_last(tmp_path):
    lb = make(tmp_path)
    lb.add("Zero", 0, 0, 0.0)
    lb.add("One", 1, 1000, 0.5)
    assert [e["name"] for e in lb.top()] == ["One", "Zero"]


def test_persistence_roundtrip(tmp_path):
    lb = make(tmp_path)
    lb.add("Élodie & Sami", 4, 4120, 120.4)
    again = make(tmp_path)
    assert [e["name"] for e in again.top()] == ["Élodie & Sami"]
    assert not list(tmp_path.glob("*.tmp"))  # l'écriture atomique ne laisse rien derrière


def test_delete(tmp_path):
    lb = make(tmp_path)
    e = lb.add("A", 1, 1000, 1.0)
    assert lb.delete("nope") is False
    assert lb.delete(e["id"]) is True
    assert lb.top() == []
    assert make(tmp_path).top() == []  # la suppression est bien écrite sur disque


def test_reset_keeps_a_backup(tmp_path):
    lb = make(tmp_path)
    lb.add("A", 1, 1000, 1.0)
    lb.add("B", 2, 2000, 1.0)
    assert lb.reset() == 2
    assert lb.top() == []
    backups = list(tmp_path.glob("lb.backup-*.json"))
    assert len(backups) == 1
    assert len(json.loads(backups[0].read_text())["entries"]) == 2
    lb.add("C", 1, 1000, 1.0)
    lb.reset()
    lb.add("D", 1, 1000, 1.0)
    lb.reset()
    assert len(list(tmp_path.glob("lb.backup-*.json"))) == 3  # pas d'écrasement dans la même seconde


def test_corrupt_file_is_set_aside_not_crashing(tmp_path):
    path = tmp_path / "lb.json"
    path.write_text("{ ceci n'est pas du json", encoding="utf-8")
    lb = Leaderboard(path)
    assert lb.top() == []
    assert len(list(tmp_path.glob("lb.corrupt-*.json"))) == 1
    lb.add("A", 1, 1000, 1.0)  # le jeu continue de fonctionner
    assert Leaderboard(path).top()[0]["name"] == "A"


def test_wrong_structure_is_also_treated_as_corrupt(tmp_path):
    path = tmp_path / "lb.json"
    path.write_text(json.dumps({"entries": [{"name": "sans id"}]}), encoding="utf-8")
    assert Leaderboard(path).top() == []
    assert len(list(tmp_path.glob("lb.corrupt-*.json"))) == 1
