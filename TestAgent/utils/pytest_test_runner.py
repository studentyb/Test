import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from utils.test_models import TestCaseResult, TestRunResult


class PytestTestRunner:
    """
    Python 单元测试运行与解析工具。
    使用 pytest-json-report 生成结构化报告，返回与 JavaTestRunnerTool 一致的
    TestRunResult / TestCaseResult 对象，同时保留完整日志作为兜底。
    """

    def __init__(self, dataset_root: Path, conda_env: Optional[str] = None):
        self.dataset_root = dataset_root
        self.conda_env = conda_env or os.environ.get("CONDA_ENV", "mate")

    def run_pytest(self, test_file_path: str) -> TestRunResult:
        if not self.dataset_root.exists():
            return TestRunResult(
                success=False,
                build_failed=True,
                error_msg=f"Error: Project root does not exist: {self.dataset_root}",
            )

        ini_path = self.dataset_root / "pytest.ini"
        if not ini_path.exists():
            try:
                ini_path.write_text("[pytest]\npythonpath = .\n", encoding="utf-8")
            except Exception as e:
                return TestRunResult(
                    success=False,
                    build_failed=True,
                    error_msg=f"Failed to create pytest.ini: {e}",
                )

        report_file = self.dataset_root / ".report.json"
        if report_file.exists():
            report_file.unlink()



        abs_file_path = Path(test_file_path).resolve()

        # 1. 依然建议保持相对路径和正斜杠，这是最干净的路径格式
        try:
            rel_file_path = os.path.relpath(abs_file_path, self.dataset_root)
        except ValueError:
            rel_file_path = str(abs_file_path)

        safe_file_path = str(rel_file_path).replace("\\", "/")

        # 2. 核心大招：使用 sys.executable 直接调用当前环境的 pytest
        cmd = [
            sys.executable,  # 指向当前环境的 python.exe
            "-m",  # 以模块方式运行
            "pytest",  # 调用 pytest
            safe_file_path,  # 目标测试文件
            "--json-report",
            "--json-report-file",
            ".report.json",
        ]

        # 彻底移除 if self.conda_env 的判断分支！
        # 直接拿组装好的 cmd 去跑 subprocess

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self.dataset_root),
                capture_output=True,
                text=True,
                timeout=120,
            )
        except FileNotFoundError:
            return TestRunResult(
                success=False, build_failed=True, error_msg="pytest not found in PATH."
            )
        except subprocess.TimeoutExpired:
            return TestRunResult(
                success=False, build_failed=True, error_msg="Pytest run timed out (120s)."
            )

        fallback_log = self._build_fallback_log(proc)

        if not report_file.exists():
            return TestRunResult(
                success=False,
                build_failed=True,
                error_msg=(
                    "No JSON report generated. Likely SyntaxError or import error.\n"
                    + fallback_log[-4000:]
                ),
            )

        try:
            with report_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            return TestRunResult(
                success=False,
                build_failed=True,
                error_msg=f"Failed to parse JSON report: {e}\n{fallback_log[-4000:]}",
            )

        return self._parse_json_report(data, fallback_log, proc.returncode)

    # ------------------------------------------------------------------

    def _parse_json_report(
        self, data: dict, fallback_log: str, returncode: int
    ) -> TestRunResult:
        run_result = TestRunResult(success=False, build_failed=False)

        has_collection_error = False
        collection_errors = []

        for collector in data.get("collectors", []):
            if collector.get("outcome") == "failed":
                has_collection_error = True
                collection_errors.append(str(collector.get("longrepr", "Unknown")))

        tests = data.get("tests", [])

        for test in tests:
            nodeid = test.get("nodeid", "")
            class_name, test_name = self._parse_nodeid(nodeid)

            setup = test.get("setup", {})
            call = test.get("call", {})
            teardown = test.get("teardown", {})

            # setup 阶段失败
            if setup.get("outcome") == "failed":
                error_type = self._extract_error_type(setup.get("longrepr", ""))
                run_result.test_cases.append(
                    TestCaseResult(
                        class_name=class_name,
                        test_name=test_name,
                        status="ERROR",
                        error_type=error_type or "SetupError",
                        message=self._truncate(str(setup.get("longrepr", "")), 1000),
                    )
                )
                continue

            # call 阶段
            if call.get("outcome") == "passed":
                run_result.test_cases.append(
                    TestCaseResult(
                        class_name=class_name,
                        test_name=test_name,
                        status="PASSED",
                    )
                )
            elif call.get("outcome") in ("failed", "error"):
                longrepr = str(call.get("longrepr", ""))
                error_type = self._extract_error_type(longrepr)

                is_assertion = (
                    (error_type and "AssertionError" in error_type)
                    or "AssertionError" in longrepr
                    or "assert " in longrepr.lower()
                )
                status = "FAILED" if is_assertion else "ERROR"

                msg = self._truncate(longrepr, 1000)
                stdout = call.get("stdout", "")
                if stdout:
                    msg += f"\n--- STDOUT ---\n{self._truncate(stdout, 500)}"

                run_result.test_cases.append(
                    TestCaseResult(
                        class_name=class_name,
                        test_name=test_name,
                        status=status,
                        error_type=error_type or ("AssertionError" if is_assertion else "RuntimeError"),
                        message=msg,
                    )
                )
            elif test.get("outcome") == "skipped":
                run_result.test_cases.append(
                    TestCaseResult(
                        class_name=class_name,
                        test_name=test_name,
                        status="SKIPPED",
                    )
                )

            # teardown 阶段失败（少见但需要捕获）
            if teardown.get("outcome") == "failed":
                error_type = self._extract_error_type(teardown.get("longrepr", ""))
                run_result.test_cases.append(
                    TestCaseResult(
                        class_name=class_name,
                        test_name=f"{test_name}::teardown",
                        status="ERROR",
                        error_type=error_type or "TeardownError",
                        message=self._truncate(str(teardown.get("longrepr", "")), 1000),
                    )
                )

        # ---- 状态判定 ----

        # 场景 A: 收集阶段失败（import error / syntax error），没有任何测试用例
        if has_collection_error and not tests:
            run_result.build_failed = True
            run_result.success = False
            run_result.error_msg = (
                "Collection failed (SyntaxError / ImportError).\n"
                + "\n".join(collection_errors[:3])
                + "\n"
                + fallback_log[-3000:]
            )
            return run_result

        # 场景 B: 有收集错误但部分测试仍然运行了
        if has_collection_error:
            run_result.build_failed = False
            run_result.success = False
            run_result.error_msg = (
                "Partial collection failure.\n"
                + "\n".join(collection_errors[:3])
                + "\n"
                + fallback_log[-3000:]
            )
            return run_result

        has_failed = any(tc.status in ("FAILED", "ERROR") for tc in run_result.test_cases)

        # 场景 C: 有失败的测试用例
        if has_failed:
            run_result.success = False
            run_result.error_msg = fallback_log[-4000:]
            return run_result

        # 场景 D: 所有用例通过但进程异常退出
        if returncode != 0:
            run_result.success = False
            run_result.error_msg = (
                f"All tests passed but process exited with code {returncode}.\n"
                + fallback_log[-4000:]
            )
            return run_result

        # 场景 E: 完美通过
        run_result.success = True
        return run_result

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_nodeid(nodeid: str):
        """
        将 pytest nodeid 拆分为 (class_name, test_name)。
        例如 "tests/test_foo.py::TestBar::test_baz" -> ("TestBar", "test_baz")
             "tests/test_foo.py::test_baz"           -> ("test_foo", "test_baz")
        """
        parts = nodeid.split("::")
        if len(parts) >= 3:
            return parts[-2], parts[-1]
        elif len(parts) == 2:
            module = parts[0].replace("/", ".").replace("\\", ".")
            if module.endswith(".py"):
                module = module[:-3]
            module = module.split(".")[-1]
            return module, parts[-1]
        return "unknown", nodeid

    @staticmethod
    def _extract_error_type(longrepr: str) -> Optional[str]:
        """从 longrepr 中提取异常类型，如 'ValueError', 'AssertionError' 等"""
        match = re.search(r"(\w+Error|\w+Exception|\w+Warning)\b", longrepr)
        return match.group(1) if match else None

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return text[:max_len] + "\n... [truncated]"

    @staticmethod
    def _build_fallback_log(proc: subprocess.CompletedProcess) -> str:
        log = ""
        if proc.stderr:
            log += f"--- STDERR ---\n{proc.stderr}\n"
        if proc.stdout:
            log += f"--- STDOUT ---\n{proc.stdout}\n"
        return log
