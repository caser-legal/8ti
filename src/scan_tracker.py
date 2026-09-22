import json
from datetime import datetime
from pathlib import Path
from typing import Optional

class SyncTracker:
    def __init__(self, state_file="logs/scan_state.json"):
        self.state_file = Path(state_file)
        self.state = self.load_state()
    
    def load_state(self):
        state = {
            "last_scan_start": None,
            "last_scan_end": None,
            "last_scan_status": "never",
            "total_scans": 0,
            "feeds_processed": 0,
            "docs_upserted": 0,
            "feeds_skipped": 0,
            "last_error": None,
            "shard_index": 0,
            "shard_count": 1,
        }
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    loaded = json.load(f)
                    state.update(loaded)
                    # Migrate old keys
                    if "total_syncs" in loaded:
                        state["total_scans"] = loaded["total_syncs"]
            except:
                pass
        return state
    
    def save_state(self):
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=2)
    
    def start_scan(self, shard_index: int = 0, shard_count: int = 1):
        self.state["last_scan_start"] = datetime.now().isoformat()
        self.state["last_scan_status"] = "running"
        self.state["shard_index"] = shard_index
        self.state["shard_count"] = shard_count
        self.save_state()
    
    def end_scan(self, feeds_ok=0, skipped=0, docs_upserted=0, error=None, shard_index: Optional[int] = None, shard_count: Optional[int] = None):
        self.state["last_scan_end"] = datetime.now().isoformat()
        self.state["last_scan_status"] = "error" if error else "completed"
        self.state["total_scans"] += 1
        self.state["feeds_processed"] = feeds_ok
        self.state["feeds_skipped"] = skipped
        self.state["docs_upserted"] = docs_upserted
        self.state["last_error"] = error
        if shard_index is not None:
            self.state["shard_index"] = shard_index
        if shard_count is not None:
            self.state["shard_count"] = shard_count
        self.save_state()
    
    def get_status(self):
        self.state = self.load_state()
        return self.state.copy()

tracker = SyncTracker()
