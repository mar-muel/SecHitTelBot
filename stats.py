import json
import os
from config import STATS

_data: dict = {}

def _defaults() -> dict:
    return {
        "libwin_policies": 0, "libwin_kill": 0,
        "fascwin_policies": 0, "fascwin_hitler": 0,
        "cancelled": 0, "groups": [],
    }

def load():
    global _data
    if os.path.exists(STATS):
        with open(STATS, 'r') as f:
            _data = json.load(f)
    else:
        _data = _defaults()
        save()

def save():
    with open(STATS, 'w') as f:
        json.dump(_data, f)

def get() -> dict:
    return _data
