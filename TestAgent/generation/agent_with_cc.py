import json
import logging
import os
import subprocess
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Optional, Tuple, List

from agents.agents import create_test_debugger
from piplines.core import PipelineStep
from utils.java_test_runner import JavaTestRunnerTool
from utils.pytest_test_runner import PytestTestRunner
from utils.test_models import TestCaseResult, TestRunResult
from utils.parser import parse_debug_report
from utils.tree_utils import get_directory_tree
from utils.file_utils import read_file

log = logging.getLogger("mate")


class Test4CA:
    """
    测试运行和调试分析器
    - 运行被测项目的现有测试用例
    - 分析失败测试
    - 生成结构化测试报告
    """

    def __init__(
        self,
        *,
        build: str = "maven",
        sut_root: str,
        dataset_root: str = None,
        language: str,
        verbose: bool = False,
        debug: bool = True,
        stream: bool = True,
        feature: str = None,
        put: str = "",
    ):
        # 只保留 debug 相关的 agent
        self.test_debugger = create_test_debugger()
        self.cot5_desc = read_file('prompt/test_debugger/test_debug.md')

        self.build = build.strip().lower()
        self.sut_root = Path(sut_root).resolve()
        self.dataset_root = Path(dataset_root).resolve() if dataset_root else self.sut_root
        self.put = put
        self.language = language.strip().lower()
        self.verbose = verbose
        self.debug = debug
        self.stream = stream
        self.feature = feature or "all_tests"

        # 确定测试目录
        if self.language == "java":
            self.test_root = self.dataset_root / "src" / "test" / "java"
        else:
            self.test_root = self.dataset_root / "tests"

        self.ps = get_directory_tree(str(self.sut_root))
        self.debug_report: Optional[Dict] = None

    # ------------------------------------------------------------------
    # 对外入口 — 运行所有测试并生成报告
    # ------------------------------------------------------------------
    def run(self) -> dict | None:
        """运行所有测试并生成调试报告"""

        log.info("=" * 30 + " Running All Tests " + "=" * 30)
        test_results = self._run_all_tests()

        if not test_results:
            log.error("No test results obtained")
            return None

        # 统计测试结果
        total = len(test_results.test_cases)
        passed = sum(1 for tc in test_results.test_cases if tc.status == "PASSED")
        failed = sum(1 for tc in test_results.test_cases if tc.status in ["FAILED", "ERROR"])

        log.info(f"Test Summary: {passed}/{total} passed, {failed} failed")

        if test_results.build_failed:
            log.error(f"Build failed: {test_results.error_msg}")
            return {
                "feature": self.feature,
                "build_failed": True,
                "error_msg": test_results.error_msg,
                "overall_pass_rate": "0/0",
                "summary": "Build/compilation failed. No tests executed.",
                "test_results": [],
            }

        # 如果全部通过，直接返回报告
        if test_results.success:
            log.info("All tests passed")
            return {
                "feature": self.feature,
                "overall_pass_rate": f"{passed}/{total}",
                "summary": "All tests passed. No SUT bugs detected.",
                "test_results": [
                    {"test_name": tc.test_name, "status": "PASSED", "reason": ""}
                    for tc in test_results.test_cases
                ],
            }

        # 有失败的测试 - 进行 debug 分析
        log.info("=" * 30 + " Debug & Report " + "=" * 30)
        self.debug_report = self._analyze_failures(
            test_results=test_results,
            verbose=self.verbose
        )

        return self.debug_report

    # ------------------------------------------------------------------
    # 运行所有测试
    # ------------------------------------------------------------------
    def _run_all_tests(self) -> Optional[TestRunResult]:
        """
        运行被测项目下的所有测试
        """
        language = self.language or "python"

        try:
            if language == "python":
                runner = PytestTestRunner(
                    dataset_root=self.dataset_root,
                    conda_env=os.environ.get("CONDA_ENV", "mate"),
                )
                # 运行整个测试目录
                result = runner.run_pytest(str(self.test_root))
                return result
            else:
                runner = JavaTestRunnerTool(
                    sut_root=self.sut_root,
                    dataset_root=self.dataset_root,
                    build_tool=self.build,
                )
                # 运行所有测试
                return self._run_all_java_tests()
        except Exception as e:
            log.error(f"Error running tests: {e}")
            return None

    # ------------------------------------------------------------------
    # 运行所有 Java 测试
    # ------------------------------------------------------------------
    def _run_all_java_tests(self) -> TestRunResult:
        """运行所有 Java 测试（支持 Maven 和 Gradle）"""

        if self.build == "gradle":
            gradle_cmd = "gradle.bat" if os.name == "nt" else "gradle"
            cmd = [gradle_cmd, "clean", "test"]
            report_dir = self.dataset_root / "build" / "test-results" / "test"
        else:
            mvn_cmd = "mvn.cmd" if os.name == "nt" else "mvn"
            cmd = [mvn_cmd, "clean", "test"]
            report_dir = self.dataset_root / "target" / "surefire-reports"

        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.dataset_root),
                capture_output=True,
                text=True,
                timeout=300,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError:
            return TestRunResult(
                success=False,
                build_failed=True,
                error_msg=f"{self.build} not found in PATH."
            )
        except subprocess.TimeoutExpired:
            return TestRunResult(
                success=False,
                build_failed=True,
                error_msg=f"{self.build} test run timed out."
            )

        fallback_log = ""
        if result.stderr:
            fallback_log += f"--- STDERR ---\n{result.stderr}\n"
        if result.stdout:
            fallback_log += f"--- STDOUT ---\n{result.stdout}\n"

        return self._parse_junit_report_dir(report_dir, fallback_log, result.returncode)

    # ------------------------------------------------------------------
    # 解析 JUnit XML 报告目录
    # ------------------------------------------------------------------
    def _parse_junit_report_dir(
            self, report_dir: Path, fallback_log: str, process_returncode: int
    ) -> TestRunResult:
        """
        遍历目录下所有 JUnit XML，解析并根据规则判定最终状态。
        """
        report_path = Path(report_dir)
        run_result = TestRunResult(success=False, build_failed=False)

        xml_found = False

        if report_path.is_dir():
            for path in report_path.iterdir():
                if path.suffix.lower() != ".xml":
                    continue

                xml_found = True
                try:
                    tree = ET.parse(str(path))
                    root = tree.getroot()
                    suites = [root] if root.tag == "testsuite" else (root.findall(".//testsuite") or [root])

                    for suite in suites:
                        for case in suite.findall("testcase"):
                            class_attr = case.get("classname", "")
                            name_attr = case.get("name", "")
                            status = "PASSED"
                            error_type = None
                            core_message = None

                            failure_node = case.find("failure")
                            error_node = case.find("error")
                            skipped_node = case.find("skipped")

                            if failure_node is not None:
                                status = "FAILED"
                                error_type = failure_node.get("type", "") or ""
                                core_message = failure_node.get("message", "") or ""
                                if not core_message and failure_node.text:
                                    core_message = failure_node.text.strip().split("\n")[0]

                            elif error_node is not None:
                                status = "ERROR"
                                error_type = error_node.get("type", "") or ""
                                core_message = error_node.get("message", "") or ""
                                if not core_message and error_node.text:
                                    core_message = error_node.text.strip().split("\n")[0]

                            elif skipped_node is not None:
                                status = "SKIPPED"

                            run_result.test_cases.append(TestCaseResult(
                                class_name=class_attr,
                                test_name=name_attr,
                                status=status,
                                error_type=error_type,
                                message=core_message
                            ))

                except ET.ParseError as e:
                    run_result.error_msg += f"Parse error in {path!s}: {e}\n"

        # 没有 XML：认为构建/初始化失败
        if not xml_found:
            run_result.build_failed = True
            run_result.success = False
            run_result.error_msg = (
                f"No XML reports found. Compilation/setup likely failed.\n"
                f"{fallback_log[-4000:]}"
            )
            return run_result

        run_result.build_failed = False

        # 分类统计
        has_error_node = any(tc.status == "ERROR" for tc in run_result.test_cases)

        failed_cases = [tc for tc in run_result.test_cases if tc.status == "FAILED"]

        def is_assertion_failed_error(tc: TestCaseResult) -> bool:
            error_type = (tc.error_type or "").strip()
            return (
                    error_type == "org.opentest4j.AssertionFailedError"
                    or error_type == "junit.framework.AssertionFailedError"
                    or error_type == "java.lang.AssertionError"
                    or error_type.endswith(".AssertionFailedError")
                    or error_type.endswith(".AssertionError")
                    or error_type in {"AssertionFailedError", "AssertionError"}
            )

        has_non_assertion_failure = any(
            not is_assertion_failed_error(tc) for tc in failed_cases
        )

        has_only_assertion_failures = (
                len(failed_cases) > 0 and
                not has_error_node and
                not has_non_assertion_failure
        )

        # 有 <error>，整体失败
        if has_error_node:
            run_result.success = False
            run_result.error_msg = fallback_log[-4000:]

        # 有非 AssertionFailedError 的 <failure>，整体失败
        elif has_non_assertion_failure:
            run_result.success = False
            run_result.error_msg = fallback_log[-4000:]

        # 如果只有 AssertionFailedError，整体算通过
        elif has_only_assertion_failures:
            run_result.success = True
            run_result.error_msg = fallback_log[-4000:]

        # XML 全绿但返回码异常，整体失败
        elif process_returncode != 0:
            run_result.success = False
            run_result.error_msg = (
                f"Tests passed, but process crashed unexpectedly (Return Code: {process_returncode}).\n"
                f"Check logs for environment issues like OOM.\n{fallback_log[-4000:]}"
            )

        # 完全通过
        else:
            run_result.success = True

        return run_result

    # ------------------------------------------------------------------
    # 分析失败测试
    # ------------------------------------------------------------------
    def _analyze_failures(self, test_results: TestRunResult, verbose: bool = True) -> Optional[Dict]:
        """
        分析失败的测试用例，生成结构化的调试报告
        """
        feature_name = self.feature
        language = self.language or "python"

        # 获取失败的测试用例
        failed_tests = [
            tc for tc in test_results.test_cases
            if tc.status in ["FAILED", "ERROR"]
        ]

        if not failed_tests:
            return {
                "feature": feature_name,
                "overall_pass_rate": f"{len(test_results.test_cases)}/{len(test_results.test_cases)}",
                "summary": "All tests passed. No failures to analyze.",
                "test_results": [],
            }

        log.info(f"Analyzing {len(failed_tests)} failed tests...")

        # 对每个失败的测试进行详细分析
        all_debug_results = []

        for failed_test in failed_tests:
            debug_result = self._analyze_single_failure(
                failed_test=failed_test,
                language=language,
                verbose=verbose
            )
            if debug_result:
                all_debug_results.append(debug_result)

        # 汇总所有调试结果
        passed_tests = [
            {"test_name": tc.test_name, "status": "PASSED", "reason": ""}
            for tc in test_results.test_cases
            if tc.status == "PASSED"
        ]

        sut_bugs = [r for r in all_debug_results if r.get("status") == "SUT_BUG"]
        test_bugs = [r for r in all_debug_results if r.get("status") == "TEST_BUG"]

        valid_total = len(passed_tests) + len(sut_bugs)
        valid_pass_rate = f"{len(passed_tests)}/{valid_total}" if valid_total > 0 else "0/0"

        report = {
            "feature": feature_name,
            "overall_pass_rate": valid_pass_rate,
            "summary": f"Found {len(sut_bugs)} SUT bugs, {len(test_bugs)} test bugs",
            "test_results": passed_tests + sut_bugs,
            "ignored_test_bugs": test_bugs,
        }

        return report

    # ------------------------------------------------------------------
    # 分析单个失败测试
    # ------------------------------------------------------------------
    def _analyze_single_failure(
        self,
        failed_test: TestCaseResult,
        language: str,
        verbose: bool
    ) -> Optional[Dict]:
        """
        对单个失败的测试进行详细分析，包括行追踪
        """
        test_name = failed_test.test_name
        error_type = failed_test.error_type
        error_msg = failed_test.message

        log.info(f"Analyzing failure: {test_name} - {error_type}")

        # 尝试获取被测类和方法名
        sut_class_name, sut_method_name = self._parse_sut_info(failed_test)

        # 行追踪信息
        line_tracer_info = ""

        # 如果是断言错误且是 Java，尝试行追踪
        if (error_type and "Assertion" in error_type.lower() and
            language == "java" and sut_class_name and sut_method_name):

            try:
                from debug.java_debugger import run_java_line_tracer

                jar_path = str(Path(__file__).parent.parent / "debug" / "line-tracer.jar")
                test_method = f"{failed_test.class_name}#{test_name}"

                returncode, stdout, stderr = run_java_line_tracer(
                    project_path=str(self.dataset_root),
                    class_name=sut_class_name,
                    method_name=sut_method_name,
                    test_method=test_method,
                    jar_path=jar_path,
                    timeout=30
                )

                if returncode == 0:
                    line_tracer_info = stdout
                    log.info(f"Line tracer output: {len(stdout)} chars")
                else:
                    log.warning(f"Line tracer failed: {stderr}")

            except Exception as e:
                log.warning(f"Line tracer error: {e}")

        # 调用 Debug Agent 分析
        debug_step = PipelineStep(
            agent=self.test_debugger,
            template_text=self.cot5_desc,
            expected_output="A structured JSON debug report classifying of failure as SUT_BUG or TEST_BUG.",
            output_file='',
            verbose=verbose,
            stream=self.stream,
            debug=self.debug,
        )

        # 构造测试代码字符串
        test_code = f"""
// Test Class: {failed_test.class_name}
// Test Method: {test_name}
// Error Type: {error_type}
// Error Message: {error_msg}
"""

        # 尝试读取代码上下文
        code_context = self._get_code_context(sut_class_name, sut_method_name, language)

        output = debug_step.run(
            ps=self.ps,
            put=self.put or f"Test failure analysis for {test_name}",
            test_code=test_code,
            source_code=code_context,
            exec_report=error_msg or "",
            line_tracer_info=line_tracer_info
        )

        # 解析 debug agent 的输出
        raw_output = self._collect_output(output)

        result = {
            "test_name": test_name,
            "status": "UNKNOWN",
            "reason": raw_output[:500],
            "line_tracer_info": line_tracer_info[:1000] if line_tracer_info else "",
        }

        # 简单解析输出中的状态
        if "SUT_BUG" in raw_output:
            result["status"] = "SUT_BUG"
        elif "TEST_BUG" in raw_output:
            result["status"] = "TEST_BUG"

        return result

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------
    def _parse_sut_info(self, test_case: TestCaseResult) -> Tuple[Optional[str], Optional[str]]:
        """
        从测试用例中尝试解析被测类和方法名
        """
        class_name = test_case.class_name
        test_name = test_case.test_name

        if not class_name or not test_name:
            return None, None

        # 简单的启发式规则：去掉 Test 后缀
        if class_name.endswith("Test"):
            sut_class = class_name[:-4]
        elif class_name.endswith("Tests"):
            sut_class = class_name[:-5]
        else:
            sut_class = class_name

        # 从测试方法名中提取被测方法名
        test_name_lower = test_name.lower()
        if test_name_lower.startswith("test_"):
            sut_method = test_name[5:]
        elif test_name_lower.startswith("test"):
            sut_method = test_name[4:]
        else:
            sut_method = test_name

        return sut_class, sut_method

    def _get_code_context(self, sut_class: str, sut_method: str, language: str) -> str:
        """
        获取被测代码的上下文
        """
        if not sut_class:
            return ""

        try:
            if language == "java":
                from tools.grep import get_code_context
                return get_code_context(
                    str(self.sut_root),
                    json.dumps([{"focal_method": f"{sut_class}.{sut_method}()"}]),
                    language,
                    None
                )
            else:
                return f"# Module: {sut_class}\n# Function: {sut_method}"
        except Exception as e:
            log.warning(f"Error getting code context: {e}")
            return ""

    def _collect_output(self, output) -> str:
        """收集 pipeline step 的输出"""
        result = ""
        if hasattr(output, "__iter__") and not isinstance(output, str):
            for chunk in output:
                content = getattr(chunk, "content", str(chunk))
                result += content
        else:
            result = str(output)
        return result
