import json
import logging
from pathlib import Path
from typing import Dict

from agents.agents import (
    create_test_designer,
    create_test_development_engineer,
    create_mr_parser,
)
from piplines.core import PipelineStep
from rag.db_instance import vector_db
from utils.file_utils import (
    write_file,
    collect_output,
    normalize_display_newlines,
)

log = logging.getLogger("mate")


class HumanEvalMinimal4CA:
    """
    HumanEval 最小可运行版
    - 不读取外部 prompt 模板
    - 不执行测试
    - 不包含 debug
    - 只生成测试用例代码
    """

    def __init__(
        self,
        sample: Dict,
        variant_key: str = "put0",
        verbose: bool = False,
        debug: bool = True,
        stream: bool = True,
        enable_mr: bool = True,
    ):
        self.sample = sample
        self.variant_key = variant_key

        self.task_id = sample["task_id"]
        self.feature = self.task_id.replace("/", "_")
        self.prompt = sample["prompt"]
        self.entry_point = sample["entry_point"]
        self.candidate_code = sample["variants"][variant_key]

        self.verbose = verbose
        self.debug = debug
        self.stream = stream
        self.enable_mr = enable_mr

        self.test_designer = create_test_designer()
        self.mr_parser = create_mr_parser()
        self.test_developer = create_test_development_engineer()

        self.max_review_iterations = 2
        self.working_memory = Path("memory") / "working_memory"
        self.working_memory.mkdir(parents=True, exist_ok=True)

        self.put = self._build_put()
        self.code_context = self._build_code_context()

        # =========================
        # 内联 Prompt 定义
        # =========================

        self.mr_desc = """
You are a metamorphic relation design assistant for HumanEval-style Python function problems.

Your task:
Given a Python function prompt and entry point, generate useful metamorphic relations (MRs)
for black-box test generation.

Requirements:
1. Focus on function-level semantics, not project-level architecture.
2. Prefer relations about:
   - permutation invariance
   - idempotence
   - monotonicity
   - boundary behavior
   - neutral element insertion
   - symmetry
   - scale / translation transformations
   - duplicate handling
3. Do not invent implementation details.
4. Do not reference source files, classes, repositories, or project structure.
5. Keep each MR concise and testable.
6. Output JSON only.

Output format:
{
  "entry_point": "...",
  "mrs": [
    {
      "id": "MR1",
      "description": "...",
      "input_transformation": "...",
      "expected_relation": "..."
    }
  ]
}
""".strip()

        self.mr_parse_out = """
Return valid JSON only.
""".strip()

        self.mr_review_desc = """
You are reviewing metamorphic relations for a HumanEval-style Python function task.

Please review the given MR set and identify:
- invalid relations
- risky or ambiguous relations
- redundant relations
- weak relations with low testing value

Rules:
1. Judge from the problem statement only.
2. Do not assume any hidden implementation behavior.
3. Prefer correctness over quantity.
4. Output JSON only.

Output format:
{
  "summary": "...",
  "issues": [
    {
      "mr_id": "MR1",
      "level": "Invalid | Risky | Weak | Redundant",
      "reason": "..."
    }
  ],
  "overall": "PASS | REVISE"
}
""".strip()

        self.mr_review_out = """
Return valid JSON only.
""".strip()

        self.mr_fix_desc = """
You are revising metamorphic relations for a HumanEval-style Python function task.

Input:
- function problem description
- previous MR set
- review feedback

Task:
Revise the MR set so that:
1. Invalid or risky MRs are removed or corrected.
2. The revised MRs remain concise and testable.
3. The result is suitable for downstream test design.
4. Output JSON only.

Output format:
{
  "entry_point": "...",
  "mrs": [
    {
      "id": "MR1",
      "description": "...",
      "input_transformation": "...",
      "expected_relation": "..."
    }
  ]
}
""".strip()

        self.cot2_desc = """
You are a test design assistant for HumanEval-style Python function tasks.

Task:
Given:
- the function prompt
- the entry point
- optional metamorphic relations

Generate a structured test specification.

Requirements:
1. Focus on black-box functional behavior.
2. Cover:
   - normal cases
   - boundary cases
   - corner cases
   - special values
   - metamorphic checks when appropriate
3. Do not assume implementation internals.
4. Do not invent project structure, classes, or external files.
5. The test specification must be executable in principle for a single Python function.
6. Output JSON only.

Output format:
{
  "task_id": "...",
  "entry_point": "...",
  "focal_method": "...",
  "observables": [
    "..."
  ],
  "test_cases": [
    {
      "id": "TC1",
      "scenario": "...",
      "category": "normal | boundary | corner | metamorphic",
      "inputs": {
        "...": "..."
      },
      "expected_behavior": "...",
      "oracle_type": "explicit | metamorphic"
    }
  ]
}
""".strip()

        self.cot2_out = """
Return valid JSON only.
""".strip()

        self.cot4_desc = """
You are a Python test development assistant for HumanEval-style function tasks.

Task:
Convert the structured test specification into executable Python test code.

Strict output constraints:
1. Output Python code only.
2. Do NOT output markdown code fences.
3. Do NOT output file paths.
4. Do NOT output pytest-style test files.
5. Do NOT output explanations.
6. Define exactly one function:

def check(candidate):
    ...

7. Use plain assert statements inside check(candidate).
8. candidate is the function under test.
9. Do not redefine candidate.
10. Do not modify the provided test intent.
11. Prefer concrete assertions when expected outputs are clear.
12. For metamorphic tests, encode the relation with asserts directly.
13. Keep imports minimal. Avoid unnecessary imports.
14. The generated code must be a standalone check(candidate) block.

Example form:
def check(candidate):
    assert candidate(...) == ...
    x1 = candidate(...)
    x2 = candidate(...)
    assert x1 == x2
""".strip()

        self.cot4_out = """
Return Python code only, with a single function check(candidate).
No markdown fences. No file path.
""".strip()

    # ------------------------------------------------------------------
    # 输入构造
    # ------------------------------------------------------------------
    def _build_put(self) -> str:
        payload = {
            "task_id": self.task_id,
            "entry_point": self.entry_point,
            "prompt": self.prompt,
            "requirement": self.prompt,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _build_code_context(self) -> str:
        context = f"""# Task ID
{self.task_id}

# Entry Point
{self.entry_point}

# Prompt
{self.prompt}

"""
        return context.strip()

    def _write_code_context(self) -> None:
        path = self.working_memory / f"code_context_{self.feature}.md"
        write_file(path, self.code_context)

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
    def run(self) -> Dict[str, str]:
        log.info("=" * 20 + f" HumanEval Minimal Pipeline: {self.feature} " + "=" * 20)

        self._write_code_context()

        mr_content = ""
        if self.enable_mr:
            mr_content = self.process_mr_lifecycle(self.feature, put=self.put, verbose=self.verbose)

        test_spec = self._run_test_design(mr_content=mr_content)
        generated_test_code = self._generate_initial_test(test_spec)

        return {
            "feature": self.feature,
            "variant": self.variant_key,
            "mr": mr_content,
            "test_spec": test_spec,
            "generated_test_code": generated_test_code,
        }

    # ------------------------------------------------------------------
    # 测试设计
    # ------------------------------------------------------------------
    def _run_test_design(self, mr_content: str = "") -> str:
        log.info("=" * 20 + " Test Design " + "=" * 20)

        step2 = PipelineStep(
            agent=self.test_designer,
            template_text=self.cot2_desc,
            expected_output=self.cot2_out,
            output_file=str(self.working_memory / f"ts_ca_{self.feature}.json"),
            verbose=self.verbose,
            stream=self.stream,
            debug=self.debug,
            stage="design",
        )

        output = step2.run(
            sut=self.put,
            uml_class=f"entry_point: {self.entry_point}",
            mr=mr_content,
        )

        test_spec = collect_output(output)
        write_file(self.working_memory / f"ts_ca_{self.feature}.json", test_spec)
        return test_spec

    # ------------------------------------------------------------------
    # 测试开发
    # ------------------------------------------------------------------
    def _generate_initial_test(self, test_spec: str) -> str:
        log.info("=" * 20 + " Test Development " + "=" * 20)

        step4 = PipelineStep(
            agent=self.test_developer,
            template_text=self.cot4_desc,
            expected_output=self.cot4_out,
            output_file="",
            verbose=self.verbose,
            stream=self.stream,
            debug=self.debug,
            stage="develop",
        )

        output = step4.run(
            test_cases=test_spec,
            test_file_path="",
            sut_root="",
            file_tree="",
            language="python",
            exist_test_file="",
            code_context=self.code_context,
            uml_class=f"entry_point: {self.entry_point}",
        )

        generated_test_code = collect_output(output)
        write_file(
            self.working_memory / f"generated_test_{self.feature}_{self.variant_key}.py",
            generated_test_code
        )
        return generated_test_code

    # ------------------------------------------------------------------
    # MR 生命周期
    # ------------------------------------------------------------------
    def process_mr_lifecycle(self, feature: str, put: str, verbose: bool = False) -> str:
        print(f"\n=== Starting MR Lifecycle for {feature} ===\n")

        mr_file_path = str(self.working_memory / f"mr_{feature}.json")

        print("[MR Phase 1] Generating Initial Metamorphic Relations...")
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

        gen_stream = step_gen.run(
            sut=put,
            retrieved_examples_json=vector_db.search(put, 3)
        )

        current_mr_content = self._collect_stream_text(gen_stream)

        for i in range(self.max_review_iterations):
            print(f"\n[MR Phase 2] Review Round {i + 1}/{self.max_review_iterations}...")

            review_file_path = str(self.working_memory / f"mr_review_{feature}_round_{i}.json")

            step_review = PipelineStep(
                agent=self.mr_parser,
                template_text=self.mr_review_desc,
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
            review_feedback = self._collect_stream_text(review_stream)

            if '"overall": "PASS"' in review_feedback or '"overall":"PASS"' in review_feedback:
                print(f"\n[SUCCESS] MR Review Passed at round {i + 1}.")
                break

            if i == self.max_review_iterations - 1:
                print("\n[WARNING] Max iterations reached. Stop MR optimization.")
                break

            print(f"\n[MR Phase 3] Fixing MR based on feedback (Round {i + 1})...")
            step_fix = PipelineStep(
                agent=self.mr_parser,
                template_text=self.mr_fix_desc,
                expected_output=self.mr_parse_out,
                output_file=mr_file_path,
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

            current_mr_content = self._collect_stream_text(fix_stream)

        write_file(self.working_memory / f"mr_{feature}.json", current_mr_content)
        return current_mr_content

    @staticmethod
    def _collect_stream_text(stream_obj) -> str:
        content_text = ""
        if hasattr(stream_obj, "__iter__") and not isinstance(stream_obj, str):
            for chunk in stream_obj:
                content = getattr(chunk, "content", str(chunk))
                print(normalize_display_newlines(content), end="", flush=True)
                content_text += content
        else:
            content = getattr(stream_obj, "result", str(stream_obj))
            print(normalize_display_newlines(content), end="", flush=True)
            content_text = content
        return content_text


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    sample = {
        "task_id": "HumanEval/0",
        "prompt": '''from typing import List

def has_close_elements(numbers: List[float], threshold: float) -> bool:
    """ Check if in given list of numbers, are any two numbers closer to each other than
    given threshold.
    >>> has_close_elements([1.0, 2.0, 3.0], 0.5)
    False
    >>> has_close_elements([1.0, 2.8, 3.0, 4.0, 5.0, 2.0], 0.3)
    True
    """
''',
        "entry_point": "has_close_elements",
        "variants": {
            "put0": '''from typing import List

def has_close_elements(numbers: List[float], threshold: float) -> bool:
    """ Check if in given list of numbers, are any two numbers closer to each other than
    given threshold.
    >>> has_close_elements([1.0, 2.0, 3.0], 0.5)
    False
    >>> has_close_elements([1.0, 2.8, 3.0, 4.0, 5.0, 2.0], 0.3)
    True
    """
    for i in range(len(numbers)):
        for j in range(i + 1, len(numbers)):
            if abs(numbers[i] - numbers[j]) <= threshold:
                return True
    return False
'''
        }
    }

    runner = HumanEvalMinimal4CA(
        sample=sample,
        variant_key="put0",
        verbose=False,
        debug=True,
        stream=True,
        enable_mr=True,
    )

    result = runner.run()

    print("\n" + "=" * 60)
    print("Feature:", result["feature"])
    print("Variant:", result["variant"])
    print("\n[Generated Test Spec]\n")
    print(result["test_spec"])
    print("\n[Generated Test Code]\n")
    print(result["generated_test_code"])