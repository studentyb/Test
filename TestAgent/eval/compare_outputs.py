"""
比较bug版本和原始版本在plus_input输入下的输出一致性
"""

import json
import math
from pathlib import Path
from typing import List, Dict, Any, Tuple, Union
from collections import defaultdict


def load_humanevalplus(dataset_path: str) -> List[Dict[str, Any]]:
    """加载 HumanEvalPlus.jsonl 数据集"""
    tasks = []
    with open(dataset_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                tasks.append(json.loads(line))
    return tasks


def load_puts_variants(puts_root: str) -> Dict[str, Dict[str, str]]:
    """加载所有PUTs变体代码"""
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


def execute_function(code: str, entry_point: str) -> callable:
    """
    执行代码并获取指定函数

    Args:
        code: Python代码字符串
        entry_point: 函数名

    Returns:
        函数对象，如果失败返回None
    """
    try:
        local_scope = {}
        exec(code, {}, local_scope)
        return local_scope.get(entry_point)
    except Exception:
        return None


def compare_outputs_with_tolerance(
    a: Any,
    b: Any,
    atol: float = 0
) -> bool:
    """
    比较两个值，支持数值容忍度

    Args:
        a, b: 要比较的值
        atol: 绝对容忍度

    Returns:
        是否相等
    """
    if atol > 0:
        # 数值比较
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return math.isclose(a, b, abs_tol=atol)
        elif isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
            if len(a) != len(b):
                return False
            return all(compare_outputs_with_tolerance(x, y, atol) for x, y in zip(a, b))

    # 普通比较
    return a == b


def compare_variant_outputs(
    task: Dict[str, Any],
    variant_code: str,
    use_plus_input: bool = True
) -> Dict[str, Any]:
    """
    比较变体版本和原始版本在输入下的输出一致性

    Args:
        task: HumanEvalPlus任务数据
        variant_code: 变体代码
        use_plus_input: 是否使用plus_input（True）还是base_input（False）

    Returns:
        {
            "total_inputs": int,
            "consistent": int,
            "inconsistent": int,
            "errors": int,
            "details": List[Dict]  # 每个输入的比较结果
        }
    """
    entry_point = task["entry_point"]
    atol = task.get("atol", 0)

    # 选择输入数据
    inputs = task["plus_input"] if use_plus_input else task["base_input"]

    # 获取原始版本函数
    original_code = task["prompt"] + task["canonical_solution"]
    original_func = execute_function(original_code, entry_point)
    if original_func is None:
        return {
            "total_inputs": len(inputs),
            "consistent": 0,
            "inconsistent": 0,
            "errors": len(inputs),
            "details": [],
            "error": "Failed to load original function"
        }

    # 获取变体版本函数
    variant_func = execute_function(variant_code, entry_point)
    if variant_func is None:
        return {
            "total_inputs": len(inputs),
            "consistent": 0,
            "inconsistent": 0,
            "errors": len(inputs),
            "details": [],
            "error": "Failed to load variant function"
        }

    # 比较每个输入
    results = {
        "total_inputs": len(inputs),
        "consistent": 0,
        "inconsistent": 0,
        "errors": 0,
        "details": []
    }

    for idx, input_args in enumerate(inputs):
        detail = {
            "index": idx,
            "input": input_args,
            "original_output": None,
            "variant_output": None,
            "original_error": None,
            "variant_error": None,
            "status": "unknown"
        }

        try:
            # 调用原始版本
            if isinstance(input_args, (list, tuple)):
                original_output = original_func(*input_args)
            else:
                original_output = original_func(input_args)
            detail["original_output"] = original_output
        except Exception as e:
            detail["original_error"] = str(e)
            results["errors"] += 1
            detail["status"] = "original_error"
            results["details"].append(detail)
            continue

        try:
            # 调用变体版本
            if isinstance(input_args, (list, tuple)):
                variant_output = variant_func(*input_args)
            else:
                variant_output = variant_func(input_args)
            detail["variant_output"] = variant_output
        except Exception as e:
            detail["variant_error"] = str(e)
            results["errors"] += 1
            detail["status"] = "variant_error"
            results["details"].append(detail)
            continue

        # 比较输出
        if compare_outputs_with_tolerance(original_output, variant_output, atol):
            results["consistent"] += 1
            detail["status"] = "consistent"
        else:
            results["inconsistent"] += 1
            detail["status"] = "inconsistent"

        results["details"].append(detail)

    return results


def compare_all_variants(
    tasks: List[Dict[str, Any]],
    variants: Dict[str, Dict[str, str]],
    use_plus_input: bool = True,
    task_filter: List[str] = None
) -> Dict[str, Any]:
    """
    比较所有变体的输出一致性

    Args:
        tasks: HumanEvalPlus任务列表
        variants: PUTs变体字典
        use_plus_input: 是否使用plus_input
        task_filter: 可选，只比较指定的task_id列表

    Returns:
        {
            "results": {
                "task_id": {
                    "variant_name": comparison_result
                }
            },
            "summary": {...}
        }
    """
    results = {}
    summary = {
        "total_tasks": 0,
        "total_variants": 0,
        "total_inputs": 0,
        "consistent": 0,
        "inconsistent": 0,
        "errors": 0,
        "input_type": "plus_input" if use_plus_input else "base_input"
    }

    for task in tasks:
        task_id = task["task_id"]

        if task_filter and task_id not in task_filter:
            continue

        task_variants = variants.get(task_id, {})
        if not task_variants:
            continue

        task_results = {}
        for variant_name, variant_code in task_variants.items():
            comparison = compare_variant_outputs(task, variant_code, use_plus_input)
            task_results[variant_name] = comparison

            # 更新摘要
            summary["total_variants"] += 1
            summary["total_inputs"] += comparison["total_inputs"]
            summary["consistent"] += comparison["consistent"]
            summary["inconsistent"] += comparison["inconsistent"]
            summary["errors"] += comparison["errors"]

        results[task_id] = task_results

    summary["total_tasks"] = len(results)
    summary["consistency_rate"] = (
        summary["consistent"] / summary["total_inputs"]
        if summary["total_inputs"] > 0 else 0
    )

    return {"results": results, "summary": summary}


def print_comparison_summary(summary: Dict[str, Any]):
    """打印比较结果摘要"""
    print("\n" + "="*60)
    print(f"输出一致性比较摘要 ({summary['input_type']})")
    print("="*60)
    print(f"任务数: {summary['total_tasks']}")
    print(f"变体数: {summary['total_variants']}")
    print(f"总输入数: {summary['total_inputs']}")
    print(f"一致: {summary['consistent']}")
    print(f"不一致: {summary['inconsistent']}")
    print(f"错误: {summary['errors']}")
    print(f"一致性率: {summary['consistency_rate']:.2%}")
    print("="*60)


def print_task_comparison(task_id: str, task_results: Dict[str, Any], max_details: int = 3):
    """打印单个任务的比较结果"""
    print(f"\n{task_id}:")
    for variant_name, result in task_results.items():
        print(f"  {variant_name}:")
        print(f"    总输入: {result['total_inputs']}")
        print(f"    一致: {result['consistent']}, 不一致: {result['inconsistent']}, 错误: {result['errors']}")

        # 显示不一致的示例
        inconsistent_details = [d for d in result['details'] if d['status'] == 'inconsistent']
        if inconsistent_details:
            print(f"    不一致示例 (最多{max_details}个):")
            for detail in inconsistent_details[:max_details]:
                print(f"      输入#{detail['index']}: {detail['input']}")
                print(f"        原始: {detail['original_output']}")
                print(f"        变体: {detail['variant_output']}")


def save_comparison_results(results: Dict[str, Any], output_path: str):
    """保存比较结果到JSON文件"""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n结果已保存到: {output_path}")


if __name__ == "__main__":
    # 数据集路径
    dataset_path = Path(__file__).parent / "dataset" / "HumanEvalPlus.jsonl"
    puts_root = Path(__file__).parent / "dataset" / "PUTs"

    # 加载数据
    print("正在加载数据集...")
    tasks = load_humanevalplus(str(dataset_path))

    print("正在加载PUTs变体...")
    variants = load_puts_variants(str(puts_root))

    # [比较plus_input (设置为False使用base_input)]
    use_plus_input = True

    # 测试过滤：只测试前5个任务
    task_filter = [task["task_id"] for task in tasks[:5]]

    print(f"\n正在比较输出一致性 (使用 {['base_input', 'plus_input'][use_plus_input]})...")
    result = compare_all_variants(tasks, variants, use_plus_input=use_plus_input, task_filter=task_filter)

    # 打印摘要
    print_comparison_summary(result["summary"])

    # 打印前3个任务的详细结果
    print("\n前3个任务的详细结果:")
    for task_id, task_results in list(result["results"].items())[:3]:
        print_task_comparison(task_id, task_results)

    # 保存结果
    output_path = Path(__file__).parent / "comparison_results.json"
    save_comparison_results(result, str(output_path))
