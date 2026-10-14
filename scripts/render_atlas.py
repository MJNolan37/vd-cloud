"""Render the Atlas dashboard from an already verified exported metrics table.

    python scripts/render_atlas.py

This does not download data or rerun the research calculations.
"""
from pathlib import Path
import sys

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.atlas_dashboard import render_dashboard


def main():
    path=ROOT/'results/atlas_observatory/metrics.csv'
    metrics=pd.read_csv(path,index_col='date',parse_dates=True,float_precision='round_trip')
    output=ROOT/'atlas/index.html'
    render_dashboard(metrics,'TQQQ','QQQ',float(metrics.Price_Index.iloc[-1]/100-1),output,
                     snapshot_path=ROOT/'results/atlas_dashboard_snapshot.json')
    print(f'Updated dashboard: {output}')
    print(f'Latest market observation retained: {metrics.index[-1].date()}')


if __name__=='__main__':main()
