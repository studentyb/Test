from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Iterator, Optional


# ---------- 1. 基础数据结构 (Feature) ----------

@dataclass(frozen=True)
class Feature:
    # === 基础元数据 (对应 JSON 中的字段) ===
    feature_id: str
    feature_name: str
    description: str
    methods: List[Dict[str, str]]
    reqs: List[Dict[str, Any]]
    dependencies: List[Dict[str, str]]

    # === 注入的上下文信息 (运行时注入，不保存回 JSON) ===
    # 1. 全局补充信息 (Global Context)
    project_supplementary: str = field(default="")

    # 2. 模块级共享知识 (Module Context)
    module_shared_context: str = field(default="")

    # 3. 模块描述
    module_desc: str = field(default="")

    def to_dict(self) -> Dict[str, Any]:
        """
        序列化为字典。
        注意：排除注入的上下文信息，保持 JSON 纯净。
        """
        return {
            "feature_id": self.feature_id,
            "feature_name": self.feature_name,
            "description": self.description,
            "methods": self.methods,
            "reqs": self.reqs,
            "dependencies": self.dependencies
        }

    def get_context_summary(self) -> str:
        """
        生成面向 LLM 的分层上下文提示 (Prompt Context)。

        结构顺序：
        1. 全局环境与补充信息 (Global)
        2. 模块背景与共享定义 (Module)
        3. 待测功能描述 (Feature)
        4. 目标 API 签名 (Target APIs)
        5. 测试逻辑与断言 (Test Oracles)
        """
        # 格式化 API 列表
        methods_lines = []
        for m in self.methods:
            sig = m.get('signature', 'N/A')
            desc = m.get('description', '')
            methods_lines.append(f"- Signature: `{sig}`\n  Functionality: {desc}")
        methods_txt = "\n".join(methods_lines) if methods_lines else "  (No signatures provided)"

        # 格式化需求列表
        reqs_lines = []
        for i, r in enumerate(self.reqs, 1):
            goal = r.get('goal', '')
            steps = r.get('steps', '')
            constraints = r.get('constraints', '')
            exceptions = r.get('exceptions', '')
            reqs_lines.append(
                f"  {i}. Goal: {goal}\n"
                f"     - Constraints: {constraints}\n"
                f"     - Steps: {steps}\n"
                f"     - Expected Results/Errors: {exceptions}"
            )
        reqs_txt = "\n".join(reqs_lines) if reqs_lines else "  (No specific requirements logic provided)"

        # 格式化外部依赖 (Mock Targets)
        deps_lines = []
        for d in self.dependencies:
            deps_lines.append(f"- Mock Target: `{d}` ")
        deps_txt = "\n".join(deps_lines) if deps_lines else "  (No external dependencies to mock)"

        # 组装最终 Prompt
        return (
            f"### 1. System Environment & Supplementary Info (Global)\n"
            f"{self.project_supplementary}\n\n"

            f"### 2. Module Context & Shared Definitions (Module-Level)\n"
            f"- **Module Responsibility**: {self.module_desc}\n"
            f"- **Shared Context (Classes/Helpers/Logic)**: \n{self.module_shared_context}\n\n"

            f"### 3. Program Under Test (PUT)\n"
            f"- **Feature Name**: `{self.feature_name}`\n"
            f"- **Description**: {self.description}\n\n"

            f"### 4. Target APIs (Code to Invoke)\n"
            f"{methods_txt}\n\n"

            f"### 5. External Dependencies (Mocks Needed)\n"
            f"{deps_txt}\n\n"

            f"### 6. Test Logic & Oracles (Assert Basis)\n"
            f"Use the following logic to derive test inputs and expected outputs:\n"
            f"{reqs_txt}"
        )


# ---------- 2. 基础数据结构 (Module) ----------

@dataclass(frozen=True)
class Module:
    module_id: str
    module_name: str
    classes: List[str]
    description: str
    features: List[Feature]

    # [关键新字段] 模块内的共享知识 (对应 JSON: shared_context)
    shared_context: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """
        返回 Module 的 dict 表示（可 JSON 序列化）
        """
        return {
            "module_id": self.module_id,
            "module_name": self.module_name,
            "classes": self.classes,
            "description": self.description,
            "shared_context": self.shared_context,  # 包含此字段
            "features": [f.to_dict() for f in self.features],
        }

    def to_json(self, *, indent: int = 2, ensure_ascii: bool = False) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=ensure_ascii)


# ---------- 3. Memory 管理类 ----------

