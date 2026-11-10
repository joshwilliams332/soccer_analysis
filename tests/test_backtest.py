import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import backtest  # noqa: E402
import model  # noqa: E402

ODDS = """Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,PSCH,PSCD,PSCA,PC>2.5,PC<2.5,BFECH,BFECD,BFECA,AvgCH,AvgCD,AvgCA
E0,21/08/2026,20:00,Man United,Tottenham,2,1,2.0,3.5,4.0,1.9,2.0,,,,2.1,3.4,3.9
E0,22/08/2026,15:00,Hull,Coventry,0,0,,,,,,2.5,3.2,3.0,2.4,3.1,3.1
"""


class TestBacktest(unittest.TestCase):
    def test_devig(self):
        p = backtest.devig([2.0, 3.5, 4.0])
        self.assertAlmostEqual(sum(p), 1.0)
        self.assertGreater(p[0], p[2])
        self.assertIsNone(backtest.devig([2.0, None, 4.0]))

    def test_odds_join_and_fallback(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "odds.csv")
        with open(path, "w") as fh:
            fh.write(ODDS)
        odds = backtest.load_odds(path)
        ms = [{"kickoff": "2026-08-21T19:00:00Z", "home_name": "Man Utd", "away_name": "Spurs"},
              {"kickoff": "2026-08-22T14:00:00Z", "home_name": "Hull City", "away_name": "Coventry City"}]
        self.assertEqual(backtest.attach_odds(ms, odds), 2)
        self.assertEqual(ms[0]["mkt"]["x12_src"], "PSC")
        self.assertIsNotNone(ms[0]["mkt"]["over"])
        self.assertEqual(ms[1]["mkt"]["x12_src"], "BFEC")  # no Pinnacle close: Betfair Exchange

    def test_priors(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "priors.json")
        with open(path, "w") as fh:
            json.dump({"teams": {"Arsenal": {"att": 1.3, "def": 0.6}}}, fh)
        pr = model.load_priors({1: "Arsenal", 2: "Coventry City"}, path)
        self.assertEqual(pr[1]["att"], 1.3)
        self.assertEqual((pr[2]["att"], pr[2]["def"]), model.PROMOTED)  # not in last season: promoted
        self.assertIsNone(model.load_priors({1: "Arsenal"}, os.path.join(d, "missing.json")))

    def test_fit_uses_goal_scale(self):
        ms = [{"home": 1, "away": 2, "hg": 1, "ag": 1, "hxg": 3.0, "axg": 3.0}] * 5
        _, avg = model.fit(ms)
        self.assertEqual(avg, {"home": 1.0, "away": 1.0})  # xG ran high; projections land on goals


if __name__ == "__main__":
    unittest.main()
