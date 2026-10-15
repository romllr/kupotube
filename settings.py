"""Per-user data, never stored next to the executable or in the checkout."""
import os
from pathlib import Path


def data_dir():
    root = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local' / 'share')) / 'Kupotube'
    return root


def cookie_path():
    return data_dir() / 'session-cookies.txt'


def get_preferences():
    import json
    try:
        saved = json.loads((data_dir() / 'preferences.json').read_text(encoding='utf-8'))
        return {'sound': saved.get('sound') is not False}
    except (OSError, ValueError, AttributeError):
        return {'sound': True}


def set_sound(enabled):
    import json
    root = data_dir()
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / 'preferences.tmp'
    temporary.write_text(json.dumps({'sound': bool(enabled)}), encoding='utf-8')
    temporary.replace(root / 'preferences.json')
