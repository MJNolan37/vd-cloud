from datetime import datetime, timezone
import hashlib
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from src.atlas_dashboard import build_charts, render_dashboard


class DashboardTests(unittest.TestCase):
    def metrics(self):
        n=60
        frame=pd.DataFrame({"Price_Index":np.linspace(100,150,n),
                            "Realized_Vol":np.linspace(.4,.9,n),
                            "Dispersion_Proxy":np.linspace(.0001,.0005,n),
                            "Correlation_vs_QQQ":1-np.linspace(.0001,.0005,n),
                            "Rolling_Volume":np.linspace(40e6,60e6,n),
                            "Vol_Bucket":["Low","Medium","High","Very High"]*15,
                            "Disp_Bucket":["Very Low","Low","Medium","High"]*15,
                            "Zone":["descriptive"]*n},index=pd.bdate_range("2026-01-02",periods=n))
        frame.loc[frame.index[:20],"Disp_Bucket"]=np.nan
        return frame

    def test_latest_marker_and_recent_trail_preserve_observations(self):
        frame=self.metrics();original=frame.copy(deep=True)
        charts=build_charts(frame)
        state=charts['state']
        self.assertEqual(state.data[0].mode,'markers')
        self.assertEqual(len(state.data[0].x),40)
        self.assertEqual(len(state.data),3)
        self.assertEqual(state.data[1].mode,'lines+markers')
        self.assertTrue(all(not trace.marker.showscale for trace in state.data))
        self.assertEqual(len(state.data[1].x),20)
        np.testing.assert_array_equal(state.data[1].x,frame.Realized_Vol.iloc[-20:].to_numpy())
        np.testing.assert_array_equal(state.data[1].y,frame.Dispersion_Proxy.iloc[-20:].to_numpy())
        self.assertEqual(state.data[-1].marker.symbol,'diamond')
        self.assertAlmostEqual(state.data[-1].x[0],frame.Realized_Vol.iloc[-1])
        self.assertAlmostEqual(state.data[-1].y[0],frame.Dispersion_Proxy.iloc[-1])
        pd.testing.assert_frame_equal(frame,original)

    def test_heatmap_denominator_excludes_uncalibrated_days(self):
        charts=build_charts(self.metrics())
        heat=np.asarray(charts['heatmap'].data[0].z)
        self.assertAlmostEqual(heat.sum(),100.)
        np.testing.assert_array_equal(np.diag(heat),[25.]*4)
        self.assertEqual(len(charts['volatility'].data),1)
        self.assertEqual(len(charts['distance'].data),1)

    def test_snapshot_generation_time_stays_stable_until_content_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'index.html'
            first=datetime(2026,10,14,4,0,tzinfo=timezone.utc)
            second=datetime(2026,10,15,4,0,tzinfo=timezone.utc)
            frame=self.metrics()
            render_dashboard(frame,'TQQQ','QQQ',.5,path,generated_at=first)
            initial=hashlib.sha256(path.read_bytes()).hexdigest()
            render_dashboard(frame,'TQQQ','QQQ',.5,path,generated_at=second)
            self.assertEqual(initial,hashlib.sha256(path.read_bytes()).hexdigest())
            page=path.read_text(encoding='utf-8')
            self.assertIn('13 Oct 2026, 09:00 PM PDT',page)
            changed=frame.copy();changed.iloc[-1,0]=151
            render_dashboard(changed,'TQQQ','QQQ',.51,path,generated_at=second)
            self.assertNotEqual(initial,hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertIn('14 Oct 2026, 09:00 PM PDT',path.read_text(encoding='utf-8'))

    def test_self_contained_page_with_data_disclosure_and_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'index.html'
            render_dashboard(self.metrics(),'TQQQ','QQQ',.5,path)
            page=path.read_text(encoding='utf-8')
            self.assertEqual(page.count('<section class="card'),6)
            self.assertIn('not real-time quotes',page)
            self.assertIn('Updated manually',page)
            self.assertIn('Reset all charts',page)
            self.assertIn('zoomIn2d',page)
            self.assertIn('zoomOut2d',page)
            self.assertNotIn('<script src=',page)
            self.assertNotIn('scale(0.9)',page)
            self.assertIn('width=device-width',page)
            import re
            sections=re.findall(r'<section\b.*?</section>',page,flags=re.S)
            self.assertEqual(len(sections),6)
            self.assertTrue(all('TQQQ' in section for section in sections))
            self.assertIn('Gray dots = earlier this year',page)
            self.assertIn('Teal trail = recent 20 observations',page)
            self.assertIn('White diamond = latest, drawn over the trail’s last point. Hover for dates.',page)
            self.assertIn('stock splits and distributions',page)
            self.assertIn('a reading of 150',page)
            self.assertIn('25 of every 100 included days',page)
            self.assertIn('not a 40% gain or loss',page)
            self.assertIn('not the direction of TQQQ’s price',page)
            self.assertIn('50 million shares each day',page)

    def test_header_states_and_heatmap_definitions_follow_calculations(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'index.html'
            frame=self.metrics();frame.loc[frame.index[-1],'Zone']='Lower volatility / low correlation distance'
            render_dashboard(frame,'TQQQ','QQQ',.5,path)
            page=path.read_text(encoding='utf-8')
            self.assertIn('<strong>Lower volatility · low correlation distance</strong>',page)
            self.assertIn('volatility of 80% or more is high',page)
            self.assertIn('>Year to date</button>',page)
            self.assertNotIn('Full year',page)
            self.assertIn('20-day annualized volatility',page)
            self.assertIn('20-day correlation with QQQ',page)
            self.assertIn('The last adjusted close of 2025 is then set to 100',page)
            self.assertIn('Low up to and including 40%; Medium above 40% to 70%; High above 70% to 100%; Very High above 100%',page)
            self.assertIn('Included: 40 of 60 days',page)
            self.assertIn('20 days without 20 earlier observations this year are excluded',page)
            self.assertIn('(here Very Low 25% · Low 25% · Medium 25% · High 25%)',page)
            self.assertIn("'yaxis.range'",page)
            frame.loc[frame.index[-1],'Zone']='Uncalibrated'
            render_dashboard(frame,'TQQQ','QQQ',.5,path)
            self.assertIn('Uncalibrated (needs 20 earlier observations this year)',path.read_text(encoding='utf-8'))

    def test_heatmap_rows_show_right_closed_volatility_bands(self):
        heat=build_charts(self.metrics())['heatmap'].data[0]
        self.assertEqual(list(heat.y),['Low ≤40%','Medium 40–70%','High 70–100%','Very High >100%'])


if __name__=='__main__':unittest.main()
