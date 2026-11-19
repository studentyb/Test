"""
加载 HumanEval PUTs (Program Under Test) 变体的脚本
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional


def load_humanevalplus(
    dataset_path: str,
    fields: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    加载 HumanEvalPlus.jsonl 数据集，并可只保留指定字段

    Args:
        dataset_path: 数据集文件路径
        fields: 需要保留的字段列表。
                如果为 None，则保留整条记录的所有字段。

    Returns:
        包含任务数据的列表
    """
    tasks = []

    with open(dataset_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            item = json.loads(line)

            if fields is not None:
                item = {k: item[k] for k in fields if k in item}

            tasks.append(item)

    return tasks


def load_puts_variants(puts_root: str) -> Dict[str, Dict[str, str]]:
    """
    加载所有PUTs变体代码

    Args:
        puts_root: PUTs根目录路径

    Returns:
        嵌套字典: {task_id: {variant_name: code}}
        例如: {"HumanEval/0": {"put0": "code..."}}
    """
    puts_root_path = Path(puts_root)
    variants = {}

    for folder in puts_root_path.iterdir():
        if folder.is_dir() and folder.name.startswith("HumanEval_"):
            # 文件夹名 HumanEval_0 -> task_id HumanEval/0
            task_id = f"HumanEval/{folder.name.split('_')[1]}"

            task_variants = {}
            for py_file in folder.glob("*.py"):
                variant_name = py_file.stem  # 例如: put0
                with open(py_file, 'r', encoding='utf-8') as f:
                    task_variants[variant_name] = f.read()

            variants[task_id] = task_variants

    return variants


def get_task_variants(variants: Dict[str, Dict[str, str]], task_id: str) -> Dict[str, str]:
    """
    获取指定任务的所有变体

    Args:
        variants: 所有变体字典
        task_id: 任务ID (如 "HumanEval/0")

    Returns:
        该任务的变体字典，如果未找到返回空字典
    """
    return variants.get(task_id, {})


def get_variant_code(variants: Dict[str, Dict[str, str]], task_id: str, variant_name: str) -> str:
    """
    获取指定任务的指定变体代码

    Args:
        variants: 所有变体字典
        task_id: 任务ID (如 "HumanEval/0")
        variant_name: 变体名称 (如 "put0")

    Returns:
        变体代码字符串，如果未找到返回空字符串
    """
    task_variants = variants.get(task_id, {})
    return task_variants.get(variant_name, "")


def combine_with_humanevalplus(
    humaneval_tasks: List[Dict[str, Any]],
    put_variants: Dict[str, Dict[str, str]]
) -> List[Dict[str, Any]]:
    """
    将HumanEvalPlus数据集与PUTs变体合并

    Args:
        humaneval_tasks: HumanEvalPlus任务列表
        put_variants: PUTs变体字典

    Returns:
        合并后的任务列表，每个任务新增 'variants' 字段
    """
    combined = []
    for task in humaneval_tasks:
        task_copy = task.copy()
        task_copy['variants'] = put_variants.get(task['task_id'], {})
        combined.append(task_copy)
    return combined


if __name__ == "__main__":
    # 数据集路径
    dataset_path = Path(__file__).parent / "dataset" / "HumanEvalPlus.jsonl"
    puts_root = Path(__file__).parent / "dataset" / "PUTs"

    # 加载HumanEvalPlus数据集
    print(f"正在加载数据集: {dataset_path}")
    humaneval_tasks = load_humanevalplus(str(dataset_path),['task_id','prompt','entry_point'])

    # 加载PUTs变体
    print(f"正在加载PUTs变体: {puts_root}")
    put_variants = load_puts_variants(str(puts_root))

    print(f"\n加载完成:")
    print(f"  HumanEvalPlus任务数: {len(humaneval_tasks)}")
    print(f"  有变体的任务数: {len(put_variants)}")

    # 合并数据
    combined_tasks = combine_with_humanevalplus(humaneval_tasks, put_variants)

    # 显示第一个任务的变体信息
    first_task = combined_tasks[0]
    print(f"\n第一个任务 (task_id: {first_task['task_id']}):")
    print(f"  entry_point: {first_task['entry_point']}")
    print(f"  变体数量: {len(first_task['variants'])}")
    print(f"  变体名称: {list(first_task['variants'].keys())}")

    # 显示第一个变体的代码
    if first_task['variants']:
        first_variant_name = list(first_task['variants'].keys())[0]
        print(f"\n变体 '{first_variant_name}' 代码:")
        print(first_task['variants'][first_variant_name])