class Memory:
    """
    管理 modules.json 的内存表示。
    负责加载 Global Info, Module Info 并注入到 Feature 中。
    """

    def __init__(self, json_path: str | Path):
        self.json_path = Path(json_path).resolve()

        # 内部状态
        self._modules: List[Module] = []
        self._project_name: str = ""
        self._project_describe: str = ""

        # [Global Context] 对应 JSON 中的 "supplementary_info"
        self._project_supplementary: str = ""

        self._raw_data: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if not self.json_path.exists():
            raise FileNotFoundError(f"JSON file not found: {self.json_path}")

        text = self.json_path.read_text(encoding="utf-8")

        # --- JSON 解析 (支持 Markdown 代码块剥离) ---
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
            if not match:
                raise ValueError(
                    f"File is not valid JSON and does not contain a ```json code block: {self.json_path}"
                )
            json_str = match.group(1).strip()
            try:
                raw = json.loads(json_str)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON inside ```json block: {e}") from e

        self._raw_data = raw

        # 1. 提取项目级信息
        self._project_name = raw.get("project_name", "")
        self._project_describe = raw.get("project_describe", "")
        # 提取全局补充信息
        self._project_supplementary = raw.get("supplementary_info", "")

        # 2. 解析 Modules
        modules_raw = raw.get("modules", [])
        if not isinstance(modules_raw, list):
            raise ValueError(f'"modules" must be a list in {self.json_path}')

        self._modules = [self._parse_module(m) for m in modules_raw]

    def _parse_module(self, data: Dict[str, Any]) -> Module:
        # 1. 提取模块级共享信息
        mod_shared_ctx = data.get("shared_context", "")
        mod_desc = data.get("description", "")

        # 2. 解析 Feature，同时注入 Global 和 Module 上下文
        features = [
            Feature(
                feature_id=f.get("feature_id", ""),
                feature_name=f.get("feature_name", ""),
                description=f.get("description", ""),
                methods=f.get("methods", []),
                reqs=f.get("reqs", []),
                dependencies=f.get("dependencies", []),

                # --- 注入上下文 (关键步骤) ---
                project_supplementary=self._project_supplementary,  # Global
                module_shared_context=mod_shared_ctx,  # Module
                module_desc=mod_desc
            )
            for f in data.get("features", [])
        ]

        return Module(
            module_id=data.get("module_id", ""),
            module_name=data.get("module_name", ""),
            classes=data.get("classes", []),
            description=mod_desc,
            features=features,
            shared_context=mod_shared_ctx  # 保存 Module 级上下文
        )

    # ---------- 对外接口 ----------

    @property
    def modules(self) -> List[Module]:
        return self._modules

    @property
    def project_name(self) -> str:
        return self._project_name

    @property
    def supplementary_info(self) -> str:
        return self._project_supplementary

    def get_module_by_name(self, module_name: str) -> Module | None:
        return next((m for m in self._modules if m.module_name == module_name), None)

    def iter_all_features(self) -> Iterator[Feature]:
        for module in self._modules:
            for feature in module.features:
                yield feature


import re


def extract_failed_fixed_pairs(log_file):

    with open(log_file, "r", encoding="utf-8") as f:
        text = f.read()

    pattern = re.compile(
        r'<<<TEST_CASE>>>\s*(.*?)\s*<<</TEST_CASE>>>\s*'
        r'<<<STATUS>>>\s*(PASS|FAIL)\s*<<</STATUS>>>\s*'
        r'(?:<<<ERROR_LOG>>>\s*(.*?)\s*<<</ERROR_LOG>>>)?',
        re.DOTALL
    )

    matches = pattern.findall(text)

    results = []

    first_failed_test = None
    first_error_log = None

    for test_case, status, error_log in matches:

        if status == "FAIL":
            if first_failed_test is None:
                first_failed_test = test_case.strip()
                first_error_log = (error_log or "").strip()

        elif status == "PASS":
            if first_failed_test is not None:
                results.append({
                    "failed_test": first_failed_test,
                    "fixed_test": test_case.strip(),
                    "error_log": first_error_log
                })

                first_failed_test = None
                first_error_log = None

    return results



# ---------- 测试代码 ----------
if __name__ == '__main__':
    # memory = Memory('/home/mgh/dev/projects/python_projects/mate/memory/working_memory/test_plan.json')
    # modules = memory.modules
    # for feature in memory.iter_all_features():
    #     print(feature.get_context_summary())
    #     print('----------------')
    pairs =extract_failed_fixed_pairs('../logs/experiment.log')
    for p in pairs:
        print("原始失败测试:")
        print(p["failed_test"])
        print()

        print("修复成功测试:")
        print(p["fixed_test"])
        print()

        print("错误日志:")
        print(p["error_log"])
        print("=" * 50)



