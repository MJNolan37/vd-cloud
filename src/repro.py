"""Local CSV download cache with hashes and explicit offline/refresh behavior."""
import hashlib
import json
import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_RECORDS = []


def _read_cache(csv_path, levels):
    # round_trip parsing restores every float exactly as written; pandas' default
    # parser can differ from the written value by one unit in the last place.
    return pd.read_csv(csv_path, header=list(range(levels)) if levels > 1 else 0,
                       index_col=0, parse_dates=True, float_precision="round_trip")


def download(tickers, start=None, end=None, auto_adjust=True, progress=False, **kwargs):
    specification = {"tickers": list(tickers) if not isinstance(tickers, str) else [tickers],
                     "start": start, "end": end, "auto_adjust": auto_adjust, **kwargs}
    key = hashlib.sha256(json.dumps(specification, sort_keys=True).encode()).hexdigest()[:20]
    directory = ROOT / "data"
    csv_path, metadata_path = directory / f"{key}.csv", directory / f"{key}.json"
    offline = os.environ.get("VD_CLOUD_OFFLINE") == "1"
    refresh = os.environ.get("VD_CLOUD_REFRESH") == "1"
    if offline and refresh:
        raise ValueError("Offline and refresh modes are mutually exclusive.")
    if csv_path.exists() and metadata_path.exists() and not refresh:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if hashlib.sha256(csv_path.read_bytes()).hexdigest() != metadata["sha256"]:
            raise ValueError(f"Cached data hash mismatch: {csv_path.name}")
        source = "cache"
    else:
        if offline:
            raise FileNotFoundError(f"No cached download for {specification}; run online once first.")
        import yfinance as yf
        raw = yf.download(tickers, start=start, end=end, auto_adjust=auto_adjust,
                          progress=progress, **kwargs)
        from .vdcloud import adjusted_close
        adjusted_close(raw, specification["tickers"])
        directory.mkdir(exist_ok=True)
        raw.to_csv(csv_path)
        metadata = {"specification": specification, "column_levels": raw.columns.nlevels,
                    "downloaded_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
                    "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
                    "first_date": str(raw.index.min()), "last_date": str(raw.index.max()),
                    "missing_counts": {str(k): int(v) for k, v in raw.isna().sum().items()}}
        metadata_path.write_text(json.dumps(metadata, indent=2)+"\n", encoding="utf-8")
        source = "download"
    # Always analyze the parsed cache, so a first online run and later offline
    # replays receive identical inputs.
    raw = _read_cache(csv_path, metadata["column_levels"])
    DATA_RECORDS.append({"cache_file": csv_path.name, "source": source, **metadata})
    return raw
