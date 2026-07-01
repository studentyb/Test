# agent.py
import json
import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional, Dict, Set

from openai import OpenAI

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
from piplines.core import PipelineStep, LLMCallError
from tools.grep import get_code_context
from utils.dataset_utils import load_dataset
from utils.file_utils import (
    read_file, normalize_display_newlines, write_marked_block,
    restore_all, move_to_quarantine, save_code_to_file, write_file,
    collect_output, render_prompt, copy_files_to_working_memory,
)
from utils.java_test_runner import JavaTestRunnerTool
from utils.pytest_test_runner import PytestTestRunner
from utils.memory_utils import Memory
from utils.parser import parse_file_and_code, parse_debug_report
from utils.progress import ProgressTracker
from utils.tree_utils import get_directory_tree

log = logging.getLogger("mate")

# 步骤编号 → 说明
# 1  = Plan        测试计划
# 2  = Design      测试设计
# 3  = Context     代码上下文提取
# 4  = eXecute     测试开发 + 修复循环
# 5  = debuG       运行 & 分析测试报告
STEP_PLAN = 1
STEP_DESIGN = 2
STEP_CONTEXT = 3
STEP_EXECUTE = 4
STEP_DEBUG = 5
ALL_STEPS = {STEP_PLAN, STEP_DESIGN, STEP_CONTEXT, STEP_EXECUTE, STEP_DEBUG}


def _banner(tag: str, title: str):
    log.info(f"[{tag}] {'=' * 20} {title} {'=' * 20}")


def _setup_logging():
    """确保 'mate' logger 有一个 StreamHandler。"""
    mate_log = logging.getLogger("mate")
    if mate_log.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    ))
    mate_log.addHandler(handler)
    if not mate_log.level:
        mate_log.setLevel(logging.INFO)


