import json

try:
    with open('icons.json') as f:
        _data = json.load(f)
    for _k, _v in _data.items():
        globals()[_k] = _v
except Exception as e:
    print('icons: failed to load icons.json:', e)
