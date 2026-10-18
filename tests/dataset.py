"""Most tests read the team dataset (a teammate's price contract and news archive), which is not in this repo.
Point DATA_DIR (and NEWS_FEED for the GPU feed) at a local copy to run them; otherwise they are skipped."""
import unittest

from hardware_signal.config import Settings

HAS_DATASET = (Settings.from_env().data_dir / "prices/retail-and-cloud-price-contract.json").exists()
requires_dataset = unittest.skipUnless(HAS_DATASET, "needs the team dataset: set DATA_DIR (see README)")

from hardware_signal.article_cache import CACHE_DIR
from hardware_signal.config import ROOT

requires_article_cache = unittest.skipUnless(CACHE_DIR.exists() and any(CACHE_DIR.glob("*.json")),
                                             "needs a fetched article cache (OUTPUT_DIR/article_cache)")
requires_stock_data = unittest.skipUnless((ROOT / "dataset/ram_gpu_stocks/data/processed").exists(),
                                          "needs dataset/ram_gpu_stocks (stock-news research track)")
