import json
from pathlib import Path
from typing import Any, Optional


METADATA_PATH = Path("memory") / "working_memory" / "metadata.json"


def _load_metadata(metadata_path: Path = METADATA_PATH) -> dict:
    """
    读取 metadata.json，若文件不存在则返回空字典；
    若目录不存在则自动创建；
    若文件内容损坏则返回空字典。
    """
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    if not metadata_path.exists():
        return {}

    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_metadata(data: dict, metadata_path: Path = METADATA_PATH) -> None:
    """
    将字典写入 metadata.json。
    """
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_metadata_value(key: str, metadata_path: Path = METADATA_PATH) -> Optional[Any]:
    """
    根据键读取值。
    如果键不存在，返回 None。
    """
    data = _load_metadata(metadata_path)
    return data.get(key)


def set_metadata_value(key: str, value: Any, metadata_path: Path = METADATA_PATH) -> None:
    """
    写入键值对：
    - 如果 key 已存在，则修改
    - 如果 key 不存在，则插入
    """
    data = _load_metadata(metadata_path)
    data[key] = value
    _save_metadata(data, metadata_path)