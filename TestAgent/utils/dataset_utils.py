from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass(frozen=True)
class DatasetLoader:
    dataset_name: str
    # 项目根目录
    dataset_root: Path
    # 源码目录 Java为 dataset_root/src/main/java
    sut_root: Path
    srs: str
    uml_class: str
    uml_sequence: str
    architecture_design: str
    language: str
    test_root:str


def load_dataset(
        dataset_name: str,
        *,
        encoding: str = "utf-8",
        strict: bool = True,
) -> DatasetLoader:

    global_prefix = Path(os.environ.get("DATASET_ROOT"))
    dataset_root = Path(global_prefix).expanduser().resolve() / dataset_name
    config_path = dataset_root / "config.json"

    # 读取并解析 config.json
    try:
        config_obj: Dict[str, Any] = json.loads(config_path.read_text(encoding=encoding))
    except FileNotFoundError:
        raise FileNotFoundError(f"config.json not found: {config_path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {config_path}: {e}") from e

    # 取 srs / UML_class 的相对路径
    srs_rel = config_obj.get("srs")
    uml_class_rel = config_obj.get("uml_class")
    uml_sequence_rel = config_obj.get("uml_sequence")
    architecture_design_rel = config_obj.get("architecture_design")
    sut=config_obj.get("sut_root")
    language = config_obj.get("language")

    if strict:
        if not srs_rel:
            raise KeyError(f'Missing or empty key "PRD" in {config_path}')
        if not uml_class_rel:
            raise KeyError(f'Missing or empty key "UML_class" in {config_path}')
        if not uml_sequence_rel:
            raise KeyError(f'Missing or empty key "UML_sequence" in {config_path}')
        if not architecture_design_rel:
            raise KeyError(f'Missing or empty key "architecture_design" in {config_path}')

    srs_path = (dataset_root / srs_rel).resolve() if srs_rel else (dataset_root / "MISSING_PRD")
    uml_class_path = (dataset_root / uml_class_rel).resolve() if uml_class_rel else (dataset_root / "MISSING_UML_class")
    uml_sequence_path = (dataset_root / uml_sequence_rel).resolve() if uml_sequence_rel else (
            dataset_root / "MISSING_UML_class")
    architecture_design_path = (dataset_root / architecture_design_rel).resolve() if architecture_design_rel else (
            dataset_root / "MISSING_Architecture_Design")
    if language=='java':
        test_root = dataset_root / "src/test/java"
        sut_root = dataset_root / "src/main/java"
    else:
        test_root = dataset_root / "tests"
        sut_root = dataset_root / sut

    # 读取文件内容
    def _read_text(p: Path) -> str:
        if p.exists():
            return p.read_text(encoding=encoding)
        if strict:
            raise FileNotFoundError(f"File not found: {p}")
        return ""

    srs_text = _read_text(srs_path)
    uml_class_text = _read_text(uml_class_path)
    uml_sequence_text = _read_text(uml_sequence_path)
    architecture_design_text = _read_text(architecture_design_path)

    return DatasetLoader(
        dataset_name=dataset_name,
        dataset_root=dataset_root,
        srs=srs_text,
        uml_class=uml_class_text,
        uml_sequence=uml_sequence_text,
        architecture_design=architecture_design_text,
        sut_root=sut_root,
        language=language,
        test_root=str(test_root)
    )


# ---- 使用示例 ----
if __name__ == "__main__":
    docs = load_dataset(
        "readtime",
        strict=True,
    )
    print(docs.test_root)


