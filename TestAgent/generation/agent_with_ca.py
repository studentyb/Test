import json
import logging
import os
import shutil
from typing import Tuple, Optional, Dict
from pathlib import Path

from agents.agents import (
    create_test_designer,
    create_test_development_engineer,
    create_test_debugger, create_mr_parser, create_test_reviewer,
)
from experience.core import summarize_experience, search_exp
from piplines.core import PipelineStep
from rag.db_instance import vector_db
from tools.grep import get_code_context
from utils.file_utils import (
    read_file, write_marked_block,
    restore_all, move_to_quarantine, save_code_to_file, write_file,
    collect_output, archive_working_memory, normalize_display_newlines,
)
from utils.java_test_runner import JavaTestRunnerTool
from utils.json_utils import set_metadata_value, get_metadata_value
import sys

# 导入 line_tracer 模块
line_tracer_module_path = Path(__file__).parent.parent / "line_tracer" / "line_tracer.py"
line_tracer_module = None
if line_tracer_module_path.exists():
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("line_tracer", str(line_tracer_module_path))
        if spec and spec.loader:
            line_tracer_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(line_tracer_module)
    except Exception as e:
        import logging
        logging.getLogger("mate").warning(f"[G] Failed to load line_tracer module: {e}")
        line_tracer_module = None
from utils.pytest_test_runner import PytestTestRunner
from utils.parser import parse_file_and_code, parse_debug_report
from utils.tree_utils import get_directory_tree

log = logging.getLogger("mate")


