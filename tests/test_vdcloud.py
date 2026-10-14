import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

STRICT=os.environ.get("VD_CLOUD_STRICT_TESTS")=="1"

from src.vdcloud import (adjusted_close, price_returns, rolling_zscore, build_cloud,
                        forward_return, purge_cross_boundary, persistence_confirmed,
                        prior_quantile_buckets, classify_zone, monte_carlo_p,
                        label_null_test, bucket_inference)


class CalculationTests(unittest.TestCase):
    def test_missing_price_does_not_create_zero_or_bridge_return(self):
        frame=pd.DataFrame({"A":[100., np.nan, 110., 121.]})
        result=price_returns(frame).A
        self.assertTrue(result.iloc[:3].isna().all())
        self.assertAlmostEqual(result.iloc[3], .1)
        self.assertEqual(len(result),len(frame))

    def test_download_layouts_and_missing_ticker(self):
        index=pd.date_range("2020-01-01",periods=3)
        raw=pd.DataFrame([[100.,200.]]*3,index=index,
                         columns=pd.MultiIndex.from_tuples([("Close","A"),("Close","B")]))
        expected=adjusted_close(raw,["A","B"])
        swapped=raw.copy(); swapped.columns=swapped.columns.swaplevel()
        pd.testing.assert_frame_equal(expected,adjusted_close(swapped,["A","B"]))
        with self.assertRaises(ValueError): adjusted_close(raw,["A","C"])
        with self.assertRaises(ValueError): adjusted_close(raw.iloc[[1,0]],["A","B"])

    def test_download_duplicate_empty_and_invalid(self):
        frame=pd.DataFrame({"Close":[100.,101.]},index=pd.to_datetime(["2020-01-01"]*2))
        with self.assertRaises(ValueError): adjusted_close(frame,["A"])
        for values in ([np.nan,np.nan],[100.,0.],[100.,np.inf]):
            frame=pd.DataFrame({"Close":values},index=pd.date_range("2020-01-01",periods=2))
            with self.assertRaises(ValueError): adjusted_close(frame,["A"])

    def test_forward_return_endpoint_and_unavailable_tail(self):
        r=pd.Series([np.nan,.10,-.05,.20,.03])
        result=forward_return(r,2)
        self.assertAlmostEqual(result.iloc[0],1.10*.95-1)
        self.assertAlmostEqual(result.iloc[1],.95*1.20-1)
        self.assertTrue(result.iloc[-2:].isna().all())
        with self.assertRaises(ValueError): forward_return(r,0)

    def test_forward_return_missing_outcome(self):
        result=forward_return(pd.Series([.01,.02,np.nan,.04,.05]),2)
        self.assertTrue(result.iloc[:2].isna().all())
        self.assertAlmostEqual(result.iloc[2],1.04*1.05-1)

    def test_purging_uses_outcome_endpoint_per_horizon(self):
        index=pd.bdate_range("2020-12-01",periods=110)
        returns=pd.Series(.01,index=index)
        forward=pd.DataFrame({f"fwd_{h}d":forward_return(returns,h) for h in (5,21,63)})
        end=index[70]
        result=purge_cross_boundary(forward,end)
        for h in (5,21,63):
            self.assertEqual(int(result.loc[:end,f"fwd_{h}d"].isna().sum()),h)
            self.assertTrue(pd.notna(result.iloc[70-h][f"fwd_{h}d"]))
            pd.testing.assert_series_equal(result.loc[index[71]:,f"fwd_{h}d"],forward.loc[index[71]:,f"fwd_{h}d"])

    def test_cloud_requires_both_spans_and_ties_are_inside(self):
        constant=pd.Series(1.,index=pd.bdate_range("2020-01-01",periods=80))
        cloud=build_cloud(constant)
        self.assertTrue(cloud.regime_state.iloc[:51].isna().all())
        self.assertTrue(cloud.regime_state.iloc[51:].eq("inside_cloud").all())
        increasing=build_cloud(pd.Series(np.arange(80.)))
        self.assertTrue(increasing.regime_state.iloc[51:].eq("above_cloud").all())
        decreasing=build_cloud(pd.Series(-np.arange(80.)))
        self.assertTrue(decreasing.regime_state.iloc[51:].eq("below_cloud").all())

    def test_future_changes_do_not_relabel_past(self):
        s=pd.Series(np.sin(np.arange(160)/5))
        changed=s.copy();changed.iloc[100:]=1000
        pd.testing.assert_frame_equal(build_cloud(s).iloc[:100],build_cloud(changed).iloc[:100])
        pd.testing.assert_series_equal(rolling_zscore(s,20).iloc[:100],rolling_zscore(changed,20).iloc[:100])

    def test_constant_zscore_is_missing(self):
        self.assertTrue(rolling_zscore(pd.Series([1.]*20),5).isna().all())

    def test_persistence_only_confirms_after_enough_past_observations(self):
        s=pd.Series(["above_cloud"]*3+["below_cloud"]*3)
        self.assertEqual(persistence_confirmed(s,3).tolist(),
                         ["unconfirmed","unconfirmed","above_cloud","unconfirmed","unconfirmed","below_cloud"])
        s.iloc[1]=np.nan
        self.assertEqual(persistence_confirmed(s,3).iloc[2],"unconfirmed")

    def test_quantile_thresholds_are_prior_data_and_handle_ties(self):
        labels=["a","b","c","d"]
        s=pd.Series(np.arange(40.));changed=s.copy();changed.iloc[20:]=1000
        pd.testing.assert_series_equal(prior_quantile_buckets(s,labels,5).iloc[:20],prior_quantile_buckets(changed,labels,5).iloc[:20])
        constant=prior_quantile_buckets(pd.Series([1.]*30),labels,5)
        self.assertTrue(constant.iloc[:5].isna().all())
        self.assertTrue(constant.iloc[5:].eq("a").all())

    def test_uncalibrated_zone_and_exact_boundary(self):
        self.assertEqual(classify_zone(.8,.2,np.nan),"Uncalibrated")
        self.assertEqual(classify_zone(.8,.2,.2),"High volatility / high correlation distance")

    def test_plus_one_p_cannot_be_zero(self):
        self.assertAlmostEqual(monte_carlo_p([0.,.01,.02],1.),.25)
        self.assertEqual(monte_carlo_p([1.,2.,3.],1.),1.)

    def test_label_tests_reproducible_and_reject_internal_gaps(self):
        frame=pd.DataFrame({"regime":["a"]*10+["b"]*10+["a"]*10+["b"]*10,
                            "return":np.linspace(-.1,.1,40)})
        for method in ("shuffle","circular_shift"):
            first=label_null_test(frame,"regime","return","a",30,42,method,5)
            self.assertEqual(first,label_null_test(frame,"regime","return","a",30,42,method,5))
            self.assertEqual(first["bucket_n"],20)
            self.assertGreaterEqual(first["empirical_two_sided_p_value"],1/31)
        frame.loc[20,"return"]=np.nan
        with self.assertRaises(ValueError): label_null_test(frame,"regime","return","a")

    # Set VD_CLOUD_STRICT_TESTS=1 (as CI does) to make a missing statsmodels fail instead of skip.
    @unittest.skipUnless(STRICT or importlib.util.find_spec("statsmodels"),"statsmodels unavailable; set VD_CLOUD_STRICT_TESTS=1 to require it")
    def test_hac_matches_full_chronological_regression(self):
        import statsmodels.api as sm
        rng=np.random.default_rng(10)
        indicator=np.tile(np.repeat([0.,1.],10),20)
        y=pd.Series(.01*indicator+rng.normal(0,.02,len(indicator)))
        frame=pd.DataFrame({"regime":np.where(indicator,"a","b"),"return":y})
        actual=bucket_inference(frame,"regime","return","a",20)
        expected=sm.OLS(y,sm.add_constant(indicator)).fit(cov_type="HAC",cov_kwds={"maxlags":20})
        self.assertAlmostEqual(actual["hac_t_stat"],float(expected.tvalues.iloc[1]))
        frame.loc[100,"return"]=np.nan
        with self.assertRaises(ValueError): bucket_inference(frame,"regime","return","a",20)

    def test_cached_csv_roundtrip_and_hash_verification(self):
        from src import repro
        specification={"tickers":["A","B"],"start":"2020-01-01","end":"2020-02-01","auto_adjust":True}
        import hashlib
        key=hashlib.sha256(json.dumps(specification,sort_keys=True).encode()).hexdigest()[:20]
        raw=pd.DataFrame([[100.,200.],[101.,202.]],index=pd.date_range("2020-01-01",periods=2),
                         columns=pd.MultiIndex.from_tuples([("Close","A"),("Close","B")]))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/"data").mkdir();path=root/"data"/f"{key}.csv";raw.to_csv(path)
            metadata={"column_levels":2,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
            (root/"data"/f"{key}.json").write_text(json.dumps(metadata))
            with patch.object(repro,"ROOT",root),patch.dict("os.environ",{"VD_CLOUD_OFFLINE":"1","VD_CLOUD_REFRESH":"0"}):
                result=repro.download(["A","B"],start="2020-01-01",end="2020-02-01")
                np.testing.assert_array_equal(result.to_numpy(),raw.to_numpy())
                path.write_text(path.read_text()+"\n")
                with self.assertRaises(ValueError): repro.download(["A","B"],start="2020-01-01",end="2020-02-01")

    def test_first_download_and_offline_replay_return_identical_frames(self):
        import os
        import types
        from src import repro
        index=pd.DatetimeIndex(pd.bdate_range("2020-01-01",periods=40),name="Date")
        columns=pd.MultiIndex.from_product([["Close","Volume"],["A","B"]],names=["Price","Ticker"])
        values=np.random.default_rng(7).uniform(50,150,(40,4))*1.000000001234567
        raw=pd.DataFrame(values,index=index,columns=columns)
        raw.iloc[3,0]=np.nan
        fake=types.ModuleType("yfinance");fake.download=lambda *a,**k: raw.copy()
        with tempfile.TemporaryDirectory() as directory, patch.dict("sys.modules",{"yfinance":fake}), \
                patch.object(repro,"ROOT",Path(directory)):
            with patch.dict(os.environ,{"VD_CLOUD_OFFLINE":"0","VD_CLOUD_REFRESH":"0"}):
                first=repro.download(["A","B"],start="2020-01-01",end="2020-03-01")
            with patch.dict(os.environ,{"VD_CLOUD_OFFLINE":"1","VD_CLOUD_REFRESH":"0"}):
                replay=repro.download(["A","B"],start="2020-01-01",end="2020-03-01")
        pd.testing.assert_frame_equal(first,replay)
        # Exact float round trip: the cache must not perturb prices by one ULP.
        np.testing.assert_array_equal(replay.to_numpy(),raw.to_numpy())

    def test_adjusted_close_preferred_and_volume_selected_from_either_layout(self):
        from src.vdcloud import select_field
        index=pd.date_range("2020-01-01",periods=2)
        raw=pd.DataFrame([[90.,100.,5.],[91.,101.,0.]],index=index,
                         columns=pd.MultiIndex.from_tuples([("Adj Close","A"),("Close","A"),("Volume","A")]))
        self.assertEqual(adjusted_close(raw,["A"]).A.tolist(),[90.,91.])
        swapped=raw.copy();swapped.columns=swapped.columns.swaplevel()
        self.assertEqual(adjusted_close(swapped,["A"]).A.tolist(),[90.,91.])
        self.assertEqual(select_field(swapped,("Volume",),["A"]).A.tolist(),[5.,0.])
        with self.assertRaises(ValueError): select_field(raw,("Volume",),["A","B"])

    def test_dependency_record_does_not_require_pip(self):
        from scripts.reproduce import installed_distributions
        record=installed_distributions()
        self.assertTrue(any(line.lower().startswith("numpy==") for line in record))
        names=[line.split("==")[0].lower() for line in record]
        self.assertEqual(names,sorted(names))

    def test_notebook_code_compiles_and_uses_shared_ingestion(self):
        root=Path(__file__).resolve().parents[1]
        for path in [*root.glob("notebooks/*.ipynb"),*root.glob("atlas/*.ipynb")]:
            nb=json.loads(path.read_text(encoding="utf-8"))
            combined=""
            for i,cell in enumerate(nb["cells"]):
                if cell["cell_type"]=="code":
                    text="".join(cell["source"]);compile(text,f"{path.name}:{i}","exec");combined+=text
            self.assertIn("price_returns(prices)",combined)
            self.assertNotIn("pct_change()",combined)

    def test_full_chronological_notebook_on_synthetic_prices(self):
        import contextlib
        import io
        import types
        root=Path(__file__).resolve().parents[1]
        index=pd.bdate_range("2015-01-01","2026-05-29")
        tickers=["EFA","URTH","EWJ","EWU","EWG","EWQ","EWI","EWP","EWN","EWD","EWL","EWC","EWA","EWO","EWK"]
        rng=np.random.default_rng(42)
        returns=rng.normal(.0002,.01,(len(index),len(tickers)))
        raw=pd.DataFrame(100*np.cumprod(1+returns,axis=0),index=index,
                         columns=pd.MultiIndex.from_product([["Close"],tickers]))
        nb=json.loads((root/"notebooks/03_temporal_holdout_clean.ipynb").read_text(encoding="utf-8"))
        namespace={"__name__":"__main__"}
        with patch.dict("sys.modules",{"yfinance":types.ModuleType("yfinance")}),patch("src.repro.download",return_value=raw),contextlib.redirect_stdout(io.StringIO()):
            for i,cell in enumerate(nb["cells"]):
                if cell["cell_type"]=="code":
                    exec(compile("".join(cell["source"]),f"synthetic-phase3:{i}","exec"),namespace)
        self.assertEqual(len(namespace["in_sample_vs_holdout_consistency"]),56)
        end=pd.Timestamp("2020-12-31")
        for h in (5,10,21,63):
            positions=np.flatnonzero(index<=end)
            self.assertTrue(namespace["efa_fwd"].iloc[positions[-h:]][f"fwd_{h}d"].isna().all())
        raw_labels=namespace["raw_regimes"]["additive"]
        confirmed=namespace["confirmed_regimes"][("additive",5)]
        self.assertTrue(confirmed.loc[raw_labels.isna()].isna().all())

    def test_headline_counts_follow_thresholds_and_minimum_size(self):
        from scripts.reproduce import headline_counts
        frame=pd.DataFrame({"bucket_n":[100,100,5,100],"empirical_p":[.05,.2,.01,.05],
                            "hac_t_stat":[2.,2.,3.,.5],"circular_shift_p":[.05,.05,.01,.2]})
        counts=headline_counts(frame,.1,1.65,30)
        self.assertEqual(counts,{"shuffle_interesting":2,"hac_interesting":2,"circular_shift_interesting":2,"shuffle_and_hac":1})
        self.assertEqual(headline_counts(frame,.01,2.5,30)["shuffle_and_hac"],0)


if __name__=="__main__": unittest.main()
