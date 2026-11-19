import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from utils.test_models import TestCaseResult, TestRunResult

class JavaTestRunnerTool:
    """
    Java 单元测试运行与解析工具。
    支持自动运行 Gradle 或 Maven 测试，并以结构化对象形式返回结果，
    能精准区分“代码构建失败”与“业务测试用例失败”。
    """

    def __init__(self, sut_root: Path, dataset_root: Path, build_tool: str = "gradle"):
        """
        初始化测试运行器。

        :param sut_root: 被测代码 (SUT) 的根目录路径。
        :param dataset_root: 包含构建脚本 (build.gradle 或 pom.xml) 的工作空间根目录。
        :param build_tool: 构建工具类型，"gradle" 或 "maven"。
        """
        self.sut_root =sut_root
        self.dataset_root = dataset_root
        self.build = build_tool.lower()

    def run_java_tests(self, test_class_name: str) -> TestRunResult:
        """根据初始化的构建工具运行测试，并返回结构化的测试结果对象。"""
        if not self.sut_root.exists():
            return TestRunResult(
                success=False,
                build_failed=True,
                error_msg=f"Error: SUT directory does not exist: {self.sut_root}"
            )

        if self.build == "gradle":
            return self._run_gradle_tests(test_class_name)
        elif self.build == "maven":
            return self._run_maven_tests(test_class_name)
        else:
            return TestRunResult(
                success=False,
                build_failed=True,
                error_msg=f"Error: Unsupported build tool '{self.build}'"
            )

    def _run_gradle_tests(self, test_class_name: str) -> TestRunResult:
        gradle_cmd = "gradle.bat" if os.name == "nt" else "gradle"
        # 注意：这里必须带上 clean，这是后续判定 build_failed 的重要前提
        cmd = [gradle_cmd, "clean", "test", "--tests", test_class_name]

        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.dataset_root),
                capture_output=True,
                text=True,
                timeout=120,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError:
            return TestRunResult(success=False, build_failed=True, error_msg="Gradle not found in PATH.")
        except subprocess.TimeoutExpired:
            return TestRunResult(success=False, build_failed=True, error_msg="Gradle test run timed out.")

        report_dir = self.dataset_root / "build" / "test-results" / "test"
        fallback_log = self._build_fallback_log(result)

        return self._parse_junit_report_dir(
            report_dir, fallback_log, process_returncode=result.returncode
        )

    def _run_maven_tests(self, test_class_name: str) -> TestRunResult:
        mvn_cmd = "mvn.cmd" if os.name == "nt" else "mvn"
        # 同样带上 clean
        cmd = [mvn_cmd, "clean", "test", f"-Dtest={test_class_name}"]

        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.dataset_root),
                capture_output=True,
                text=True,
                timeout=120,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError:
            return TestRunResult(success=False, build_failed=True, error_msg="Maven not found in PATH.")
        except subprocess.TimeoutExpired:
            return TestRunResult(success=False, build_failed=True, error_msg="Maven test run timed out.")

        report_dir = self.dataset_root / "target" / "surefire-reports"
        fallback_log = self._build_fallback_log(result)

        return self._parse_junit_report_dir(
            report_dir, fallback_log, process_returncode=result.returncode
        )

    def _build_fallback_log(self, result: subprocess.CompletedProcess) -> str:
        """提取基础的控制台日志，用于严重错误时的兜底排查"""
        log = ""
        if result.stderr:
            log += f"--- STDERR ---\n{result.stderr}\n"
        if result.stdout:
            log += f"--- STDOUT ---\n{result.stdout}\n"
        return log

    def _parse_junit_report_dir(
            self, report_dir: Path, fallback_log: str, process_returncode: int
    ) -> TestRunResult:
        """
        遍历目录下所有 JUnit XML，解析并根据规则判定最终状态。

        判定规则：
        1. 没有 XML -> 构建/初始化失败
        2. 存在 <error> -> 整体失败
        3. 存在 <failure>，但全部都是 AssertionFailedError -> 整体通过
        4. 存在 <failure>，且有非 AssertionFailedError -> 整体失败
        5. 没有失败/错误，但返回码非 0 -> 进程异常，整体失败
        6. 其他情况 -> 整体通过
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

        # 1. 没有 XML：认为构建/初始化失败
        if not xml_found:
            run_result.build_failed = True
            run_result.success = False
            run_result.error_msg = (
                f"No XML reports found. Compilation/setup likely failed.\n"
                f"{fallback_log[-4000:]}"
            )
            return run_result

        run_result.build_failed = False

        # 2. 分类统计
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

        # 3. 有 <error>，整体失败
        if has_error_node:
            run_result.success = False
            run_result.error_msg = fallback_log[-4000:]

        # 4. 有非 AssertionFailedError 的 <failure>，整体失败
        elif has_non_assertion_failure:
            run_result.success = False
            run_result.error_msg = fallback_log[-4000:]

        # 5. 如果只有 AssertionFailedError，整体算通过
        elif has_only_assertion_failures:
            run_result.success = True
            run_result.error_msg = fallback_log[-4000:]

        # 6. XML 全绿但返回码异常，整体失败
        elif process_returncode != 0:
            run_result.success = False
            run_result.error_msg = (
                f"Tests passed, but process crashed unexpectedly (Return Code: {process_returncode}).\n"
                f"Check logs for environment issues like OOM.\n{fallback_log[-4000:]}"
            )

        # 7. 完全通过
        else:
            run_result.success = True

        return run_result

    # def _parse_junit_report_dir(
    #         self, report_dir: Path, fallback_log: str, process_returncode: int
    # ) -> TestRunResult:
    #     """
    #     核心逻辑：遍历目录下所有 JUnit XML，解析并根据三维变量判定最终状态。
    #     """
    #     report_path = Path(report_dir)
    #     run_result = TestRunResult(success=False, build_failed=False)
    #
    #     xml_found = False
    #
    #     # 1. 尝试解析可能存在的 XML 报告
    #     if report_path.is_dir():
    #         for path in report_path.iterdir():
    #             if path.suffix.lower() != ".xml":
    #                 continue
    #
    #             xml_found = True
    #             try:
    #                 tree = ET.parse(str(path))
    #                 root = tree.getroot()
    #                 suites = [root] if root.tag == "testsuite" else (root.findall(".//testsuite") or [root])
    #
    #                 for suite in suites:
    #                     for case in suite.findall("testcase"):
    #                         class_attr = case.get("classname", "")
    #                         name_attr = case.get("name", "")
    #                         status = "PASSED"
    #                         error_type = None
    #                         core_message = None
    #
    #                         failure_node = case.find("failure")
    #                         error_node = case.find("error")
    #                         skipped_node = case.find("skipped")
    #
    #                         bad_node = failure_node if failure_node is not None else error_node
    #
    #                         if bad_node is not None:
    #                             status = "FAILED" if failure_node is not None else "ERROR"
    #                             error_type = bad_node.get("type", "")
    #
    #                             # 精准提取核心错误信息，抛弃冗余堆栈
    #                             core_message = bad_node.get("message", "")
    #                             if not core_message and bad_node.text:
    #                                 core_message = bad_node.text.strip().split('\n')[0]
    #                         elif skipped_node is not None:
    #                             status = "SKIPPED"
    #
    #                         run_result.test_cases.append(TestCaseResult(
    #                             class_name=class_attr,
    #                             test_name=name_attr,
    #                             status=status,
    #                             error_type=error_type,
    #                             message=core_message
    #                         ))
    #             except ET.ParseError as e:
    #                 run_result.error_msg += f"Parse error in {path!s}: {e}\n"
    #
    #     # ==========================================
    #     # 2. 状态判定矩阵
    #     # ==========================================
    #
    #     # 场景 A: 真正的构建失败 (编译报错、依赖找不到等，导致没走到测试环节)
    #     if not xml_found:
    #         run_result.build_failed = True
    #         run_result.success = False
    #         run_result.error_msg = f"No XML reports found. Compilation/setup likely failed.\n{fallback_log[-4000:]}"
    #         return run_result
    #
    #     # 既然能找到 XML，说明编译成功通过了
    #     run_result.build_failed = False
    #
    #     has_failed_tests = any(tc.status in ["FAILED", "ERROR"] for tc in run_result.test_cases)
    #
    #     # 场景 B: 纯粹的测试用例失败 (代码跑通了，但断言没过)
    #     if has_failed_tests:
    #         run_result.success = False
    #         run_result.error_msg=fallback_log[-4000:]
    #
    #     # 场景 C: 极端边缘异常 (XML 全绿，但进程异常退出了，如 OOM)
    #     elif not has_failed_tests and process_returncode != 0:
    #         run_result.success = False
    #         run_result.error_msg = (
    #             f"Tests passed, but process crashed unexpectedly (Return Code: {process_returncode}).\n"
    #             f"Check logs for environment issues like OOM.\n{fallback_log[-4000:]}"
    #         )
    #
    #     # 场景 D: 完美通过 (XML 全绿，进程状态码为 0)
    #     else:
    #         run_result.success = True
    #
    #     return run_result

if __name__ == '__main__':
    import json

    runner = JavaTestRunnerTool(sut_root=Path("/home/mgh/dev/data/dataset/DevEval/java/idcenter/src/main/java"), dataset_root=Path("/home/mgh/dev/data/dataset/DevEval/java/idcenter"))

    # 返回的是一个 TestRunResult 类实例
    result: TestRunResult = runner.run_java_tests("SidWorkerTest")

    # 1. 面向对象的访问方式
    if result.success:
        print("✅ 所有测试都通过了！")
    else:
        print(f"❌ 测试失败，构建失败状态: {result.build_failed}")
        if result.error_msg:
            print(f"全局错误信息: {result.error_msg}")

        # 遍历处理每个用例
        for test in result.test_cases:
                print(f"用例 {test.test_name} :{test.status}")
                print(f"-> 错误类型: {test.error_type}")
                print(f"-> 核心信息: {test.message}")

