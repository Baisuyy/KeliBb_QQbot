import json
import os
NAMES_FILE = "/opt/qqbot/user_names.json"
def load_names():
    if os.path.exists(NAMES_FILE):
        with open(NAMES_FILE, 'r') as f:
            return json.load(f)
    return {}
def save_names(names):
    with open(NAMES_FILE, 'w') as f:
        json.dump(names, f, indent=2, ensure_ascii=False)
def get_user_name(user_id):
    names = load_names()
    return names.get(str(user_id), None)
def set_user_name(user_id, name):
    names = load_names()
    names[str(user_id)] = name
    save_names(names)