class Test4CA:

    def __init__(
            self,
            *,
            build: str,
            sut_root: str,
            put: str,
            language: str,
            verbose: bool = False,
            debug: bool = True,
            stream: bool = True,
            feature: str,
            exp: bool = True,
            max_retries: int = 3,
            dataset_root: str = None,
            new_project: bool = True,
            uml_class=None
    ):
        self.test_designer = create_test_designer()
        self.mr_parser = create_mr_parser()
        self.test_reviewer = create_test_reviewer()
        self.test_developer = create_test_development_engineer()
        self.test_debugger = create_test_debugger()
        self.cot2_desc = read_file('prompt/test_design/test_design.md')
        self.cot2_out = read_file('prompt/test_design/test_design_out.md')
        self.mr_desc = read_file(Path('prompt') / 'mr_parse' / 'mr_parse_input.md')
        self.mr_parse_out = read_file(Path('prompt') / 'mr_parse' / 'mr_parse_output.md')
        self.mr_review_desc = read_file(Path('prompt') / 'mr_parse' / 'mr_review.md')
        self.mr_review_out = read_file(Path('prompt') / 'mr_parse' / 'mr_review_out.md')
        self.mr_fix_desc = read_file(Path('prompt') / 'mr_parse' / 'mr_fix.md')
        self.cot4_desc = read_file('prompt/test_development/test_develop.md')
        self.cot4_fix = read_file('prompt/test_development/self_fix.md')
        self.cot4_out = read_file('prompt/test_development/test_develop_out.md')
        self.cot5_desc = read_file('prompt/test_debugger/test_debug.md')

        self.build = build.strip().lower()
        self.sut_root = Path(sut_root).resolve()
        self.dataset_root = Path(dataset_root).resolve() if dataset_root else self.sut_root
        self.put = put
        self.language = language.strip().lower()
        self.verbose = verbose
        self.debug = debug
        self.stream = stream
        self.feature = feature
        self.experience = exp
        self.max_retries = max_retries
        self.uml_class = uml_class

        if self.language == "java":
            self.test_root = self.dataset_root / "src" / "test" / "java"
        else:
            self.test_root = self.dataset_root / "tests"

        self.ps = get_directory_tree(str(self.sut_root))
        self.debug_report: Optional[Dict] = None

        self.metadata_path = Path("memory") / "working_memory" / "metadata.json"
        self.new_project = self._is_new_project()
        self.max_review_iterations = 2  # 最大评审迭代次数
        self.report=2
    # ------------------------------------------------------------------
    # 对外入口 — 返回签名不变
    # ------------------------------------------------------------------
    def run(self) -> dict | None:

        if self.new_project:
            archive_working_memory()

            # 无论是不是新项目，都确保 metadata 记录的是本次项目
        self._write_project_metadata()
        # todo
        first = f"ts_ca_{self.feature}.json" not in os.listdir(
            "memory/working_memory")
        if first:
            # mr生成
            # self.process_mr_lifecycle(self.feature, put=self.put)
            # D — 测试设计
            log.info("=" * 20 + " Test Design " + "=" * 20)
            step2 = PipelineStep(
                agent=self.test_designer,
                template_text=self.cot2_desc,
                expected_output=self.cot2_out,
                output_file=f"memory/working_memory/ts_ca_{self.feature}.json",
                verbose=self.verbose,
                stream=self.stream,
                debug=self.debug,
                stage="design",
            )
            print("===============put=============\n")
            print(self.put)
            mr_path = Path('memory') / 'working_memory' / f'mr_{self.feature}.json'
            step2_out = step2.run(sut=self.put, uml_class=self.uml_class, mr=read_file(mr_path) if mr_path.exists() else "")
            collect_output(step2_out, result_attr="raw")
        # C — 代码上下文提取
        log.info("=" * 20 + " Code Context Extraction " + "=" * 20)
        context = get_code_context(
            str(self.sut_root),
            read_file(f"memory/working_memory/ts_ca_{self.feature}.json"),
            self.language,
            self.uml_class
        )
        write_file(Path(f'memory/working_memory/code_context_{self.feature}.md'), context)
        if first:
            # X — 测试开发 pipeline
            log.info("=" * 20 + " Test Development " + "=" * 20)
            final_code, last_report, success = self.run_pipeline(
                feature=self.feature,
                verbose=self.verbose,
            )

        # G — Debug 分析
        log.info("=" * 20 + " Test Debug & Report " + "=" * 20)
        # debug前恢复测试
        log_file = Path("memory/working_memory/recovery_map.json")
        # todo
        if not log_file.exists():
            log.warning(f"[G] No quarantine log found, skipping debug for {self.feature}")
            return None

        with open(log_file, 'r', encoding='utf-8') as f:
            try:
                recovery_map = json.load(f)
            except json.JSONDecodeError:
                log.warning(f"[G] Invalid quarantine log format: {log_file}")
                return None

        feature_name = self.feature
        target_q_path = None
        target_original_path = None
        matched_key = None

        # 按 feature_name 查找要恢复的测试文件
        for q_path, ori_path in recovery_map.items():
            if Path(q_path).name.startswith(f"{feature_name}_"):
                target_q_path = Path(q_path)
                target_original_path = Path(ori_path)
                matched_key = q_path
                break

        if not target_q_path or not target_q_path.exists():
            log.warning(f"[G] No quarantined test file found for {feature_name}, skipping")
            return None

        # 恢复测试文件
        target_original_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target_q_path), str(target_original_path))
        log.info(f"[G] Restored test file: {target_original_path}")

        # 删除 recovery_map 中已恢复的映射记录
        if matched_key is not None:
            recovery_map.pop(matched_key, None)
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(recovery_map, f, indent=4, ensure_ascii=False)
            log.info(f"[G] Removed restored mapping from recovery log: {matched_key}")

        try:
            # 执行 debug
            self.debug_report = self._run_debug_step(
                feature=self.feature,
                test_code=read_file(target_original_path),
                test_file_path=target_original_path,
                verbose=self.verbose
            )
        finally:
            # debug后再次隔离测试
            if target_original_path and target_original_path.exists():
                quarantined_path = move_to_quarantine(
                    file_path=str(target_original_path),
                    feature_name=self.feature
                )
                if quarantined_path:
                    log.info(f"[G] Re-quarantined test file after debug: {quarantined_path}")
                else:
                    log.warning(f"[G] Failed to re-quarantine test file after debug: {target_original_path}")
            else:
                log.warning(f"[G] Restored test file missing after debug, cannot quarantine: {target_original_path}")

        if self.debug_report:
            report_path = f"memory/working_memory/debug_report_{self.feature}.json"
            write_file(Path(report_path), json.dumps(self.debug_report, indent=2, ensure_ascii=False))
            log.info(f"[G] Report saved → {report_path}")
        return self.debug_report

    # ------------------------------------------------------------------
    # 测试开发 pipeline
    # ------------------------------------------------------------------
    def run_pipeline(self, feature: str, verbose: bool = True) -> Tuple[str, str, bool]:
        feature_name = feature if isinstance(feature, str) else getattr(feature, "feature_name", str(feature))
        language = self.language or "python"
        log.info(f"[X] Starting test generation for feature: {feature_name}")

        initial_code = self._generate_initial_test(feature_name, verbose, language)
        log.info("[X] Initial code generation done")

        path_relative, _ = parse_file_and_code(initial_code)
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

        final_code, success, final_test_file_path, last_report = self._execute_repair_loop(
            initial_code=initial_code,
            default_test_file_path=default_test_file_path,
            feature_name=feature_name,
            max_retries=self.max_retries,
            verbose=verbose,
            language=language,
        )

        if success:
            log.info(f"[X] PASS — Test generation completed for {feature_name}")
        else:
            log.warning(f"[X] FAIL — Test generation failed after retries for {feature_name}")
        if final_test_file_path:
            move_to_quarantine(final_test_file_path, feature_name)
        return final_code, last_report, success

    # ------------------------------------------------------------------
    # 初始测试代码生成
    # ------------------------------------------------------------------
    def _generate_initial_test(self, feature: str, verbose: bool, language: str) -> str:
        log.info("[X] Generating initial test code …")
        test_cases_json = read_file(f'memory/working_memory/ts_ca_{feature}.json')

        step4 = PipelineStep(
            agent=self.test_developer,
            template_text=self.cot4_desc,
            expected_output=self.cot4_out,
            output_file='',
            verbose=verbose,
            stream=self.stream,
            debug=self.debug,
            stage="develop",
        )

        output = step4.run(
            test_cases=test_cases_json,
            test_file_path=str(self.test_root),
            sut_root=str(self.sut_root),
            file_tree=self.ps,
            language=language,
            exist_test_file=read_file('memory/working_memory/exist_test_file.txt') if os.path.exists(
                'memory/working_memory/exist_test_file.txt') else '',
            code_context=read_file(f'memory/working_memory/code_context_{feature}.md'),
            uml_class=self.uml_class
        )

        return collect_output(output)

    # ------------------------------------------------------------------
    # 迭代修复循环
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

        def _run_tests(code_to_run: str) -> Tuple[bool, str, list, str, str]:
            path_relative, parsed_code = parse_file_and_code(code_to_run)
            resolved = self._resolve_test_file_path(path_relative) if path_relative else None
            test_path = str(resolved) if resolved else default_test_file_path
            save_code_to_file(parsed_code, test_path)

            if language == "python":
                runner = PytestTestRunner(
                    dataset_root=self.dataset_root,
                    conda_env=os.environ.get("CONDA_ENV", "mate"),
                )
                result = runner.run_pytest(test_path)
            else:
                test_class = Path(test_path).stem
                set_metadata_value('target_class', test_class)
                runner = JavaTestRunnerTool(
                    sut_root=self.sut_root,
                    dataset_root=self.dataset_root,
                    build_tool=self.build,
                )
                result = runner.run_java_tests(test_class)

            return result.success, result.error_msg, result.test_cases, test_path, parsed_code

        current_code = initial_code
        log.info("[X] Running initial tests …")
        passed, report, test_cases, current_test_file_path, code = _run_tests(current_code)
        last_report = report

        log.info(f"[X] Result: passed={passed}")
        if self.debug:
            log.debug(f"[X] Error log: {report}")

        if passed:
            log.info("[X] PASS — Initial run succeeded")
            return current_code, True, current_test_file_path, last_report

        # 收集失败用例（按 error_type 去重）
        current_failed_tests = []
        seen_error_types = set()
        for tc in test_cases:
            if tc.status in ["FAILED", "ERROR"]:
                err_type = getattr(tc, 'error_type', None) or "UnknownErrorType"
                if err_type not in seen_error_types:
                    seen_error_types.add(err_type)
                    current_failed_tests.append(tc)

        write_marked_block(feature_name, 'TEST_CASE', code)
        write_marked_block(feature_name, 'STATUS', 'FAIL')
        if current_failed_tests:
            write_marked_block(feature_name, 'ERROR_TYPE', current_failed_tests[0].error_type)
            write_marked_block(feature_name, 'ERROR_LOG', current_failed_tests[0].message)
        else:
            write_marked_block(feature_name, 'ERROR_TYPE', 'BuildError')
            write_marked_block(feature_name, 'ERROR_LOG', report)

        # 经验检索
        aggregated_experiences = []
        if self.experience:
            log.info("[X] Searching historical experience …")
            if current_failed_tests:
                for tc in current_failed_tests:
                    exp = search_exp(tc.error_type, tc.message, tc.test_name, 2, True)
                    if exp:
                        aggregated_experiences.append(f"### Experience for error [{tc.error_type}]: \n{exp}")
            else:
                log.warning("[X] No structured test cases — using build error log for experience search")
                exp = search_exp("BuildError", report[:2000], feature_name, 2, True)
                if exp:
                    aggregated_experiences.append(f"### Experience for build error: \n{exp}")

        # 经验修复
        if self.experience and aggregated_experiences:
            log.info("[X] Experience hit — attempting experience-based repair")
            final_experience_prompt = "\n\n".join(aggregated_experiences)
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
        else:
            log.info("[X] No experience hit — proceeding to multi-round repair")

        # 多轮修复
        log.info("[X] Starting multi-round repair …")
        for attempt in range(max_retries):
            log.info(f"[X] Repair attempt {attempt + 1}/{max_retries}")
            current_code = self._repair_code(code, report, feature_name, verbose, experience=None)

            passed, report, test_cases, current_test_file_path, code = _run_tests(current_code)
            log.info(f"[X] Result: passed={passed}")
            if self.debug:
                log.debug(f"[X] Error log: {report}")

            last_report = report
            write_marked_block(feature_name, 'TEST_CASE', code)
            write_marked_block(feature_name, 'STATUS', 'PASS' if passed else 'FAIL')
            if passed:
                log.info("[X] PASS — Tests passed after multi-round repair")
                summarize_experience(feature_name)
                return current_code, True, current_test_file_path, last_report
            write_marked_block(feature_name, 'ERROR_LOG', report)

        return current_code, False, current_test_file_path, last_report

    # ------------------------------------------------------------------
    # Debug 步骤辅助函数
    # ------------------------------------------------------------------
    def _parse_method_from_test_spec(self, feature: str) -> Optional[str]:
        """
        从 ts_ca_{feature}.json 中的 focal_method 字段解析被测方法名

        文件可能包含 md 代码块语法，需要先去除

        Args:
            feature: feature 名称

        Returns:
            方法名
        """
        import re

        ts_ca_path = Path(f'memory/working_memory/ts_ca_{feature}.json')
        if not ts_ca_path.exists():
            return None

        try:
            content = read_file(ts_ca_path)

            # 检查并去除 markdown 代码块包裹
            if content.strip().startswith('```'):
                # 匹配 ```json 到 ``` 之间的内容
                match = re.search(r'```(?:json)?\s*(.*?)```', content, re.DOTALL)
                if match:
                    content = match.group(1)

            # 解析 JSON 并提取 focal_method
            import json
            data = json.loads(content)
            if isinstance(data, list) and len(data) > 0:
                focal_method = data[0].get('focal_method', '')
                if focal_method:
                    # 从 "ReturnType methodName(params)" 格式中提取方法名
                    method_match = re.search(r'[\w<>\[\]]+\s+(\w+)\s*\(', focal_method)
                    if method_match:
                        return method_match.group(1)

        except (json.JSONDecodeError, KeyError, IndexError, Exception) as e:
            log.warning(f"[G] Failed to parse method from ts_ca: {e}")

        return None

    def _parse_method_from_code_context(self, code_context: str) -> Tuple[Optional[str], Optional[str]]:
        """
        从 code_context 中解析被测类名和方法名

        code_context 由 grep.py 生成，包含格式化的标注：
        // File: xxx.java
        // AST Type: method_declaration
        // Class: user_authentication.service.impl.AuthenticationServiceImpl
        // Method: findUserIdentityByUsername

        优先级：
        1. 包含 @Override 的实现类
        2. 包含 "impl" 包名的类
        3. 第一个匹配的类

        Returns:
            (class_name, method_name): 类名（含包名）和方法名
        """
        import re

        # 找所有 // Class: 和 // Method: 的配对
        # 每个代码块的格式：
        # // File: xxx
        # // AST Type: xxx
        # // Class: xxx
        # // Method: xxx
        # 代码内容...

        blocks = code_context.split('// File:')
        all_classes = []
        all_methods = []

        for block in blocks[1:]:  # 跳过第一个空块
            lines = block.split('\n')

            class_name = None
            method_name = None
            has_override = False

            for line in lines:
                # 检查是否有 @Override（通常在代码内容中）
                if '@Override' in line:
                    has_override = True

                # 提取类名
                class_match = re.search(r'// Class:\s*([\w.]+)', line)
                if class_match:
                    class_name = class_match.group(1)

                # 提取方法名
                method_match = re.search(r'// Method:\s*(\w+)', line)
                if method_match:
                    method_name = method_match.group(1)

            if class_name and method_name:
                # 判断优先级
                priority = 0
                if has_override:
                    priority = 3  # 最高优先级：实现类
                elif 'impl' in class_name.lower():
                    priority = 2  # 次优先级：包含 impl 的类
                else:
                    priority = 1  # 最低优先级

                all_classes.append((priority, class_name))
                all_methods.append((priority, method_name))

        # 按优先级排序，选择最高优先级的
        if all_classes:
            all_classes.sort(key=lambda x: x[0], reverse=True)
            all_methods.sort(key=lambda x: x[0], reverse=True)

            # 选择最高优先级的类名和方法名（可能来自不同块，取各自最高）
            best_class = all_classes[0][1]
            best_method = all_methods[0][1]

            return best_class, best_method

        return None, None

    def _parse_method_from_put(self, put: str) -> Optional[str]:
        """
        从 put（原始需求文本）中解析被测方法名

        put 格式示例：
        {
            "signature": "UserIdentity findUserIdentityByUsername(String username)",
            "semantic": "Finds user identity by username",
            ...
        }

        Returns:
            方法名
        """
        import re

        # 尝试从 signature 字段中解析方法名
        # 格式: "ReturnType methodName(param1, param2)"
        signature_pattern = r'"signature"\s*:\s*"[\w<>\[\]]+\s+(\w+)\s*\('
        match = re.search(signature_pattern, put)
        if match:
            return match.group(1)

        return None

    def _parse_function_from_test_spec(self, feature: str) -> Tuple[Optional[str], Optional[str]]:
        """
        从 ts_ca_{feature}.json 中解析被测函数名（Python 版本）

        Args:
            feature: feature 名称

        Returns:
            (module_path, function_name): 模块路径（如 "src.utils"）和函数名
        """
        import re

        ts_ca_path = Path(f'memory/working_memory/ts_ca_{feature}.json')
        if not ts_ca_path.exists():
            return None, None

        try:
            content = read_file(ts_ca_path)

            # 去除 markdown 代码块包裹
            if content.strip().startswith('```'):
                match = re.search(r'```(?:json)?\s*(.*?)```', content, re.DOTALL)
                if match:
                    content = match.group(1)

            # 解析 JSON 并提取 focal_method
            import json
            data = json.loads(content)
            if isinstance(data, list) and len(data) > 0:
                focal_method = data[0].get('focal_method', '')
                if focal_method:
                    # Python 格式可能是:
                    # 1. "module.ClassName.method_name"
                    # 2. "module.function_name"
                    # 3. "function_name(args) -> return_type"
                    # 4. "function_name"

                    # 检查是否包含函数签名 (如 "add(a, b) -> int" 或 "read_time()")
                    if '(' in focal_method:
                        # 提取函数签名前的部分
                        signature_part = focal_method.split('(')[0].strip()
                        # 如果包含模块路径，提取最后一部分作为函数名，前面的作为模块路径
                        if '.' in signature_part:
                            parts = signature_part.rsplit('.', 1)
                            module_path = parts[0]
                            function_name = parts[1]
                            return module_path, function_name
                        else:
                            # 没有模块路径，只返回函数名
                            return None, signature_part
                    else:
                        # 没有括号，可能是 "module.function_name" 或 "function_name"
                        parts = focal_method.split('.')
                        if len(parts) > 1:
                            # 至少有一个点，最后一个是函数名，前面的是模块路径
                            module_path = '.'.join(parts[:-1])
                            function_name = parts[-1]
                            return module_path, function_name
                        else:
                            # 没有模块路径，只返回函数名
                            return None, focal_method

        except (json.JSONDecodeError, KeyError, IndexError, Exception) as e:
            log.warning(f"[G] Failed to parse function from ts_ca: {e}")

        return None, None

    def _parse_function_from_code_context(self, code_context: str) -> Tuple[Optional[str], Optional[str]]:
        """
        从 code_context 中解析被测模块名和函数名（Python 版本）

        code_context 格式（由 grep.py 的 search_definition_ast 生成）：
        # File: xxx.py
        # AST Type: function_definition
        # Class: module.path
        # Method: function_name

        Returns:
            (module_name, function_name): 模块名和函数名
        """
        import re

        blocks = code_context.split('# File:')
        all_modules = []
        all_functions = []

        for block in blocks[1:]:  # 跳过第一个空块
            lines = block.split('\n')

            module_name = None
            function_name = None

            for line in lines:
                # 提取文件名作为模块名
                file_match = re.search(r'# File:\s*(.+?\.py)', line)
                if file_match:
                    file_path = file_match.group(1)
                    # 从文件路径提取模块名（去掉 .py 后缀）
                    module_name = file_path.replace('/', '.').replace('\\', '.')
                    if module_name.endswith('.py'):
                        module_name = module_name[:-3]

                # 提取函数名（grep.py 使用 # Method: 而不是 # Function:）
                func_match = re.search(r'# Method:\s*(\w+)', line)
                if func_match:
                    function_name = func_match.group(1)

            if module_name and function_name:
                log.info(f"[G] Parsed from code_context: module={module_name}, function={function_name}")
                all_modules.append(module_name)
                all_functions.append(function_name)

        if all_modules and all_functions:
            return all_modules[0], all_functions[0]

        return None, None

    # ------------------------------------------------------------------
    # Debug 步骤`
    # ------------------------------------------------------------------
    def _run_debug_step(self, feature: str, test_code: str, test_file_path: str=None, verbose: bool = True) -> Optional[Dict]:
        feature_name = feature if isinstance(feature, str) else getattr(feature, "feature_name", str(feature))
        language = self.language or "python"
        target_class = get_metadata_value('target_class')

        # 预先解析被测类和方法名（用于行追踪）
        sut_class_name = None
        sut_method_name = None
        if language == "java":
            # 优先级1: 从 ts_ca_{feature}.json 的 focal_method 解析
            sut_method_name = self._parse_method_from_test_spec(feature_name)

            # 如果没解析到，从 code_context 解析类名和方法名
            if not sut_method_name:
                code_context = read_file(f'memory/working_memory/code_context_{feature_name}.md')
                sut_class_name, sut_method_name = self._parse_method_from_code_context(code_context)
            else:
                # 只有方法名，需要从 code_context 获取类名
                code_context = read_file(f'memory/working_memory/code_context_{feature_name}.md')
                sut_class_name, _ = self._parse_method_from_code_context(code_context)

            # 如果还没解析到方法名，尝试从 put 解析
            if not sut_method_name:
                sut_method_name = self._parse_method_from_put(self.put)

            log.info(f"[G] Parsed SUT class: {sut_class_name}, method: {sut_method_name}")
        elif language == "python":
            # Python 解析逻辑
            sut_module_name = None
            sut_function_name = None

            # 从 ts_ca 解析模块名和函数名（返回元组）
            parsed_module, parsed_function = self._parse_function_from_test_spec(feature_name)
            sut_module_name = parsed_module
            sut_function_name = parsed_function

            from pathlib import Path
            # 如果从 ts_ca 没有解析到函数名，从 code_context 解析
            if not sut_function_name:
                code_context_path = Path(f'memory/working_memory/code_context_{feature_name}.md')
                if code_context_path.exists():
                    code_context = read_file(code_context_path)
                    sut_module_name, sut_function_name = self._parse_function_from_code_context(code_context)
            elif not sut_module_name:
                # 已有函数名，但没有模块名，尝试从 code_context 获取模块名
                code_context_path = Path(f'memory/working_memory/code_context_{feature_name}.md')
                if code_context_path.exists():
                    code_context = read_file(code_context_path)
                    sut_module_name, _ = self._parse_function_from_code_context(code_context)

            # 将解析结果存入相同变量用于后续处理（行追踪需要这些变量名）
            sut_class_name = sut_module_name  # 复用变量，存储模块路径（如 "src.utils"）
            sut_method_name = sut_function_name  # 复用变量，存储函数名

            log.info(f"[G] Parsed SUT module: {sut_module_name}, function: {sut_function_name}")

        try:
            log.info(f"[G] Running tests for {feature_name} …")
            if language == "python":
                runner = PytestTestRunner(
                    dataset_root=self.dataset_root,
                    conda_env=os.environ.get("CONDA_ENV", "mate"),
                )
                # test_code 参数是测试文件的绝对路径，直接使用
                result = runner.run_pytest(test_file_path)
            else:
                test_class = target_class
                runner = JavaTestRunnerTool(
                    sut_root=self.sut_root,
                    dataset_root=self.dataset_root,
                    build_tool=self.build,
                )
                result = runner.run_java_tests(test_class)

            total = len(result.test_cases)
            passed_cnt = sum(1 for tc in result.test_cases if tc.status == "PASSED")
            log.info(f"[G] Execution result: {passed_cnt}/{total} passed")

            all_passed = (
                    result.success
                    and len(result.test_cases) > 0
                    and all(tc.status == "PASSED" for tc in result.test_cases)
            )

            if all_passed:
                log.info(f"[G] All tests passed for {feature_name}")
                return {
                    "feature": feature_name,
                    "overall_pass_rate": f"{passed_cnt}/{total}",
                    "summary": "All tests passed. No SUT bugs detected.",
                    "test_results": [
                        {"test_name": tc.test_name, "status": "PASSED", "reason": ""}
                        for tc in result.test_cases
                    ],
                    "sut_bug_report": "",
                }
            if self.report == 1:
                failed_cases = [
                    tc for tc in result.test_cases
                    if tc.status in {"FAILED", "ERROR"}
                ]

                return {
                    "feature": feature_name,
                    "overall_pass_rate": f"{passed_cnt}/{total}",
                    "summary": "Some tests failed. Potential SUT bugs detected.",
                    "test_results": [
                        {
                            "test_name": tc.test_name,
                            "status": "SUT_BUG",
                            "reason": (
                                f"{tc.error_type}: {tc.message}"
                                if tc.error_type and tc.message
                                else tc.message or tc.error_type or ""
                            )
                        }
                        for tc in failed_cases
                    ],
                    "sut_bug_report": {
                        "bugs":
                            {
                                "message":result.error_msg,
                                "test cases":test_code
                            }

                    }
                }




            # 新增：行追踪逻辑
            line_tracer_info = ""

            # 获取 line-tracer.jar 的绝对路径（相对于当前项目目录）
            from pathlib import Path
            current_dir = Path(__file__).parent.parent  # agent_with_ca.py 的父目录的父目录 = TestAgent 项目根目录
            jar_path = str(current_dir / "debug" / "line-tracer.jar")
            log.info(f"[G] Line tracer jar path: {jar_path}")

            # 检查是否有 assertion error（模糊匹配，支持 org.opentest4j.AssertionFailedError 等全限定类名）
            def _is_assertion_error(tc) -> bool:
                if tc.status not in ["FAILED", "ERROR"]:
                    return False
                # 模糊匹配 error_type 中是否包含 Assertion
                if tc.error_type and ("Assertion" in tc.error_type.lower() or "assertion" in tc.error_type.lower()):
                    return True
                # 检查 message 中是否包含 Assertion
                if tc.message and ("AssertionError" in tc.message or "AssertionFailedError" in tc.message):
                    return True
                return False

            has_assertion_error = any(_is_assertion_error(tc) for tc in result.test_cases)

            if has_assertion_error and language == "java" and sut_class_name and sut_method_name:
                try:
                    from debug.java_debugger import run_java_line_tracer

                    # 获取第一个失败的 assertion error 测试用例
                    failed_tc = next(
                        (tc for tc in result.test_cases
                         if _is_assertion_error(tc)),
                        None
                    )

                    if failed_tc:
                        # test_method: 完整的测试方法名，如 "com.example.TestClass#testMethod"
                        test_method = f"{failed_tc.class_name}#{failed_tc.test_name}"

                        # 打印参数用于调试对比
                        print(f"[G] Line tracer params:")
                        print(f"[G]   project_path: {str(self.sut_root)}")
                        print(f"[G]   class_name: {sut_class_name}")
                        print(f"[G]   method_name: {sut_method_name}")
                        print(f"[G]   test_method: {test_method}")
                        print(f"[G]   jar_path: {jar_path}")

                        returncode, stdout, stderr = run_java_line_tracer(
                            project_path=str(self.dataset_root),
                            class_name=sut_class_name,
                            method_name=sut_method_name,
                            test_method=test_method,
                            jar_path=jar_path,  # 使用绝对路径
                            timeout=30  # 设置超时时间为 120 秒，等待 Maven 编译和 JVM 启动
                        )

                        if returncode == 0:
                            line_tracer_info = stdout
                            print(f"[G] Java Line trace info:\n{line_tracer_info}")
                            log.info(f"[G] Java Line tracer output retrieved: {len(stdout)} chars")
                        else:
                            log.warning(f"[G] Java Line tracer failed (returncode={returncode}): {stderr}")

                except ImportError as e:
                    log.warning(f"[G] Failed to import java_debugger: {e}")
                except Exception as e:
                    log.warning(f"[G] Java Line tracer error: {type(e).__name__}: {e}")
                    import traceback
                    log.warning(f"[G] Traceback: {traceback.format_exc()}")

            # Python 行追踪逻辑
            elif has_assertion_error and language == "python" and sut_class_name and sut_method_name:
                try:
                    if line_tracer_module is None:
                        log.warning("[G] line_tracer module not available")
                    else:
                        # 获取第一个失败的 assertion error 测试用例
                        failed_tc = next(
                            (tc for tc in result.test_cases
                             if _is_assertion_error(tc)),
                            None
                        )

                        if failed_tc:
                            # 构造 pytest_test_path，格式为 "tests/test_xxx.py::test_xxx"
                            # 从 test_code（测试文件路径）中提取相对路径
                            test_file = Path(test_code)
                            if test_file.exists():
                                # 获取相对于 dataset_root 的路径
                                try:
                                    test_relative = test_file.relative_to(self.dataset_root)
                                    pytest_test_path = str(test_relative).replace('\\', '/')
                                    pytest_test_path = f"{pytest_test_path}::{failed_tc.test_name}"

                                    # 构造 target_func_path，格式为 "module.submodule:function_name"
                                    # sut_class_name 是模块名（如 "src.utils"），sut_method_name 是函数名（如 "read_time"）
                                    target_func_path = f"{sut_class_name}:{sut_method_name}"

                                    # 打印参数用于调试
                                    print(f"[G] Python Line tracer params:")
                                    print(f"[G]   project_root: {str(self.dataset_root)}")
                                    print(f"[G]   target_func_path: {target_func_path}")
                                    print(f"[G]   pytest_test_path: {pytest_test_path}")

                                    # 调用 run_single_test_with_trace
                                    exit_code, trace_records = line_tracer_module.run_single_test_with_trace(
                                        project_root=str(self.dataset_root),
                                        target_func_path=target_func_path,
                                        pytest_test_path=pytest_test_path,
                                    )

                                    if exit_code == 0:
                                        line_tracer_info = json.dumps(trace_records, ensure_ascii=False, indent=2, default=str)
                                        print(f"[G] Python Line trace info:\n{line_tracer_info}")
                                        log.info(f"[G] Python Line tracer output retrieved: {len(trace_records)} records")
                                    else:
                                        log.warning(f"[G] Python Line tracer failed (exitcode={exit_code})")
                                        line_tracer_info = ""
                                except (ValueError, TypeError) as e:
                                    log.warning(f"[G] Failed to resolve test file path: {e}")
                                except Exception as e:
                                    log.warning(f"[G] Python Line tracer error: {type(e).__name__}: {e}")
                                    import traceback
                                    log.warning(f"[G] Traceback: {traceback.format_exc()}")
                            else:
                                log.warning(f"[G] Test file not found: {test_code}")

                except ImportError as e:
                    log.warning(f"[G] Failed to import line_tracer dependencies: {e}")
                except Exception as e:
                    log.warning(f"[G] Python Line tracer error: {type(e).__name__}: {e}")
                    import traceback
                    log.warning(f"[G] Traceback: {traceback.format_exc()}")

            # 有失败 → 调用 Debug Agent 分析
            log.info("[G] Invoking Debug Agent to analyze failures …")

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
                ps=self.ps,
                put=self.put,
                test_code=test_code,
                source_code=read_file(f'memory/working_memory/code_context_{feature}.md'),
                exec_report=result.error_msg,
                line_tracer_info=line_tracer_info
            )

            raw_output = collect_output(output)
            debug_report = parse_debug_report(raw_output, feature_name, total, passed_cnt)

            sut_bugs = [t for t in debug_report.get("test_results", []) if t["status"] == "SUT_BUG"]
            test_bugs = [t for t in debug_report.get("test_results", []) if t["status"] == "TEST_BUG"]
            passed_tests = [t for t in debug_report.get("test_results", []) if t["status"] == "PASSED"]

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
                    log.info(f"[G]   - {bug['test_name']}: {bug['reason']}")

            if test_bugs:
                log.info("[G] Ignored Test Bugs:")
                for bug in test_bugs:
                    log.info(f"[G]   - {bug['test_name']}: {bug['reason']}")

            if debug_report.get("sut_bug_report"):
                log.info(f"[G] SUT Bug Summary:\n{debug_report['sut_bug_report']}")

            debug_report["overall_pass_rate"] = valid_pass_rate
            debug_report["ignored_test_bugs"] = test_bugs
            debug_report["test_results"] = passed_tests + sut_bugs

            return debug_report
        except Exception:
            print(Exception)

    def process_mr_lifecycle(self, feature, put, verbose=False):
        """
        MR 生命周期管理：生成 -> (评审 -> 修复/删除) * N
        """
        print(f'\n=== Starting MR Lifecycle for {feature} ===\n')

        # 定义文件路径
        mr_file_path = str(Path('memory') / 'working_memory' / f'mr_{feature}.json')

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
        gen_stream = step_gen.run(
            sut=put,
            retrieved_examples_json=vector_db.search(put, 3)
        )

        current_mr_content = ""
        if hasattr(gen_stream, "__iter__") and not isinstance(gen_stream, str):
            for chunk in gen_stream:
                content = getattr(chunk, "content", str(chunk))
                print(normalize_display_newlines(content), end="", flush=True)
                current_mr_content += content
        else:
            content = getattr(gen_stream, "result", str(gen_stream))
            print(normalize_display_newlines(content), end="", flush=True)
            current_mr_content = content

        # 2. 评审-修复 循环 (Review-Fix Loop)
        for i in range(self.max_review_iterations):
            print(f'\n\n[MR Phase 2] Review Round {i + 1}/{self.max_review_iterations}...')

            review_file_path = str(
                Path('memory') / 'working_memory' / f'mr_review_{feature}_round_{i}.json')

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
                sut=put,
                mr_content=current_mr_content,
            )

            review_feedback = ""
            if hasattr(review_stream, "__iter__") and not isinstance(review_stream, str):
                for chunk in review_stream:
                    content = getattr(chunk, "content", str(chunk))
                    print(normalize_display_newlines(content), end="", flush=True)
                    review_feedback += content
            else:
                content = getattr(review_stream, "result", str(review_stream))
                print(normalize_display_newlines(content), end="", flush=True)
                review_feedback = content

            # 2.2 判断循环终止条件
            # 简单的判断逻辑：如果反馈中不包含 "Invalid" 或 "Risky"，且包含 "Valid"，则认为通过
            # 更严谨的做法是解析 review_feedback JSON
            if "Invalid" not in review_feedback and "Risky" not in review_feedback:
                print(f"\n[SUCCESS] MR Review Passed at round {i + 1}. No critical issues found.")
                break

            if i == self.max_review_iterations - 1:
                print(f"\n[WARNING] Max iterations reached. Stopping optimization.")
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
                sut=put,
                previous_mr=current_mr_content,
                feedback=review_feedback,
            )

            # 更新 current_mr_content 用于下一轮
            current_mr_content = ""
            if hasattr(fix_stream, "__iter__") and not isinstance(fix_stream, str):
                for chunk in fix_stream:
                    content = getattr(chunk, "content", str(chunk))
                    print(normalize_display_newlines(content), end="", flush=True)
                    current_mr_content += content
            else:
                content = getattr(fix_stream, "result", str(fix_stream))
                print(normalize_display_newlines(content), end="", flush=True)
                current_mr_content = content

        return current_mr_content

    def _is_new_project(self) -> bool:
        current_dataset_root = str(self.dataset_root)

        if not self.metadata_path.exists():
            return True

        try:
            with open(self.metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except (json.JSONDecodeError, OSError, TypeError):
            return True

        last_dataset_root = metadata.get("dataset_root")
        return last_dataset_root != current_dataset_root

    def _write_project_metadata(self) -> None:
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)

        # 读取现有数据（如果文件存在）
        data = {}
        if self.metadata_path.exists():
            try:
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError):
                # 文件损坏或无法读取，使用空字典重新开始
                data = {}

        # 更新或添加 dataset_root 字段
        data["dataset_root"] = str(self.dataset_root)

        # 写回文件
        with open(self.metadata_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

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
    def _repair_code(self, broken_code: str, error_log: str, feature_name: str, verbose: bool, experience) -> str:
        fix_step = PipelineStep(
            agent=self.test_developer,
            template_text=self.cot4_fix,
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
            code_context=read_file(f'memory/working_memory/code_context_{feature_name}.md'),
            experience=experience,
            uml_class=self.uml_class
        )

        return collect_output(output)
