# app.py
import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import List
from typing import Tuple, Optional

from agents.agents import (
    create_test_architect,
    create_test_designer,
    create_test_development_engineer,
    create_test_debugger,
    create_test_reviewer,
    create_mr_parser, create_context_retriever
)
from experience.core import summarize_experience, search_exp
from rag.db_instance import vector_db
from piplines.core import PipelineStep
from tools.grep import get_code_context
from utils.chat import get_ai_response
from utils.dataset_utils import load_dataset
from utils.file_utils import read_file, normalize_display_newlines, write_marked_block, restore_all, move_to_quarantine, \
    save_code_to_file, write_file
from utils.java_test_runner import JavaTestRunnerTool
from utils.memory_utils import Memory
from utils.parser import parse_file_and_code
from utils.tree_utils import get_directory_tree


def _kickoff_text(output) -> str:
    """Text of a CrewAI kickoff. py312's CrewOutput iterates as field tuples."""
    if isinstance(output, str):
        return output
    raw = getattr(output, "raw", None)
    if isinstance(raw, str):
        return raw
    result = getattr(output, "result", None)
    if isinstance(result, str):
        return result
    if hasattr(output, "__iter__"):
        parts = []
        for chunk in output:
            content = getattr(chunk, "content", None)
            if content is None and isinstance(chunk, tuple) and len(chunk) >= 2 and chunk[0] == "raw":
                content = chunk[1]
            if content is None:
                content = str(chunk)
            parts.append(str(content))
        return "".join(parts)
    return str(output)


