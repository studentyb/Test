import os
import sys
import copy
import json
import importlib
from pathlib import Path
from types import FrameType
from typing import Any, Dict, List, Optional

import pytest


class FunctionTracer:
    def __init__(self, target_module: str, target_func: str):
        self.target_module = target_module
        self.target_func = target_func
        self.records: List[Dict[str, Any]] = []

        self._active_frame_id: Optional[int] = None
        self._last_line_record: Optional[Dict[str, Any]] = None
        self._call_index = 0
        self._current_call_index: Optional[int] = None

    def _safe_copy_locals(self, locals_dict: Dict[str, Any]) -> Dict[str, Any]:
        result = {}
        for k, v in locals_dict.items():
            try:
                result[k] = copy.deepcopy(v)
            except Exception:
                try:
                    result[k] = repr(v)
                except Exception:
                    result[k] = "<unserializable>"
        return result

    def trace_func(self, frame: FrameType, event: str, arg):
        code = frame.f_code
        module_name = frame.f_globals.get("__name__", "")
        func_name = code.co_name

        is_target = (
            module_name == self.target_module and
            func_name == self.target_func
        )

        if event == "call" and is_target:
            self._active_frame_id = id(frame)
            self._call_index += 1
            self._current_call_index = self._call_index
            return self.trace_func

        if self._active_frame_id != id(frame):
            return self.trace_func

        if event == "line":
            current_locals = self._safe_copy_locals(frame.f_locals)
            lineno = frame.f_lineno

            if self._last_line_record is not None and self._last_line_record["after"] is None:
                self._last_line_record["after"] = current_locals

            current_record = {
                "call_index": self._current_call_index,
                "line": lineno,
                "before": current_locals,
                "after": None,
            }
            self.records.append(current_record)
            self._last_line_record = current_record

        elif event == "return":
            current_locals = self._safe_copy_locals(frame.f_locals)

            if self._last_line_record is not None and self._last_line_record["after"] is None:
                self._last_line_record["after"] = current_locals

            self.records.append({
                "call_index": self._current_call_index,
                "line": frame.f_lineno,
                "before": current_locals,
                "after": current_locals,
                "return": arg,
            })

            self._active_frame_id = None
            self._last_line_record = None
            self._current_call_index = None

        elif event == "exception":
            exc_type, exc_value, _ = arg
            current_locals = self._safe_copy_locals(frame.f_locals)

            if self._last_line_record is not None and self._last_line_record["after"] is None:
                self._last_line_record["after"] = current_locals

            self.records.append({
                "call_index": self._current_call_index,
                "line": frame.f_lineno,
                "before": current_locals,
                "after": current_locals,
                "exception": f"{exc_type.__name__}: {exc_value}",
            })

            self._active_frame_id = None
            self._last_line_record = None
            self._current_call_index = None

        return self.trace_func


def run_single_test_with_trace(
    project_root: str,
    target_func_path: str,
    pytest_test_path: str,
):
    """
    project_root: 项目根目录
    target_func_path: 例如 "mypkg.mod:add"
    pytest_test_path: 例如 "tests/test_mod.py::test_add"
    """
    project_root = str(Path(project_root).resolve())
    old_cwd = os.getcwd()
    old_sys_path = list(sys.path)
    old_trace = sys.gettrace()

    try:
        os.chdir(project_root)

        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        module_name, func_name = target_func_path.split(":")
        importlib.invalidate_caches()
        importlib.import_module(module_name)

        tracer = FunctionTracer(module_name, func_name)
        sys.settrace(tracer.trace_func)

        exit_code = pytest.main([pytest_test_path, "-q"])

        return exit_code, tracer.records

    finally:
        sys.settrace(old_trace)
        os.chdir(old_cwd)
        sys.path[:] = old_sys_path


if __name__ == "__main__":
    exit_code, records = run_single_test_with_trace(
        project_root=r"D:\BJFU\TestAgent\dataset\RQ4\workdir\readtime",
        target_func_path="src.utils:read_time",
        pytest_test_path="tests/test_utils.py::test_utils",
    )

    print(json.dumps(records, ensure_ascii=False, indent=2, default=str))


