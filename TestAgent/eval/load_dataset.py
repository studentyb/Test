"""
加载 HumanEvalPlus 数据集的脚本
"""

import json
from pathlib import Path
from typing import List, Dict, Any


def load_humanevalplus(dataset_path: str) -> List[Dict[str, Any]]:
    """
    加载 HumanEvalPlus.jsonl 数据集

    Args:
        dataset_path: 数据集文件路径

    Returns:
        包含所有任务数据的列表
    """
    tasks = []
    with open(dataset_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                tasks.append(json.loads(line))
    return tasks


def analyze_dataset(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    分析数据集统计信息

    Args:
        tasks: 任务列表

    Returns:
        统计信息字典
    """
    return {
        "total_tasks": len(tasks),
        "task_ids": [t["task_id"] for t in tasks],
        "entry_points": [t["entry_point"] for t in tasks],
        "avg_base_inputs": sum(len(t["base_input"]) for t in tasks) / len(tasks),
        "avg_plus_inputs": sum(len(t["plus_input"]) for t in tasks) / len(tasks),
    }


def get_task_by_id(tasks: List[Dict[str, Any]], task_id: str) -> Dict[str, Any]:
    """
    根据task_id获取特定任务

    Args:
        tasks: 任务列表
        task_id: 任务ID

    Returns:
        任务数据字典，如果未找到返回None
    """
    for task in tasks:
        if task["task_id"] == task_id:
            return task
    return None


def print_task_details(task: Dict[str, Any]) -> None:
    """
    打印指定任务的详细信息

    Args:
        task: 任务数据字典
    """
    print(f"\n{'='*60}")
    print(f"Task ID: {task['task_id']}")
    print(f"{'='*60}")
    print(f"\n[Prompt]")
    print(task['prompt'])
    print(f"\n[Canonical Solution]")
    print(task['canonical_solution'])
    print(f"{'='*60}\n")


if __name__ == "__main__":
    # 数据集路径
    dataset_path = Path(__file__).parent / "dataset" / "HumanEvalPlus.jsonl"

    # 加载数据集
    print(f"正在加载数据集: {dataset_path}")
    tasks = load_humanevalplus(str(dataset_path))

    # Task字段说明:
    # - task_id: 任务标识符 (如 "HumanEval/0")
    # - prompt: 函数签名 + 文档字符串
    # - entry_point: 函数入口点名称
    # - canonical_solution: 标准参考实现代码
    # - test: 测试代码 (包含assert断言)
    # - contract: 输入契约验证代码
    # - base_input: 原始测试用例输入列表
    # - plus_input: 扩展测试用例输入列表
    # - atol: 数值比较的绝对容忍度

    # 显示第一个任务的详细信息
    first_task = tasks[0]
    print(f"\n第一个任务示例 (task_id: {first_task['task_id']}):")
    print(f"  test: {first_task['test']}")
    print(f"  base input: {first_task['plus_input']}")

    # 打印指定任务的详细信息 (取消注释以使用)
    print_task_details(first_task)
