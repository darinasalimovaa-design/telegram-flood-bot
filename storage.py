import json
from pathlib import Path
from typing import Any, Dict

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
APP_FILE = DATA_DIR / "applications.json"
CONFIG_FILE = BASE_DIR / "config.json"
LOG_FILE = BASE_DIR / "bot.log"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        write_json(path, default)
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_config() -> Dict[str, Any]:
    return read_json(
        CONFIG_FILE,
        {
            "main_admin_id": 0,
            "admin_group_id": 0,
            "chats": {
                "chat1": {"title": "Chat 1", "info_url": "", "chat_id": 0, "member_limit": 60},
                "chat2": {"title": "Chat 2", "info_url": "", "chat_id": 0, "member_limit": 60},
            },
        },
    )


def load_data() -> Dict[str, Any]:
    return read_json(
        APP_FILE,
        {
            "applications": [],
            "reservations": [],
            "invite_links": [],
            "pending_joins": [],
            "counters": {"application_id": 0, "reservation_id": 0, "link_id": 0},
        },
    )


def save_data(data: Dict[str, Any]) -> None:
    write_json(APP_FILE, data)


def next_id(data: Dict[str, Any], key: str) -> int:
    data["counters"][key] += 1
    save_data(data)
    return data["counters"][key]