class TestAgentAppWOT:

    def __init__(
        self,
        *,
        dataset_name: str,
        steps: Set[str] = None,
        stream: bool = True,
        debug: bool = False,
        exp: bool = True,
        max_retries: int = 3,
    ):
        self.steps: Set[str] = steps if steps is not None else ALL_STEPS
        self.experience = exp
        self.dataset_name = dataset_name
        self.debug = debug
        self.stream = stream
        self.data = load_dataset(dataset_name, strict=True)

        # 语言 / 构建工具 / 路径配置
        self.sut_root: Path = Path(self.data.sut_root).resolve()
        self.language: str = (self.data.language or "").strip().lower()
        self.test_root: Path = Path(self.data.test_root).resolve()

        if (self.data.dataset_root / "pom.xml").exists():
            self.build: str = "maven"
        elif (self.data.dataset_root / "build.gradle").exists() or (
                self.data.dataset_root / "build.gradle.kts").exists():
            self.build = "gradle"
        else:
            self.build = ""

        # Agents
        self.test_architect = create_test_architect()
        self.test_designer = create_test_designer()
        self.mr_parser = create_mr_parser()
        self.test_reviewer = create_test_reviewer()
        self.test_developer = create_test_development_engineer()
        self.test_debugger = create_test_debugger()
        self.retriever_agent = create_context_retriever()

        # Prompts
        self.cot1_desc = read_file('prompt/test_plan/test_plan.md')
        self.cot1_out = read_file('prompt/test_plan/test_plan_out.md')
        self.mr_desc = read_file('prompt/mr_parse/mr_parse_input.md')
        self.mr_parse_out = read_file('prompt/mr_parse/mr_parse_output.md')
        self.mr_review_desc = read_file('prompt/mr_parse/mr_review.md')
        self.mr_review_out = read_file('prompt/mr_parse/mr_review_out.md')
        self.mr_fix_desc = read_file('prompt/mr_parse/mr_fix.md')
        self.cot4_desc = read_file('prompt/test_development/test_develop_wo_two.md')
        self.cot4_fix = read_file('prompt/test_development/self_fix.md')
        self.cot4_out = read_file('prompt/test_development/test_develop_out.md')
        self.cot5_desc = read_file('prompt/test_debugger/test_debug.md')

        self.max_review_iterations = 1
        self.max_retries = max_retries
        self.ps = get_directory_tree(str(self.sut_root))

        self.tracker = ProgressTracker(enabled=True)
        self.repair_messages=None

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
    def run(self, *, verbose=False, mr=False):
        _setup_logging()
        with self.tracker:
            # P — 测试计划
            if STEP_PLAN in self.steps:
                _banner("P", "Test Plan")
                archive_working_memory()
                try:
                    step1 = PipelineStep(
                        agent=self.test_architect,
                        template_text=self.cot1_desc,
                        expected_output=self.cot1_out,
                        output_file="memory/working_memory/test_plan.json",
                        verbose=verbose,
                        stream=self.stream,
                        debug=self.debug,
                    )
                    step1_output = step1.run(
                        srs=self.data.srs,
                        class_diagram=self.data.uml_class,
                        sequence_diagram=self.data.uml_sequence,
                        add=self.data.architecture_design,
                    )
                    collect_output(step1_output, result_attr="raw")
                except (LLMCallError, Exception) as e:
                    log.error(f"[1] Test Plan generation failed: {e}")
                    if not Path("memory/working_memory/test_plan.json").exists():
                        log.error("[1] No test_plan.json available, cannot continue")
                        restore_all()
                        return

            try:
                memory = Memory('memory/working_memory/test_plan.json')
                features = list(memory.iter_all_features())
            except (json.JSONDecodeError, FileNotFoundError, Exception) as e:
                log.error(f"[P] Failed to load test plan: {e}")
                restore_all()
                return

            if not features:
                log.warning("[P] No features found in test plan, nothing to process")
                restore_all()
                return

            oid = self.tracker.add_overall(total_features=len(features))

            for idx, feature in enumerate(features, 1):
                active_steps = [s for s in [STEP_DESIGN, STEP_CONTEXT, STEP_EXECUTE, STEP_DEBUG] if s in self.steps]
                fid = self.tracker.add_feature(feature.feature_name, total_stages=len(active_steps))
                self.tracker.update_stage(oid, f"[bold]Feature {idx}/{len(features)}")

                log.info(f"[Feature] Processing: {feature.feature_name}")

                try:
                    if mr:
                        self.process_mr_lifecycle(feature, verbose=verbose)

                    # # D — 测试设计
                    # if STEP_DESIGN in self.steps:
                    #     self.tracker.update_stage(fid, f"[D] Test Design — {feature.feature_name}")
                    #     _banner("D", "Test Design")
                    #     step2 = PipelineStep(
                    #         agent=self.test_designer,
                    #         template_text=self.cot2_desc,
                    #         expected_output=self.cot2_out,
                    #         output_file=f"memory/working_memory/ts_{feature.feature_name}.json",
                    #         verbose=verbose,
                    #         stream=self.stream,
                    #         debug=self.debug,
                    #     )
                    #     step2_out = step2.run(
                    #         sut=feature.get_context_summary(),
                    #         mrs=read_file(
                    #             f"memory/working_memory/mr_{feature.feature_name}.json") if os.path.exists(
                    #             f"memory/working_memory/mr_{feature.feature_name}.json") else None,
                    #     )
                    #     collect_output(step2_out, result_attr="raw")
                    #     self.tracker.advance(fid)

                    # C — 代码上下文提取
                    if STEP_CONTEXT in self.steps:
                        self.tracker.update_stage(fid, f"[C] Code Context — {feature.feature_name}")
                        _banner("C", "Code Context Extraction")
                        try:
                            context = get_code_context(
                                str(self.sut_root),
                                feature.get_context_summary(),
                                self.language,
                            )
                            write_file(Path(f'memory/working_memory/code_context_{feature.feature_name}.md'), context)
                        except Exception as e:
                            log.warning(f"[C] Code context extraction failed for {feature.feature_name}: {e}")
                            write_file(Path(f'memory/working_memory/code_context_{feature.feature_name}.md'), "")
                        self.tracker.advance(fid)

                    # X — 测试开发 + 修复循环
                    if STEP_EXECUTE in self.steps:
                        self.tracker.update_stage(fid, f"[X] Test Development — {feature.feature_name}")
                        _banner("X", "Test Development")
                        self.run_pipeline(feature=feature, verbose=verbose)
                        self.tracker.advance(fid)

                    # G — 运行 & Debug 分析
                    if STEP_DEBUG in self.steps:
                        self.tracker.update_stage(fid, f"[G] Debug & Report — {feature.feature_name}")
                        _banner("G", "Test Debug & Report")
                        debug_report = self._run_debug_step(feature=feature, verbose=verbose)
                        if debug_report:
                            report_path = f"memory/working_memory/debug_report_{feature.feature_name}.json"
                            write_file(Path(report_path), json.dumps(debug_report, indent=2, ensure_ascii=False))
                            log.info(f"[G] Report saved → {report_path}")
                        self.tracker.advance(fid)

                except Exception as e:
                    log.error(
                        f"[Feature] Error processing feature '{feature.feature_name}': {e}",
                        exc_info=True,
                    )
                    log.info(f"[Feature] Skipping '{feature.feature_name}', continuing with next feature …")

                self.tracker.finish(fid)
                self.tracker.advance(oid)

            self.tracker.finish(oid)
            restore_all()

    # ------------------------------------------------------------------
    # 测试开发 pipeline
    # ------------------------------------------------------------------
    def run_pipeline(self, feature, verbose: bool = True):
        feature_name = getattr(feature, "feature_name", str(feature))
        language = self.language or "python"

        try:
            initial_code = self._generate_initial_test(feature, verbose, language)
        except (LLMCallError, FileNotFoundError, Exception) as e:
            log.error(f"[X] Initial test generation failed for {feature_name}: {e}")
            return "", "", False

        if not initial_code or not initial_code.strip():
            log.error(f"[X] Empty initial code for {feature_name}, skipping pipeline")
            return "", "", False

        log.info("[X] Initial code generation done")

        try:
            path_relative, _ = parse_file_and_code(initial_code)
        except Exception as e:
            log.warning(f"[X] Failed to parse file path from generated code: {e}")
            path_relative = None

        if path_relative:
            resolved = self._resolve_test_file_path(path_relative)
            file_dir = os.path.dirname('memory/working_memory/exist_test_file.txt')
            if file_dir and not os.path.exists(file_dir):
                os.makedirs(file_dir)
            with open('memory/working_memory/exist_test_file.txt', 'a', encoding='utf-8') as f:
                f.write(str(path_relative) + '\n')
            default_test_file_path = str(resolved) if resolved else None
        else:
            default_test_file_path = None

        if not default_test_file_path:
            if language == "java":
                default_test_file_path = str(self.test_root / "GeneratedTest.java")
            else:
                default_test_file_path = str(self.test_root / "test_generated.py")

        try:
            final_code, success, final_test_file_path, last_report = self._execute_repair_loop(
                initial_code=initial_code,
                default_test_file_path=default_test_file_path,
                feature_name=feature_name,
                max_retries=self.max_retries,
                verbose=verbose,
                language=language,
            )
        except Exception as e:
            log.error(f"[X] Repair loop failed for {feature_name}: {e}", exc_info=True)
            return initial_code, "", False

        if final_test_file_path:
            move_to_quarantine(final_test_file_path, feature_name)

        if success:
            log.info(f"[X] PASS — Test generation completed for {feature_name}")
        else:
            log.warning(f"[X] FAIL — Test generation failed after retries for {feature_name}")

        return final_code, last_report, success

    # ------------------------------------------------------------------
    # 初始测试代码生成
    # ------------------------------------------------------------------
    def _generate_initial_test(self, feature, verbose: bool, language: str) -> str:
        log.info("[X] Generating initial test code …")

        try:
            test_cases_json = feature.get_context_summary()
        except FileNotFoundError:
            log.error(f"[X] Test design file not found for {feature.feature_name}")
            raise

        step4 = PipelineStep(
            agent=self.test_developer,
            template_text=self.cot4_desc,
            expected_output=self.cot4_out,
            output_file='',
            verbose=verbose,
            stream=self.stream,
            debug=self.debug,
        )

        output = step4.run(
            sut=feature.get_context_summary(),
            test_file_path=str(self.test_root),
            sut_root=str(self.sut_root),
            file_tree=self.ps,
            language=language,
            exist_test_file=read_file('memory/working_memory/exist_test_file.txt') if os.path.exists(
                'memory/working_memory/exist_test_file.txt') else '',
            code_context=read_file(f'memory/working_memory/code_context_{feature.feature_name}.md'),
            mrs=read_file(
                            f"memory/working_memory/mr_{feature.feature_name}.json") if os.path.exists(
                            f"memory/working_memory/mr_{feature.feature_name}.json") else None,
        )

        result = collect_output(output)
        if not result or not result.strip():
            log.warning("[X] LLM returned empty output for initial test generation")
        return result

    # ------------------------------------------------------------------
    # 迭代修复、验证
    # ------------------------------------------------------------------
    def _execute_repair_loop(
            self,
            initial_code: str,
            default_test_file_path: str,
            feature_name: str,
            max_retries: int,
            verbose: bool,
            language: str,
    ) -> Tuple[str, bool, str, str]:
        self.repair_messages=None
        def _run_tests(code_to_run: str) -> Tuple[bool, str, list, str, str]:
            try:
                path_relative, parsed_code = parse_file_and_code(code_to_run)
            except Exception as e:
                log.warning(f"[X] Failed to parse code output: {e}")
                parsed_code = code_to_run.strip()
                path_relative = None

            resolved = self._resolve_test_file_path(path_relative) if path_relative else None
            test_path = str(resolved) if resolved else default_test_file_path
            save_code_to_file(parsed_code, test_path)

            if language == "python":
                runner = PytestTestRunner(
                    dataset_root=self.data.dataset_root,
                    conda_env=os.environ.get("CONDA_ENV", "mate_run"),
                )
                result = runner.run_pytest(test_path)
            else:
                test_class = Path(test_path).stem
                runner = JavaTestRunnerTool(
                    sut_root=self.sut_root,
                    dataset_root=self.data.dataset_root,
                    build_tool=self.build,
                )
                result = runner.run_java_tests(test_class)

            return result.success, result.error_msg, result.test_cases, test_path, parsed_code

        current_code = initial_code
        current_test_file_path = default_test_file_path
        last_report = ""

        log.info("[X] Running initial tests …")
        try:
            passed, report, test_cases, current_test_file_path, code = _run_tests(current_code)
            last_report = report
        except Exception as e:
            log.error(f"[X] Initial test run failed: {e}")
            return current_code, False, current_test_file_path, str(e)

        log.info(f"[X] Result: passed={passed}")
        if self.debug:
            log.debug(f"[X] Error log: {report}")

        if passed:
            log.info("[X] PASS — Initial run succeeded")
            return current_code, True, current_test_file_path, last_report

        current_failed_tests = []
        seen_error_types = set()
        for tc in test_cases:
            try:
                if tc.status in ["FAILED", "ERROR"]:
                    err_type = getattr(tc, 'error_type', None) or "UnknownErrorType"
                    if err_type not in seen_error_types:
                        seen_error_types.add(err_type)
                        current_failed_tests.append(tc)
            except Exception as e:
                log.warning(f"[X] Failed to process test case: {e}")

        write_marked_block(feature_name, 'TEST_CASE', code)
        write_marked_block(feature_name, 'STATUS', 'FAIL')
        if current_failed_tests:
            write_marked_block(feature_name, 'ERROR_TYPE', current_failed_tests[0].error_type)
            write_marked_block(feature_name, 'ERROR_LOG', current_failed_tests[0].message)
        else:
            write_marked_block(feature_name, 'ERROR_TYPE', 'BuildError')
            write_marked_block(feature_name, 'ERROR_LOG', report)

        aggregated_experiences = []
        if self.experience:
            log.info("[X] Searching historical experience …")
            try:
                if current_failed_tests:
                    for tc in current_failed_tests:
                        exp = search_exp(tc.error_type, tc.message, tc.test_name, 2, True)
                        if exp:
                            aggregated_experiences.append(f"### Experience for error [{tc.error_type}]:\n{exp}")
                else:
                    log.warning("[X] No structured test cases — using build error log for experience search")
                    exp = search_exp("BuildError", report[:2000], feature_name, 2, True)
                    if exp:
                        aggregated_experiences.append(f"### Experience for build error:\n{exp}")
            except Exception as e:
                log.warning(f"[X] Experience search failed: {e}")

        if self.experience and aggregated_experiences:
            log.info("[X] Experience hit — attempting experience-based repair")
            final_experience_prompt = "\n\n".join(aggregated_experiences)
            try:
                current_code = self._repair_code(code, report, feature_name, verbose, experience=final_experience_prompt)
                passed, report, test_cases, current_test_file_path, code = _run_tests(current_code)
                last_report = report
                write_marked_block(feature_name, 'TEST_CASE', code)
                write_marked_block(feature_name, 'STATUS', 'PASS' if passed else 'FAIL')

                if passed:
                    log.info("[X] PASS — Tests passed after experience-based repair")
                    return current_code, True, current_test_file_path, last_report
                else:
                    write_marked_block(feature_name, 'ERROR_LOG', report)
                    log.warning("[X] Experience repair failed — falling back to multi-round repair")
            except (LLMCallError, Exception) as e:
                log.warning(f"[X] Experience-based repair failed: {e}, falling back to multi-round repair")
        else:
            log.info("[X] No experience hit — proceeding to multi-round repair")

        log.info("[X] Starting multi-round repair …")
        for attempt in range(max_retries):
            log.info(f"[X] Repair attempt {attempt + 1}/{max_retries}")
            try:
                current_code = self._repair_code(code, report, feature_name, verbose, experience=None)
                passed, report, test_cases, current_test_file_path, code = _run_tests(current_code)
            except (LLMCallError, Exception) as e:
                log.warning(f"[X] Repair attempt {attempt + 1} failed: {e}")
                continue

            log.info(f"[X] Result: passed={passed}")
            if self.debug:
                log.debug(f"[X] Error log: {report}")

            last_report = report
            write_marked_block(feature_name, 'TEST_CASE', code)
            write_marked_block(feature_name, 'STATUS', 'PASS' if passed else 'FAIL')

            if passed:
                log.info("[X] PASS — Tests passed after multi-round repair")
                _safe_summarize_experience(feature_name)
                return current_code, True, current_test_file_path, last_report
            write_marked_block(feature_name, 'ERROR_LOG', report)

        log.warning("[X] STOP — Max retries reached, validation failed")
        _safe_summarize_experience(feature_name)
        return current_code, False, current_test_file_path, last_report

    # ------------------------------------------------------------------
    # 路径工具
    # ------------------------------------------------------------------
    def _normalize_test_file_relative(self, path_relative: str) -> Optional[str]:
        if not path_relative or not path_relative.strip():
            return path_relative.strip() or None
        p = path_relative.strip().replace("\\", "/").lstrip("/")

        for prefix in ("src/test/java/", "src/test/java"):
            if p.lower().startswith(prefix.lower()):
                p = p[len(prefix):].lstrip("/")
                break

        if p.startswith("tests/"):
            p = p[6:].lstrip("/")
        elif p == "tests":
            p = ""
        return p if p else None

    def _resolve_test_file_path(self, path_relative: str) -> Optional[Path]:
        normalized = self._normalize_test_file_relative(path_relative)
        if not normalized:
            return None
        return self.test_root / normalized

    # ------------------------------------------------------------------
    # 修复 Agent
    # ------------------------------------------------------------------
    # def _repair_code(self, broken_code: str, error_log: str, feature_name: str, verbose: bool, experience) -> str:
        # fix_step = PipelineStep(
        #     agent=self.test_developer,
        #     template_text=self.cot4_fix,
        #     expected_output=self.cot4_out,
        #     output_file='',
        #     verbose=verbose,
        #     stream=self.stream,
        #     debug=self.debug,
        # )
        #
        # output = fix_step.run(
        #     broken_code=broken_code,
        #     error_log=error_log,
        #     file_tree=self.ps,
        #     language=self.language or "python",
        #     code_context=read_file(f'memory/working_memory/code_context_{feature_name}.md'),
        #     experience=experience,
        # )
        #
        # return collect_output(output)
    def _repair_code(
            self,
            broken_code: str,
            error_log: str,
            feature_name: str,
            verbose: bool,
            experience=None
    ) -> str:

        # ✅ 初始化对话历史
        if not hasattr(self, "repair_messages") or self.repair_messages is None:
            self.repair_messages = []

        # =========================
        # 🥇 首轮：使用 Jinja 模板
        # =========================
        if len(self.repair_messages) == 0:

            try:
                code_context = read_file(
                    f'memory/working_memory/code_context_{feature_name}.md'
                )
            except Exception:
                code_context = ""

            full_prompt = render_prompt(
                self.cot4_fix,  # 你的 Jinja 模板
                language=self.language or "python",
                broken_code=broken_code,
                error_log=error_log,
                file_tree=self.ps,
                code_context=code_context,
                experience=experience or ""
            )

            # system prompt（建议单独放规则）
            system_prompt = """You are an expert software developer specializing in fixing unit tests.
    Return ONLY the fixed test code. Do NOT include explanations."""

            self.repair_messages.append({
                "role": "system",
                "content": system_prompt
            })

            self.repair_messages.append({
                "role": "user",
                "content": full_prompt
            })

        # =========================
        # 🔁 后续轮次：仅增量
        # =========================
        else:

            incremental_prompt = f"""
    The previous fix did NOT pass the tests.

    Here is the updated information:

    ## Error Log
    {error_log}

    Please fix the test code again.If the issue cannot be fixed due to missing information, delete the erroneous test case.
    Remember:
    - Return ONLY the full fixed code
    **Final Output Format**:
## FILE: com/example/XXXTest.java  or test_xx.py（relative to the Test Source Directory.）
```java or python
code
```
    """

            self.repair_messages.append({
                "role": "user",
                "content": incremental_prompt.strip()
            })

        # =========================
        # 🚀 调用 LLM
        # =========================
        try:
            # ✅ 从环境变量读取
            api_key = os.environ.get("OPENAI_API_KEY")
            base_url = os.environ.get("OPENAI_BASE_URL")

            client = OpenAI(
                api_key=api_key,
                base_url=base_url
            )

            # ✅ 流式调用
            stream = client.chat.completions.create(
                model="qwen3-coder-next",
                messages=self.repair_messages,
                temperature=0,
                stream=True,
                max_tokens=16384
            )

            reply_chunks = []

            # ✅ 逐块接收
            for chunk in stream:
                delta = chunk.choices[0].delta

                if hasattr(delta, "content") and delta.content:
                    content_piece = delta.content
                    reply_chunks.append(content_piece)

                    # 👉 可选：实时打印（debug/verbose时很有用）
                    print(content_piece, end="", flush=True)

            # ✅ 拼接完整回复
            reply = "".join(reply_chunks)


        except Exception as e:
            return broken_code  # fallback

        # =========================
        # 🧠 记录 assistant 回复
        # =========================
        self.repair_messages.append({
            "role": "assistant",
            "content": reply
        })

        # =========================
        # ✂️ 可选：截断历史（防爆token）
        # =========================
        if len(self.repair_messages) > 10:
            self.repair_messages = self.repair_messages[-5:]

        return reply.strip()
    # ------------------------------------------------------------------
    # Debug 步骤
    # ------------------------------------------------------------------
    def _run_debug_step(self, feature, verbose: bool = True) -> Optional[Dict]:
        """从隔离区恢复测试文件 → 运行 → Debug Agent 分析 → 过滤测试错误 → 返回报告"""
        feature_name = getattr(feature, "feature_name", str(feature))
        language = self.language or "python"

        log_file = Path("memory/working_memory/recovery_map.json")
        if not log_file.exists():
            log.warning(f"[G] No quarantine log found, skipping debug for {feature_name}")
            return None

        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                recovery_map = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            log.error(f"[G] Failed to load recovery_map.json: {e}")
            return None

        target_q_path = None
        target_original_path = None
        for q_path, ori_path in recovery_map.items():
            if feature_name in Path(q_path).name:
                target_q_path = Path(q_path)
                target_original_path = Path(ori_path)
                break

        if not target_q_path or not target_q_path.exists():
            log.warning(f"[G] No quarantined test file found for {feature_name}, skipping")
            return None

        target_original_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(target_q_path), str(target_original_path))
        log.info(f"[G] Restored test file: {target_original_path}")

        try:
            log.info(f"[G] Running tests for {feature_name} …")
            if language == "python":
                runner = PytestTestRunner(
                    dataset_root=self.data.dataset_root,
                    conda_env=os.environ.get("CONDA_ENV", "mate_run"),
                )
                result = runner.run_pytest(str(target_original_path))
            else:
                test_class = target_original_path.stem
                runner = JavaTestRunnerTool(
                    sut_root=self.sut_root,
                    dataset_root=self.data.dataset_root,
                    build_tool=self.build,
                )
                result = runner.run_java_tests(test_class)

            total = len(result.test_cases)
            passed_cnt = sum(1 for tc in result.test_cases if tc.status == "PASSED")
            log.info(f"[G] Execution result: {passed_cnt}/{total} passed")

            if result.success:
                log.info(f"[G] All tests passed for {feature_name}")
                return {
                    "feature": feature_name,
                    "overall_pass_rate": f"{passed_cnt}/{total}",
                    "summary": "All tests passed. No SUT bugs detected.",
                    "test_results": [
                        {"test_name": tc.test_name, "status": "PASSED", "reason": ""}
                        for tc in result.test_cases
                    ],
                    "sut_bug_report": ""
                }

            # 有失败 → 调用 Debug Agent 分析
            log.info("[G] Invoking Debug Agent to analyze failures …")
            try:
                test_cases_json = read_file(f'memory/working_memory/ts_{feature_name}.json')
            except FileNotFoundError:
                log.warning(f"[G] Test design file not found for {feature_name}, using empty")
                test_cases_json = "[]"

            rel_test_path = os.path.relpath(str(target_original_path), str(self.sut_root))

            try:
                debug_step = PipelineStep(
                    agent=self.test_debugger,
                    template_text=self.cot5_desc,
                    expected_output="A structured JSON debug report classifying each failure as SUT_BUG or TEST_BUG.",
                    output_file='',
                    verbose=verbose,
                    stream=self.stream,
                    debug=self.debug,
                )

                output = debug_step.run(
                    language=language,
                    build=self.build,
                    sut_root=str(self.sut_root),
                    test_file_path=str(target_original_path),
                    rel_test_path=rel_test_path,
                    feature_name=feature_name,
                    test_cases_json=test_cases_json,
                    exec_report=result.error_msg,
                )

                raw_output = collect_output(output)
            except (LLMCallError, Exception) as e:
                log.error(f"[G] Debug Agent LLM call failed: {e}")
                return {
                    "feature": feature_name,
                    "overall_pass_rate": f"{passed_cnt}/{total}",
                    "summary": f"Debug Agent call failed: {e}",
                    "test_results": [],
                    "sut_bug_report": ""
                }

            debug_report = parse_debug_report(raw_output, feature_name, total, passed_cnt)

            sut_bugs = [t for t in debug_report.get("test_results", []) if t.get("status") == "SUT_BUG"]
            test_bugs = [t for t in debug_report.get("test_results", []) if t.get("status") == "TEST_BUG"]
            passed_tests = [t for t in debug_report.get("test_results", []) if t.get("status") == "PASSED"]

            valid_total = len(passed_tests) + len(sut_bugs)
            valid_pass_rate = f"{len(passed_tests)}/{valid_total}" if valid_total > 0 else "0/0"

            log.info(
                f"[G] Report: total={total}  passed={len(passed_tests)}  "
                f"sut_bugs={len(sut_bugs)}  test_bugs(ignored)={len(test_bugs)}  "
                f"valid_pass_rate={valid_pass_rate}"
            )

            if sut_bugs:
                log.info("[G] SUT Bug Details:")
                for bug in sut_bugs:
                    log.info(f"[G]   - {bug.get('test_name', '?')}: {bug.get('reason', '?')}")

            if test_bugs:
                log.info("[G] Ignored Test Bugs:")
                for bug in test_bugs:
                    log.info(f"[G]   - {bug.get('test_name', '?')}: {bug.get('reason', '?')}")

            if debug_report.get("sut_bug_report"):
                log.info(f"[G] SUT Bug Summary:\n{debug_report['sut_bug_report']}")

            debug_report["overall_pass_rate"] = valid_pass_rate
            debug_report["ignored_test_bugs"] = test_bugs
            debug_report["test_results"] = passed_tests + sut_bugs

            return debug_report

        except Exception as e:
            log.error(f"[G] Debug step failed for {feature_name}: {e}", exc_info=True)
            return None

        finally:
            try:
                if target_original_path and target_original_path.exists():
                    target_original_path.unlink()
                    log.info(f"[G] Cleaned up restored test file: {target_original_path}")
            except Exception as e:
                log.warning(f"[G] Failed to clean up test file: {e}")

    # ------------------------------------------------------------------
    # MR 生命周期
    # ------------------------------------------------------------------
    def process_mr_lifecycle(self, feature, verbose=False):
        log.info(f"[MR] Starting MR lifecycle for {feature.feature_name}")

        mr_file_path = f"memory/working_memory/mr_{feature.feature_name}.json"

        # Phase 1 — 生成
        log.info("[MR] Phase 1: Generating initial Metamorphic Relations …")
        try:
            step_gen = PipelineStep(
                agent=self.mr_parser,
                template_text=self.mr_desc,
                expected_output=self.mr_parse_out,
                output_file=mr_file_path,
                verbose=verbose,
                stream=self.stream,
                debug=self.debug,
            )
            gen_output = step_gen.run(
                sut=feature.get_context_summary(),
                retrieved_examples_json=vector_db.search(feature.get_context_summary(), 3),
            )
            current_mr_content = collect_output(gen_output)
        except (LLMCallError, Exception) as e:
            log.error(f"[MR] Phase 1 failed for {feature.feature_name}: {e}")
            return ""

        if not current_mr_content or not current_mr_content.strip():
            log.warning(f"[MR] Empty MR content generated for {feature.feature_name}")
            return ""

        # Phase 2 — 评审-修复循环
        for i in range(self.max_review_iterations):
            log.info(f"[MR] Phase 2: Review round {i + 1}/{self.max_review_iterations}")

            review_file_path = f"memory/working_memory/mr_review_{feature.feature_name}_round_{i}.json"

            try:
                step_review = PipelineStep(
                    agent=self.mr_parser,
                    template_text=self.mr_review_desc,
                    expected_output=self.mr_review_out,
                    output_file=review_file_path,
                    verbose=verbose,
                    stream=self.stream,
                    debug=self.debug,
                )
                review_output = step_review.run(
                    sut=feature.get_context_summary(),
                    mr_content=current_mr_content,
                )
                review_feedback = collect_output(review_output)
            except (LLMCallError, Exception) as e:
                log.warning(f"[MR] Review round {i + 1} failed: {e}, skipping review")
                break

            if not review_feedback:
                log.warning(f"[MR] Empty review feedback at round {i + 1}, skipping")
                break

            if "Invalid" not in review_feedback and "Risky" not in review_feedback:
                log.info(f"[MR] PASS — Review passed at round {i + 1}")
                break

            if i == self.max_review_iterations - 1:
                log.warning("[MR] Max review iterations reached, stopping")
                break

            # Phase 3 — 修复
            log.info(f"[MR] Phase 3: Fixing MR based on feedback (round {i + 1})")
            try:
                step_fix = PipelineStep(
                    agent=self.mr_parser,
                    template_text=self.mr_fix_desc,
                    expected_output=self.mr_parse_out,
                    output_file=mr_file_path,
                    verbose=verbose,
                    stream=self.stream,
                    debug=self.debug,
                )
                fix_output = step_fix.run(
                    sut=feature.get_context_summary(),
                    previous_mr=current_mr_content,
                    feedback=review_feedback,
                )
                current_mr_content = collect_output(fix_output)
            except (LLMCallError, Exception) as e:
                log.warning(f"[MR] Phase 3 fix failed at round {i + 1}: {e}, using previous MR content")
                break

        return current_mr_content


def _safe_summarize_experience(feature_name: str):
    """安全地调用 summarize_experience，失败时仅记录日志。"""
    try:
        summarize_experience(feature_name)
    except Exception as e:
        log.warning(f"[EXP] Failed to summarize experience for {feature_name}: {e}")


def archive_working_memory():
    src_dir = "memory/working_memory"
    if not os.path.exists(src_dir):
        return
    if not os.path.exists('memory/working_memory/test_plan.json'):
        return
    try:
        memory = Memory('memory/working_memory/test_plan.json')
        project_name = memory.project_name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model = os.environ.get("MODEL", "")
        dst_dir = os.path.join("memory/Long-Term", f"{timestamp}_{project_name}_{model}")
        os.makedirs(dst_dir, exist_ok=True)

        for name in os.listdir(src_dir):
            src_path = os.path.join(src_dir, name)
            dst_path = os.path.join(dst_dir, name)
            shutil.move(src_path, dst_path)
    except (json.JSONDecodeError, Exception) as e:
        log.warning(f"[Archive] Failed to archive working memory: {e}")
