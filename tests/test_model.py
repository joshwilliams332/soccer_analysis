import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import model  # noqa: E402


class TestModel(unittest.TestCase):
    def test_grid_sums_to_one(self):
        g = model.score_grid(1.6, 1.1)
        self.assertAlmostEqual(sum(map(sum, g)), 1.0, places=9)

    def test_probs_consistent(self):
        m = model.match_probs(1.6, 1.1)
        self.assertAlmostEqual(m["home"] + m["draw"] + m["away"], 1.0, places=9)
        self.assertGreater(m["home"], m["away"])
        for k in ("over_2_5", "btts", "home_clean_sheet", "away_clean_sheet"):
            self.assertTrue(0 < m[k] < 1, k)
        self.assertEqual(len(m["scores"]), 5)
        self.assertGreaterEqual(m["scores"][0]["p"], m["scores"][-1]["p"])

    def test_symmetric_teams_even(self):
        m = model.match_probs(1.3, 1.3)
        self.assertAlmostEqual(m["home"], m["away"], places=9)

    def test_dixon_coles_raises_draws(self):
        # negative rho moves probability onto 0-0 and 1-1
        self.assertGreater(model.match_probs(1.2, 1.2, rho=-0.1)["draw"],
                           model.match_probs(1.2, 1.2, rho=0.0)["draw"])

    def test_expected_points_range(self):
        self.assertAlmostEqual(model.expected_points(1.0, 1.0),
                               model.expected_points(1.0, 1.0))
        self.assertGreater(model.expected_points(2.5, 0.4), 2.2)
        self.assertLess(model.expected_points(0.4, 2.5), 0.4)

    def test_strengths_order_and_shrinkage(self):
        ms = []
        for i in range(10):
            ms.append({"home": "A", "away": "B", "hg": 2, "ag": 0, "hxg": 2.2, "axg": 0.5})
            ms.append({"home": "B", "away": "A", "hg": 0, "ag": 2, "hxg": 0.6, "axg": 2.0})
        s, avg = model.team_strengths(ms)
        self.assertGreater(s["A"]["att"], 1.0)
        self.assertLess(s["A"]["def"], 1.0)
        self.assertLess(s["B"]["att"], 1.0)
        # one match moves a team less than ten
        s1, _ = model.team_strengths(ms[:1])
        self.assertLess(abs(s1["A"]["att"] - 1), abs(s["A"]["att"] - 1) + 1e-9)
        lh, la = model.project("A", "B", s, avg)
        self.assertGreater(lh, la)

    def test_recency_weighting(self):
        old = [{"home": "A", "away": "B", "hg": 0, "ag": 0, "hxg": 0.3, "axg": 1.0}] * 8
        new = [{"home": "A", "away": "B", "hg": 3, "ag": 0, "hxg": 2.5, "axg": 1.0}] * 8
        s_recent_good, _ = model.team_strengths(old + new)
        s_recent_bad, _ = model.team_strengths(new + old)
        self.assertGreater(s_recent_good["A"]["att"], s_recent_bad["A"]["att"])

    def test_missing_xg_falls_back_to_goals(self):
        self.assertEqual(model.blend(None, 2), 2.0)


if __name__ == "__main__":
    unittest.main()
