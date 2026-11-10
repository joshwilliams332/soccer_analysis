"""End-to-end build on a small made-up league shaped like the FPL API."""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import build_data  # noqa: E402
import fpl  # noqa: E402

TEAMS = [(1, "Alpha", "ALP"), (2, "Bravo", "BRA"), (3, "Charlie", "CHA"), (4, "Delta", "DEL")]
STRENGTH = {1: 2.0, 2: 1.4, 3: 1.0, 4: 0.6}  # xG created per match before the opponent's defense


def make_league(tmp):
    start = datetime(2026, 8, 21, 19, tzinfo=timezone.utc)
    pairs = [(1, 2), (3, 4), (1, 3), (2, 4), (1, 4), (2, 3)]
    schedule = [(h, a) for h, a in pairs] + [(a, h) for h, a in pairs]
    fixtures = []
    for i, (h, a) in enumerate(schedule):
        gw = i // 2 + 1
        done = gw <= 5
        hx, ax = STRENGTH[h] / STRENGTH[a] ** 0.5, STRENGTH[a] / STRENGTH[h] ** 0.5
        fixtures.append({"id": i + 1, "event": gw, "team_h": h, "team_a": a, "finished": done,
                         "kickoff_time": (start + timedelta(days=7 * (gw - 1))).isoformat().replace("+00:00", "Z"),
                         "team_h_score": round(hx) if done else None, "team_a_score": round(ax) if done else None,
                         "_hx": hx, "_ax": ax})
    elements, histories = [], {}
    pid = 0
    for tid, _, _ in TEAMS:
        # striker (70% of team xG, on pens), midfielder (30% xG, 60% xA), defender, keeper, injured winger
        for pos, xg_share, xa_share, status, chance in [(4, .7, .2, "a", None), (3, .3, .6, "a", None),
                                                        (2, 0, .2, "a", None), (1, 0, 0, "a", None),
                                                        (3, 0, 0, "i", 0)]:
            pid += 1
            elements.append({"id": pid, "web_name": f"P{pid}", "first_name": "F", "second_name": f"P{pid}",
                             "team": tid, "element_type": pos, "status": status,
                             "chance_of_playing_next_round": chance, "news": "Knee" if status == "i" else "",
                             "penalties_order": 1 if pos == 4 else None,
                             "corners_and_indirect_freekicks_order": None, "direct_freekicks_order": None,
                             "minutes": 0})
            rows = []
            for fx in fixtures:
                if not fx["finished"] or tid not in (fx["team_h"], fx["team_a"]):
                    continue
                home = fx["team_h"] == tid
                txg = fx["_hx"] if home else fx["_ax"]
                mins = 0 if status == "i" and fx["event"] >= 3 else 90
                rows.append({"fixture": fx["id"], "was_home": home, "minutes": mins, "starts": int(mins > 0),
                             "goals_scored": 1 if pos == 4 and txg > 1.2 else 0, "assists": 0,
                             "expected_goals": f"{txg * xg_share:.2f}" if mins else "0.00",
                             "expected_assists": f"{txg * xa_share:.2f}" if mins else "0.00",
                             "expected_goals_conceded": "1.00", "defensive_contribution": 5, "saves": 2})
            histories[str(pid)] = rows
            elements[-1]["minutes"] = sum(r["minutes"] for r in rows)
    for fx in fixtures:
        fx.pop("_hx"), fx.pop("_ax")
    events = [{"id": g, "deadline_time": f"2026-08-{20 + g:02d}T17:30:00Z", "finished": g <= 5,
               "is_next": g == 6} for g in range(1, 7)]
    boot = {"teams": [{"id": t, "name": n, "short_name": s} for t, n, s in TEAMS],
            "elements": elements, "events": events}
    raw = os.path.join(tmp, "raw")
    os.makedirs(raw)
    for name, data in (("bootstrap.json", boot), ("fixtures.json", fixtures), ("histories.json", histories)):
        with open(os.path.join(raw, name), "w") as fh:
            json.dump(data, fh)
    return raw


class TestBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        raw = make_league(cls.tmp)
        cls.out = os.path.join(cls.tmp, "build")
        cls.log = os.path.join(cls.tmp, "log")
        cls.meta = build_data.build(raw, cls.out, now=datetime(2026, 9, 20, tzinfo=timezone.utc), log_dir=cls.log)

        def read(n):
            with open(os.path.join(cls.out, n)) as fh:
                return json.load(fh)
        cls.teams, cls.players = read("teams.json"), read("players.json")
        cls.matches, cls.fixtures = read("matches.json"), read("fixtures.json")
        cls.acc = read("accuracy.json")

    def test_meta(self):
        self.assertEqual(self.meta["season"], "2026-27")
        self.assertEqual(self.meta["matches"], 10)
        self.assertEqual(self.meta["next_gw"], 6)
        self.assertEqual(self.meta["warnings"], [])

    def test_team_xg_is_sum_of_players(self):
        m = next(m for m in self.matches if m["id"] == 1)  # ALP v BRA
        expected = STRENGTH[1] / STRENGTH[2] ** 0.5
        self.assertAlmostEqual(m["hxg"], expected, delta=0.03)

    def test_team_ranks(self):
        best = next(t for t in self.teams if t["short"] == "ALP")
        worst = next(t for t in self.teams if t["short"] == "DEL")
        self.assertEqual(best["ranks"]["xgf_pg"]["rank"], 1)
        self.assertEqual(worst["ranks"]["xgf_pg"]["rank"], 4)
        self.assertEqual(best["ranks"]["xga_pg"]["rank"], 1)  # fewest allowed
        self.assertGreater(best["attack"], 1)
        self.assertLess(best["defense"], 1)
        self.assertEqual(sum(t["gp"] for t in self.teams), 20)

    def test_players(self):
        strikers = [p for p in self.players if p["pos"] == "FWD"]
        alp = next(p for p in strikers if p["team_short"] == "ALP")
        self.assertAlmostEqual(alp["xg_share"], 0.7, delta=0.02)
        self.assertEqual(alp["ranks"]["xg90_pos"]["rank"], 1)
        injured = [p for p in self.players if p["status"] == "i"]
        self.assertTrue(all(p["chance"] == 0 for p in injured))

    def test_fixtures(self):
        self.assertEqual(len(self.fixtures), 2)  # GW6 (GW7 doesn't exist)
        for fx in self.fixtures:
            pr = fx["probs"]
            self.assertAlmostEqual(pr["home"] + pr["draw"] + pr["away"], 1.0, delta=0.002)
            names = [w["name"] for w in fx["watch"]["home"] + fx["watch"]["away"]]
            self.assertTrue(names)
            # injured winger is listed as out, never as a player to watch
            out_ids = {o["id"] for o in fx["out"]["home"] + fx["out"]["away"]}
            self.assertTrue(out_ids)
            self.assertFalse(out_ids & {w["id"] for w in fx["watch"]["home"] + fx["watch"]["away"]})
        bra_del = next(fx for fx in self.fixtures if fx["home_short"] == "BRA" or fx["away_short"] == "BRA")
        self.assertIsNotNone(bra_del["proj"]["home"])

    def test_strong_side_favoured(self):
        # GW6: ALP host? find ALP's fixture and check it's favoured
        fx = next(fx for fx in self.fixtures if "ALP" in (fx["home_short"], fx["away_short"]))
        alp_home = fx["home_short"] == "ALP"
        p_alp = fx["probs"]["home"] if alp_home else fx["probs"]["away"]
        self.assertGreater(p_alp, 0.5)


    def test_accuracy(self):
        rep = self.acc["replay"]
        self.assertEqual(rep["n"], 4)  # GW4 and GW5, two matches each
        for k in ("brier", "brier_base", "logloss", "over_brier", "goals_pred"):
            self.assertIsNotNone(rep[k], k)
        # GW6 previews saved before kickoff (Sep 25); none graded yet
        self.assertEqual(len(os.listdir(self.log)), 2)
        self.assertEqual(self.acc["live"]["n"], 0)


class TestLiveGrading(unittest.TestCase):
    def test_frozen_preview_graded(self):
        import accuracy
        tmp = tempfile.mkdtemp()
        fx = {"id": 9, "gw": 6, "kickoff": "2026-09-25T19:00:00Z", "home": 1, "away": 2, "home_short": "ALP",
              "away_short": "BRA", "proj": {"home": 2.0, "away": 0.8},
              "probs": {"home": 0.65, "draw": 0.2, "away": 0.15, "over_2_5": 0.55}}
        accuracy.snapshot(tmp, [fx], "2026-09-24T10:00:00Z", "v0")
        accuracy.snapshot(tmp, [dict(fx, proj={"home": 9, "away": 9})], "2026-09-25T20:00:00Z", "v0")  # after kickoff: ignored
        prior = [{"id": 1, "gw": 1, "kickoff": "2026-08-21T19:00:00Z", "home": 1, "away": 2, "hg": 1, "ag": 0}]
        played = prior + [{"id": 9, "gw": 6, "kickoff": fx["kickoff"], "home": 1, "away": 2, "hg": 3, "ag": 1}]
        live, graded = accuracy.grade_live(tmp, played)
        self.assertEqual(live["n"], 1)
        self.assertEqual(graded[0]["proj"]["home"], 2.0)
        self.assertAlmostEqual(live["brier"], round(0.35 ** 2 + 0.2 ** 2 + 0.15 ** 2, 3))


class TestRefresh(unittest.TestCase):
    def test_needs_refresh(self):
        now = datetime(2026, 11, 10, tzinfo=timezone.utc)
        old = {"id": 1, "finished": True, "kickoff_time": "2026-10-01T15:00:00Z"}
        recent = {"id": 2, "finished": True, "kickoff_time": "2026-11-09T15:00:00Z"}
        self.assertFalse(fpl.needs_refresh([old], {"finished_ids": [1]}, now))
        self.assertTrue(fpl.needs_refresh([old], {"finished_ids": []}, now))
        self.assertTrue(fpl.needs_refresh([old, recent], {"finished_ids": [1, 2]}, now))


if __name__ == "__main__":
    unittest.main()
