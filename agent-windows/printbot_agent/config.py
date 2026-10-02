"""Persistent settings in %APPDATA%/PrintBotAgent/config.json."""
import json
import os
from dataclasses import asdict, dataclass
from typing import Optional


def config_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "PrintBotAgent")
    os.makedirs(path, exist_ok=True)
    return path


@dataclass
class Settings:
    server_url: Optional[str] = None
    token: Optional[str] = None
    agent_name: Optional[str] = None
    system_printers_color: bool = True  # what to report for OS printers that don't say
    path: Optional[str] = None

    @property
    def is_paired(self) -> bool:
        return bool(self.server_url and self.token)

    @classmethod
    def load(cls, path: Optional[str] = None) -> "Settings":
        path = path or os.path.join(config_dir(), "config.json")
        s = cls(path=path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                if k != "path" and hasattr(s, k):
                    setattr(s, k, v)
        except (OSError, ValueError):
            pass
        return s

    def save(self) -> None:
        data = asdict(self)
        data.pop("path", None)
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.path)

    def clear_pairing(self) -> None:
        self.token = None
        self.agent_name = None
        self.save()
