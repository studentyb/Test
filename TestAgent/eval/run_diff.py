"""
执行 HumanEvalPlus 的 plus_input 对比测试脚本
使用 exec 动态执行方案
测试逻辑：
- 使用 task["plus_input"] 作为测试输入
- 将变体实现 candidate 与参考实现 put 进行对比
- 断言：assert candidate(*one_input) == put(*one_input)
"""

import json
from pathlib import Path
from typing import List, Dict, Any


def load_humanevalplus(dataset_path: str) -> List[Dict[str, Any]]:
    """
    加载 HumanEvalPlus.jsonl 数据集
    """
    tasks = []
    with open(dataset_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                tasks.append(json.loads(line))
    return tasks


def load_puts_variants(puts_root: str) -> Dict[str, Dict[str, str]]:
    """
    加载所有 PUTs 变体代码
    返回格式：
    {
        "HumanEval/0": {
            "variant_name": "code...",
            ...
        },
        ...
    }
    """
    puts_root_path = Path(puts_root)
    variants = {}

    for folder in puts_root_path.iterdir():
        if folder.is_dir() and folder.name.startswith("HumanEval_"):
            task_id = f"HumanEval/{folder.name.split('_')[1]}"

            task_variants = {}
            for py_file in folder.glob("*.py"):
                variant_name = py_file.stem
                with open(py_file, 'r', encoding='utf-8') as f:
                    task_variants[variant_name] = f.read()

            variants[task_id] = task_variants

    return variants


def build_reference_code(task: Dict[str, Any]) -> str:
    """
    构建参考实现 put 的完整代码
    """
    prompt = task["prompt"]
    canonical_solution = task["canonical_solution"]
    return prompt + canonical_solution


def run_plus_test_on_variant(task: Dict[str, Any], variant_code: str) -> Dict[str, Any]:
    """
    使用 plus_input 对单个变体进行测试：
    - candidate: 变体实现
    - put: 参考实现（由 prompt + canonical_solution 构成）
    """
    result = {
        "passed": False,
        "error": None,
        "error_type": None
    }

    entry_point = task["entry_point"]
    plus_inputs = task.get("plus_input", [])
    put_code = build_reference_code(task)

    try:
        # 1. 执行变体代码，得到 candidate
        candidate_scope = {}
        exec(variant_code, {}, candidate_scope)

        if entry_point not in candidate_scope:
            return {
                "passed": False,
                "error": f"Function {entry_point} not found in variant code",
                "error_type": "FUNCTION_NOT_FOUND_IN_VARIANT"
            }

        candidate = candidate_scope[entry_point]

        # 2. 执行参考实现代码，得到 put
        put_scope = {}
        exec(put_code, {}, put_scope)

        if entry_point not in put_scope:
            return {
                "passed": False,
                "error": f"Function {entry_point} not found in reference code",
                "error_type": "FUNCTION_NOT_FOUND_IN_REFERENCE"
            }

        put = put_scope[entry_point]

        # 3. 使用 plus_input 驱动测试
        def check(candidate, put):
            for idx, one_input in enumerate(plus_inputs):
                candidate_result = candidate(*one_input)
                put_result = put(*one_input)

                assert candidate_result == put_result, (
                    f"Mismatch at plus_input[{idx}] = {one_input}, "
                    f"candidate_result = {candidate_result}, "
                    f"put_result = {put_result}"
                )

        check(candidate, put)
        result["passed"] = True

    except AssertionError as e:
        result["error"] = str(e)
        result["error_type"] = "ASSERTION_FAILED"
    except Exception as e:
        result["error"] = str(e)
        result["error_type"] = type(e).__name__

    return result


def run_all_variants(tasks: List[Dict[str, Any]],
                     variants: Dict[str, Dict[str, str]],
                     task_filter: List[str] = None) -> Dict[str, Any]:
    """
    运行所有任务的变体测试，并输出简洁进度
    """
    results = {}
    total_tests = 0
    passed_tests = 0

    filtered_tasks = []
    for task in tasks:
        task_id = task["task_id"]
        if task_filter and task_id not in task_filter:
            continue
        if variants.get(task_id, {}):
            filtered_tasks.append(task)

    total_tasks = len(filtered_tasks)
    print(f"\n共需处理 {total_tasks} 个任务。")

    for task_index, task in enumerate(filtered_tasks, start=1):
        task_id = task["task_id"]
        task_variants = variants.get(task_id, {})

        # 既然每个任务只有一个变体，就直接取第一个
        variant_name, variant_code = next(iter(task_variants.items()))

        print(f"[{task_index}/{total_tasks}] 正在处理任务: {task_id}")

        test_result = run_plus_test_on_variant(task, variant_code)
        results[task_id] = {
            variant_name: test_result
        }

        total_tests += 1
        if test_result["passed"]:
            passed_tests += 1
            print(f"  结果: PASS")
        else:
            print(f"  结果: FAIL ({test_result['error_type']})")

    summary = {
        "total_tests": total_tests,
        "passed": passed_tests,
        "failed": total_tests - passed_tests,
        "success_rate": passed_tests / total_tests if total_tests > 0 else 0
    }

    return {"results": results, "summary": summary}


def print_summary(summary: Dict[str, Any]):
    """打印测试结果摘要"""
    print("\n" + "=" * 60)
    print("plus_input 对比测试结果摘要")
    print("=" * 60)
    print(f"总测试数: {summary['total_tests']}")
    print(f"通过: {summary['passed']}")
    print(f"失败: {summary['failed']}")
    print(f"通过率: {summary['success_rate']:.2%}")
    print("=" * 60)


def print_task_results(task_id: str, task_results: Dict[str, Any]):
    """打印单个任务的测试结果"""
    print(f"\n{task_id}:")
    for variant_name, result in task_results.items():
        status = "[PASS]" if result["passed"] else f"[FAIL] {result['error_type']}"
        print(f"  {variant_name}: {status}")
        if not result["passed"] and result["error"]:
            print(f"    Error: {result['error'][:200]}")


def save_results(results: Dict[str, Any], output_path: str):
    """保存测试结果到 JSON 文件"""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n结果已保存到: {output_path}")


if __name__ == "__main__":
    dataset_path = Path(__file__).parent / "dataset" / "HumanEvalPlus.jsonl"
    puts_root = Path(__file__).parent / "dataset" / "PUTs"

    print("正在加载数据集...")
    tasks = load_humanevalplus(str(dataset_path))

    print("正在加载 PUTs 变体...")
    variants = load_puts_variants(str(puts_root))

    print("\n正在使用 plus_input 运行 candidate vs put 对比测试...")
    result = run_all_variants(tasks, variants, task_filter=None)

    print_summary(result["summary"])

    print("\n前 3 个任务的详细结果:")
    for task_id, task_results in list(result["results"].items())[:3]:
        print_task_results(task_id, task_results)

    output_path = Path(__file__).parent / "plus_test_results.json"
    save_results(result, str(output_path))