class TestAgentApp:

    def __init__(self, *, dataset_name, stream: bool = True, debug=False, exp=True, max_retries=3):
        self.experience = exp
        self.dataset_name = dataset_name
        self.debug = debug
        # 是否使用大模型流式输出
        self.stream = stream
        self.data = load_dataset(dataset_name, strict=True)
        # 语言 / 构建工具 / 路径配置
        self.sut_root: Path = Path(self.data.sut_root).resolve()
        self.language: str = (self.data.language or "").strip().lower()
        self.test_root: Path = Path(self.data.test_root).resolve()
        # 自动探测构建工具（Maven / Gradle），用于 Java 测试运行
        if (self.data.dataset_root / "pom.xml").exists():
            self.build: str = "maven"
        elif (self.data.dataset_root / "build.gradle").exists() or (
                self.data.dataset_root / "build.gradle.kts").exists():
            self.build = "gradle"
        else:
            self.build = ""
        # 初始化几个agent
        self.test_architect = create_test_architect()
        self.test_designer = create_test_designer()
        self.mr_parser = create_mr_parser()
        self.test_reviewer = create_test_reviewer()
        self.test_developer = create_test_development_engineer()
        self.test_debugger = create_test_debugger()
        self.retriever_agent = create_context_retriever()
        self.cot1_desc = read_file(Path('prompt') / 'test_plan' / 'test_plan.md')
        self.cot1_out = read_file(Path('prompt') / 'test_plan' / 'test_plan_out.md')
        self.cot2_desc = read_file(Path('prompt') / 'test_design' / 'test_design.md')
        self.cot2_out = read_file(Path('prompt') / 'test_design' / 'test_design_out.md')
        self.mr_desc = read_file(Path('prompt') / 'mr_parse' / 'mr_parse_input.md')
        self.mr_parse_out = read_file(Path('prompt') / 'mr_parse' / 'mr_parse_output.md')
        self.mr_review_desc = read_file(Path('prompt') / 'mr_parse' / 'mr_review.md')
        self.mr_review_out = read_file(Path('prompt') / 'mr_parse' / 'mr_review_out.md')
        self.mr_fix_desc = read_file(Path('prompt') / 'mr_parse' / 'mr_fix.md')
        # self.cot3_desc = read_file(Path('prompt') / 'test_review' / 'test_review.md')
        # self.cot3_out = read_file(Path('prompt') / 'test_review' / 'test_review_out.md')
        self.cot4_desc = read_file(Path('prompt') / 'test_development' / 'test_develop.md')
        self.cot4_fix = read_file(Path('prompt') / 'test_development' / 'self_fix.md')
        self.cot4_out = read_file(Path('prompt') / 'test_development' / 'test_develop_out.md')
        self.cot5_desc = read_file(Path('prompt') / 'test_debugger' / 'test_debug.md')
        # self.cot5_out=read_file('prompt/test_debugger/test_debug_out.md')
        self.max_review_iterations = 1  # 最大评审迭代次数
        self.max_retries=max_retries
        # file_tree 仍然使用被测系统根目录
        self.ps = get_directory_tree(str(self.sut_root))

    DEBUG_RUN = {4,6}

    def run(self, *, verbose=False, mr=False):

        # --------------------------------------------------------------------
        # Cot1 — Test planning (测试计划)
        # --------------------------------------------------------------------
        if 1 in self.DEBUG_RUN:
            print('\n=====================test plan start============================\n')
            # 清空working memory
            archive_working_memory()
            # 测试计划agent
            step1 = PipelineStep(
                agent=self.test_architect,
                template_text=self.cot1_desc,
                expected_output=self.cot1_out,
                output_file=str(Path('memory') / 'working_memory' / 'test_plan.json'),
                verbose=verbose,
                stream=self.stream,
                debug=self.debug,
                stage="plan",
            )

            step1_output = step1.run(
                srs=self.data.srs,
                class_diagram=self.data.uml_class,
                sequence_diagram=self.data.uml_sequence,
                add=self.data.architecture_design
            )
            # 兼容流式与非流式输出
            if hasattr(step1_output, "__iter__") and not isinstance(step1_output, str):
                for chunk in step1_output:
                    content = getattr(chunk, "content", str(chunk))
                    print(normalize_display_newlines(content), end="", flush=True)
            else:
                content = getattr(step1_output, "raw", str(step1_output))
                print(normalize_display_newlines(content), end="", flush=True)
            # 如果需要保留结果供后续使用
            # final1 = streaming_output.result
        # load working memory
        memory = Memory(str(Path('memory') / 'working_memory' / 'test_plan.json'))
        # 逐个函数设计测试用例。CMATG_MAX_FEATURES>0 时只跑计划里的前 N 个，便于跨仓库取平均。
        from utils.token_ledger import set_context, write_row
        max_features = int(os.environ.get("CMATG_MAX_FEATURES") or "0")
        for feature_seq, feature in enumerate(memory.iter_all_features(), 1):
            if max_features and feature_seq > max_features:
                print(f"\n[CMATG] feature cap {max_features} reached\n")
                break
            set_context(feature=feature.feature_name, feature_seq=feature_seq)
            write_row('feature_start', 0, 0, experience_count=vector_db.experience_collection.count())
            print(f'\n processing：{feature.feature_name} =================================\n')
            if mr:
                self.process_mr_lifecycle(feature, verbose=verbose)

            if 2 in self.DEBUG_RUN:
                print('\n=====================test design start============================\n')
                # 测试设计agent
                step2 = PipelineStep(
                    agent=self.test_designer,
                    template_text=self.cot2_desc,
                    expected_output=self.cot2_out,
                    output_file=str(Path('memory') / 'working_memory' / f'ts_{feature.feature_name}.json'),
                    verbose=verbose,
                    stream=self.stream,
                    debug=self.debug,
                    stage="design",
                )
                step2_out = step2.run(
                    sut=feature.get_context_summary(),
                    mr=read_file(Path('memory') / 'working_memory' / f'mr_{feature.feature_name}.json') if mr else None)
                if self.stream:
                    for chunk in step2_out:
                        content = getattr(chunk, "content", str(chunk))
                        print(normalize_display_newlines(content), end="", flush=True)
                else:
                    content = getattr(step2_out, "raw", str(step2_out))
                    print(normalize_display_newlines(content), end="", flush=True)
            # 提取代码上下文
            if 6 in self.DEBUG_RUN:
                context=get_code_context(str(self.sut_root),read_file(Path('memory') / 'working_memory' / f'ts_{feature.feature_name}.json'),self.language)
                write_file(Path('memory') / 'working_memory' / f'code_context_{feature.feature_name}.md',context)
            if 4 in self.DEBUG_RUN:
                print('\n=====================test development start============================\n')
                self.run_pipeline(feature=feature, verbose=verbose)
            # 经验总结
        # 还原全部测试文件
        restore_all()

    # 测试开发 pipeline（支持 Python / Java & pytest / Maven / Gradle）
    def run_pipeline(self, feature, verbose: bool = True):
        feature_name = getattr(feature, "feature_name", str(feature))
        language = self.language or "python"
        # 1. 初始生成

        initial_code = self._generate_initial_test(feature, verbose, language)
        print('==============initial_code end====================')
        # 2. 根据大模型输出中的 `## FILE:` 解析默认测试文件相对路径
        path_relative, _ = parse_file_and_code(initial_code)
        if path_relative:
            # 解析绝对路径
            resolved = self._resolve_test_file_path(path_relative)
            exist_file = Path('memory') / 'working_memory' / 'exist_test_file.txt'
            exist_file.parent.mkdir(parents=True, exist_ok=True)
            with open(exist_file, 'a', encoding='utf-8') as f:
                f.write(str(path_relative) + '\n')
            # 绝对路径
            default_test_file_path = str(resolved) if resolved else None
        else:
            default_test_file_path = None

        # 若模型未给出文件名，则按语言给一个通用名
        if not default_test_file_path:
            if language == "java":
                default_test_file_path = str(self.test_root / "GeneratedTest.java")
            else:
                default_test_file_path = str(self.test_root / "test_generated.py")

        # 3. 执行生成 + 修复循环，返回最终代码、是否成功以及最终测试文件路径和测试报告
        final_code, success, final_test_file_path, last_report = self._execute_repair_loop(
            initial_code=initial_code,
            default_test_file_path=default_test_file_path,
            feature_name=feature_name,
            max_retries=self.max_retries,
            verbose=verbose,
            language=language,
        )

        # 隔离生成的测试文件，防止干扰后续任务
        if final_test_file_path:
            # 即使 success 为 False 也建议隔离，因为错误的代码更会阻塞编译
            move_to_quarantine(final_test_file_path, feature_name)
        if success:
            print(f"\n[Success] Test generation completed for {feature_name}.")
        else:
            print(f"\n[Failure] Test generation failed after retries for {feature_name}.")

        # 返回：最终测试代码、最后一次测试运行报告、整体是否成功
        return final_code, last_report, success

    def _generate_initial_test(self, feature, verbose: bool, language: str) -> str:
        """Step 4: 根据文本用例生成初始测试代码"""
        print("Step 4: Generating initial test code...")

        test_cases_json = read_file(Path('memory') / 'working_memory' / f'ts_{feature.feature_name}.json')

        step4 = PipelineStep(
            agent=self.test_developer,
            template_text=self.cot4_desc,  # 之前定义的 Phase 2 Prompt
            expected_output=self.cot4_out,
            output_file='',  # 暂时不直接写文件，只获取结果
            verbose=verbose,
            stream=self.stream,
            debug=self.debug,
            stage="develop",
        )

        # 执行生成
        output = step4.run(
            test_cases=test_cases_json,
            test_file_path=str(self.test_root),
            sut_root=str(self.sut_root),
            file_tree=self.ps,
            language=language,
            exist_test_file=read_file(Path('memory') / 'working_memory' / 'exist_test_file.txt') if (Path('memory') / 'working_memory' / 'exist_test_file.txt').exists() else '',
            code_context=read_file(Path('memory') / 'working_memory' / f'code_context_{feature.feature_name}.md'),
        )

        full_content = _kickoff_text(output)
        print(normalize_display_newlines(full_content), end="", flush=True)
        return full_content

    # 迭代修复、验证
    def _execute_repair_loop(
            self,
            initial_code: str,
            default_test_file_path: str,
            feature_name: str,
            max_retries: int,
            verbose: bool,
            language: str,
    ) -> Tuple[str, bool, str, str]:

        # --- 辅助内部函数：执行解析、写入并运行测试 ---
        def _run_tests(code_to_run: str) -> Tuple[bool, str, list, str, str]:
            # 解析代码和相对路径
            path_relative, parsed_code = parse_file_and_code(code_to_run)
            resolved = self._resolve_test_file_path(path_relative) if path_relative else None
            test_path = str(resolved) if resolved else default_test_file_path
            # 保存代码
            save_code_to_file(parsed_code, test_path)
            test_cases_list = []
            # 运行测试
            if language == "python":
                conda_env = os.environ.get("CONDA_ENV", None)
                is_pass, exec_report = self._run_pytest(test_path, conda_env)
            else:
                test_class = Path(test_path).stem
                runner = JavaTestRunnerTool(sut_root=self.sut_root, dataset_root=self.data.dataset_root,
                                            build_tool=self.build)
                result = runner.run_java_tests(test_class)
                is_pass = result.success
                exec_report = result.error_msg
                test_cases_list = result.test_cases

            return is_pass, exec_report, test_cases_list, test_path, parsed_code

        # 当前轮次的代码，可能包含其他文字解释
        current_code = initial_code
        print("\n=== 运行初始测试用例 ===")
        # 运行结果、log、测试用例详细结果、解析出的测试文件绝对路径、解析后的代码
        passed, report, test_cases, current_test_file_path, code = _run_tests(current_code)
        last_report = report

        print(f'--- passed: {passed} ---')
        print(f'--- error log: {report} ---')

        # 如果通过直接结束
        if passed:
            print("[Pass] Initial run passed successfully.")
            return current_code, True, current_test_file_path, last_report

        # 如果失败
        # --- 收集失败用例信息 ---
        # 按type去重
        current_failed_tests = []
        seen_error_types = set()

        for tc in test_cases:
            if tc.status in ["FAILED", "ERROR"]:
                # 获取 error_type，做兜底处理
                err_type = getattr(tc, 'error_type', None) or "UnknownErrorType"

                # 按 error_type 去重
                if err_type not in seen_error_types:
                    seen_error_types.add(err_type)

                    # 直接将原始的 tc 对象加入数组
                    current_failed_tests.append(tc)
        # 如果不是构建错误
        if current_failed_tests is not None and len(current_failed_tests) > 0:
            # 记录初始的失败日志
            write_marked_block(feature_name, 'TEST_CASE', code)
            write_marked_block(feature_name, 'STATUS', 'PASS' if passed else 'FAIL')
            write_marked_block(feature_name, 'ERROR_TYPE', current_failed_tests[0].error_type)
            write_marked_block(feature_name, 'ERROR_LOG', current_failed_tests[0].message)
        aggregated_experiences = []
        if self.experience:
            print("\n===  检索历史经验 ===")
            aggregated_experiences = []
            # 如果有失败的测试，没有编译错误
            if current_failed_tests:
                # 对多个犯相同错误的测试，去重，选一个代表性的
                # 提取当前测试文件的测试用例的不同错误，分别检索
                for tc in current_failed_tests:
                    # todo 使用测试代码作为场景
                    exp = search_exp(tc.error_type, tc.message, tc.test_name, 2, True)
                    if exp:
                        aggregated_experiences.append(f"### Experience for error [{tc.error_type}]:\n{exp}")
            # 编译失败，没有失败的测试信息，直接用编译器报错修
            else:
                print("⚠️ No specific test cases found. Attempting fallback global search...")

        # 如果命中经验且开启经验
        if self.experience and aggregated_experiences :
            print("\n===  命中经验：使用经验修复 ===")
            final_experience_prompt = "\n\n".join(aggregated_experiences)

            # 流程图：使用经验修复
            current_code = self._repair_code(code, report, feature_name, verbose, experience=final_experience_prompt)

            # 再次运行验证 (流程图里隐含的运行，走向pass的判断节点)
            passed, report, test_cases, current_test_file_path, code = _run_tests(current_code)
            last_report = report
            write_marked_block(feature_name, 'TEST_CASE', code)
            write_marked_block(feature_name, 'STATUS', 'PASS' if passed else 'FAIL')
            # 对应流程图：pass -> true
            if passed:
                print("[Pass] Tests passed after experience-based repair.")

                # todo ：增加经验被成功复用次数
                return current_code, True, current_test_file_path, last_report
            else:
                write_marked_block(feature_name, 'ERROR_LOG', report)
                # todo 看一些是否部分被修好，或是原来的错误被修好
                # 对应流程图：pass -> false
                print("[Experience Repair Failed] Falling back to multi-round repair.")
                # todo ：总结失败原因、增加经验无法被复用次数
        # 没有命中经验
        else:
            print("[No Experience Hit] Proceeding directly to multi-round repair.")
        # 没命中/命中了没修好，自己迭代修
        print("\n===  多轮修复 ===")
        # 迭代n轮修复
        for attempt in range(max_retries):
            print(f"\n--- Multi-round Validation Attempt {attempt + 1}/{max_retries} ---")

            # 多轮修复使用标准 LLM repair（不携带特定经验）
            current_code = self._repair_code(code, report, feature_name, verbose, experience=None)

            # 流程图：运行
            passed, report, test_cases, current_test_file_path, code = _run_tests(current_code)
            print(f'--- passed: {passed} ---')
            print(f'--- error log: {report} ---')
            last_report = report
            write_marked_block(feature_name, 'TEST_CASE', code)
            write_marked_block(feature_name, 'STATUS', 'PASS' if passed else 'FAIL') ,
            # 流程图：pass?
            if passed:
                print("[Pass] Tests compiled and ran successfully after multi-round repair.")
                summarize_experience(feature_name)
                return current_code, True, current_test_file_path, last_report
            write_marked_block(feature_name, 'ERROR_LOG', report)
        # 流程图：多轮修复循环结束且最终未 pass
        print("[Stop] Max retries reached. Validation failed.")
        # todo：总结经验
        summarize_experience(feature_name)
        return current_code, False, current_test_file_path, last_report

    def _normalize_test_file_relative(self, path_relative: str) -> Optional[str]:
        """
        规范化模型返回的 FILE 路径，避免重复前缀或错误路径。
        - Java: 去掉 src/test/java 前缀；
        - Python: 去掉 tests/ 前缀；
        返回相对 self.test_root 的路径。
        """
        if not path_relative or not path_relative.strip():
            return path_relative.strip() or None
        p = path_relative.strip().replace("\\", "/").lstrip("/")

        # Java: 去掉 src/test/java 前缀（大模型可能幻觉出完整路径）
        for prefix in ("src/test/java/", "src/test/java"):
            if p.lower().startswith(prefix.lower()):
                p = p[len(prefix):].lstrip("/")
                break

        # Python: 去掉 tests/ 前缀，避免 test_root/tests/xxx 重复
        if p.startswith("tests/"):
            p = p[6:].lstrip("/")
        elif p == "tests":
            p = ""
        return p if p else None

    def _resolve_test_file_path(self, path_relative: str) -> Optional[Path]:
        """
        将规范化后的相对路径解析为绝对路径；若规范化后为空则返回 None。
        """
        normalized = self._normalize_test_file_relative(path_relative)
        if not normalized:
            return None
        return self.test_root / normalized

    def _run_pytest(self, file_path: str, conda_env: str = None) -> Tuple[bool, str]:
        """运行 Pytest，生成并解析结构化 JSON 报告。"""
        root_dir = self.sut_root
        if not root_dir.exists():
            return False, f"Error: SUT directory does not exist: {root_dir}"

        ini_path = root_dir / "pytest.ini"
        if not ini_path.exists():
            try:
                ini_path.write_text("[pytest]\npythonpath = .\n", encoding="utf-8")
            except Exception as e:
                return False, f"Failed to create pytest.ini: {str(e)}"

        report_file = root_dir / ".report.json"
        abs_file_path = Path(file_path).resolve()

        base_cmd = [
            "pytest",
            str(abs_file_path),
            "--json-report",
            f"--json-report-file={report_file}",
        ]
        if conda_env:
            cmd = ["conda", "run", "-n", conda_env, "--no-capture-output"] + base_cmd
        else:
            cmd = base_cmd

        try:
            subprocess.run(
                cmd, cwd=str(root_dir), capture_output=True, text=True, timeout=60
            )

            if not report_file.exists():
                return False, "Fatal: No report generated. Likely SyntaxError or import error.\n"

            with report_file.open("r", encoding="utf-8") as f:
                data = json.load(f)

            is_structure_valid = True
            failure_logs: List[str] = []

            # 收集阶段错误
            if "collectors" in data:
                for collector in data["collectors"]:
                    if collector.get("outcome") == "failed":
                        is_structure_valid = False
                        failure_logs.append(
                            "=== COLLECTION ERROR ===\n"
                            + str(collector.get("longrepr", "Unknown"))
                        )

            for test in data.get("tests", []):
                nodeid = test.get("nodeid", "")

                # setup 阶段错误
                if test.get("setup", {}).get("outcome") == "failed":
                    is_structure_valid = False
                    failure_logs.append(
                        f"=== SETUP ERROR in {nodeid} ===\n"
                        + str(test["setup"].get("longrepr", ""))
                    )
                    continue

                # call 阶段错误
                if test.get("call", {}).get("outcome") == "failed":
                    call_data = test["call"]
                    longrepr = call_data.get("longrepr", "")
                    traceback = call_data.get("traceback", [])
                    is_assertion = any(
                        "AssertionError" in t.get("message", "") for t in traceback
                    )
                    error_type = (
                        "ASSERTION FAILURE" if is_assertion else "RUNTIME CRASH"
                    )
                    log_entry = f"=== {error_type} in {nodeid} ===\n{longrepr}\n"
                    if call_data.get("stdout"):
                        log_entry += f"--- STDOUT ---\n{call_data['stdout']}\n"
                    failure_logs.append(log_entry)
                    if not is_assertion:
                        is_structure_valid = False

            if not failure_logs:
                return True, "All tests passed."
            return is_structure_valid, "\n".join(failure_logs)

        except subprocess.TimeoutExpired:
            return False, "Test run timed out."
        except Exception as e:
            return False, f"System Error: {str(e)}"

    def _repair_code(self, broken_code: str, error_log: str, feature_name: str, verbose: bool, experience) -> str:
        """调用修复 Agent"""
        fix_step = PipelineStep(
            agent=self.test_developer,  # 复用同一个 Agent 或专用 Repair Agent
            template_text=self.cot4_fix,  # 之前定义的 Repair Prompt
            expected_output=self.cot4_out,
            output_file='',
            verbose=verbose,
            stream=self.stream,
            debug=self.debug,
            stage="repair",
        )

        output = fix_step.run(
            broken_code=broken_code,
            error_log=error_log,
            file_tree=self.ps,
            language=self.language or "python",
            code_context=read_file(Path('memory') / 'working_memory' / f'code_context_{feature_name}.md'),
            experience=experience
        )

        repaired_code = _kickoff_text(output)
        print(normalize_display_newlines(repaired_code), end="", flush=True)

        return repaired_code



    def process_mr_lifecycle(self, feature, verbose=False):
        """
        MR 生命周期管理：生成 -> (评审 -> 修复/删除) * N
        """
        print(f'\n=== Starting MR Lifecycle for {feature.feature_name} ===\n')

        # 定义文件路径
        mr_file_path = str(Path('memory') / 'working_memory' / f'mr_{feature.feature_name}.json')

        # 1. 初始生成 (Initial Generation)
        print('[MR Phase 1] Generating Initial Metamorphic Relations...')
        step_gen = PipelineStep(
            agent=self.mr_parser,
            template_text=self.mr_desc,
            expected_output=self.mr_parse_out,
            output_file=mr_file_path,
            verbose=verbose,
            stream=self.stream,
            debug=self.debug,
            stage="mr_generate",
        )
        # 获取初始 MR 内容
        retrieved = vector_db.search(feature.get_context_summary(), 3)
        write_file(Path('memory') / 'working_memory' / f'mr_retrieved_{feature.feature_name}.json',
                   json.dumps([{'id': r['id'], 'similarity': r['similarity'], 'content': r['content'],
                                'signature': (r.get('metadata') or {}).get('signature')} for r in retrieved],
                              ensure_ascii=False, indent=2))
        gen_stream = step_gen.run(
            sut=feature.get_context_summary(),
            retrieved_examples_json=retrieved
        )

        current_mr_content = _kickoff_text(gen_stream)
        print(normalize_display_newlines(current_mr_content), end="", flush=True)

        write_file(Path('memory') / 'working_memory' / f'mr_initial_{feature.feature_name}.json',
                   str(current_mr_content))
        if os.environ.get("CMATG_NO_REVIEW") == "1":
            print("\n[MR] review skipped (CMATG_NO_REVIEW)")
            return current_mr_content
        # 2. 评审-修复 循环 (Review-Fix Loop)
        for i in range(self.max_review_iterations):
            print(f'\n\n[MR Phase 2] Review Round {i + 1}/{self.max_review_iterations}...')

            review_file_path = str(Path('memory') / 'working_memory' / f'mr_review_{feature.feature_name}_round_{i}.json')

            # 2.1 执行评审 (Review)
            step_review = PipelineStep(
                agent=self.mr_parser,
                template_text=self.mr_review_desc,  # 使用包含 CoT 的 Prompt
                expected_output=self.mr_review_out,
                output_file=review_file_path,
                verbose=verbose,
                stream=self.stream,
                debug=self.debug,
                stage="mr_review",
            )

            review_stream = step_review.run(
                sut=feature.get_context_summary(),
                mr_content=current_mr_content,
            )

            review_feedback = _kickoff_text(review_stream)
            print(normalize_display_newlines(review_feedback), end="", flush=True)

            # 2.2 判断循环终止条件
            # 简单的判断逻辑：如果反馈中不包含 "Invalid" 或 "Risky"，且包含 "Valid"，则认为通过
            # 更严谨的做法是解析 review_feedback JSON
            if "Invalid" not in review_feedback and "Risky" not in review_feedback:
                print(f"\n[SUCCESS] MR Review Passed at round {i + 1}. No critical issues found.")
                break

            if i == self.max_review_iterations - 1:
                print(f"\n[WARNING] Max iterations reached. Stopping optimization.")
                break

            if os.environ.get("CMATG_NO_REFINE") == "1":
                print("\n[MR] refinement skipped (CMATG_NO_REFINE)")
                break

            # 2.3 执行修复 (Fix)
            print(f'\n[MR Phase 3] Fixing MR based on feedback (Round {i + 1})...')
            step_fix = PipelineStep(
                agent=self.mr_parser,  # 或 test_developer
                template_text=self.mr_fix_desc,
                expected_output=self.mr_parse_out,  # 修复后仍需保持标准 MR 格式
                output_file=mr_file_path,  # 覆盖更新 MR 文件
                verbose=verbose,
                stream=self.stream,
                debug=self.debug,
                stage="mr_fix",
            )

            fix_stream = step_fix.run(
                sut=feature.get_context_summary(),
                previous_mr=current_mr_content,
                feedback=review_feedback,
            )

            current_mr_content = _kickoff_text(fix_stream)
            print(normalize_display_newlines(current_mr_content), end="", flush=True)

        return current_mr_content



def archive_working_memory():
    src_dir = Path('memory') / 'working_memory'
    if not src_dir.exists():
        return
    test_plan_file = src_dir / 'test_plan.json'
    if not test_plan_file.exists():
        return
    memory = Memory(str(test_plan_file))
    project_name = memory.project_name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model = os.environ.get("MODEL", "")
    dst_dir = Path('memory') / 'Long-Term' / f"{timestamp}_{project_name}_{model}"
    dst_dir.mkdir(parents=True, exist_ok=True)

    for name in os.listdir(src_dir):
        src_path = src_dir / name
        dst_path = dst_dir / name
        shutil.move(str(src_path), str(dst_path))


