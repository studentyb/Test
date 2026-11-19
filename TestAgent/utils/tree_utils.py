import os
from pathlib import Path


def get_directory_tree(path, ignore_list=None):
    """
    生成指定目录的树结构字符串。

    :param path: 目标根目录路径
    :param ignore_list: 需要忽略的文件夹或文件名集合
    :return: 树结构的字符串
    """
    if ignore_list is None:
        ignore_list = {'.git', '__pycache__', '.pytest_cache', '.venv', '.vscode', '.idea', '.DS_Store'}

    tree_lines = []
    root_path = Path(path).resolve()
    tree_lines.append(f"{root_path.name}/")

    def build_tree(current_path, prefix=""):
        # 获取当前目录下所有条目，并进行排序（文件夹在前，文件名在后）
        try:
            entries = sorted(
                [e for e in current_path.iterdir() if e.name not in ignore_list],
                key=lambda s: (not s.is_dir(), s.name.lower())
            )
        except PermissionError:
            return

        entry_count = len(entries)
        for i, entry in enumerate(entries):
            is_last = (i == entry_count - 1)
            connector = "└── " if is_last else "├── "

            # 添加当前行
            tree_lines.append(f"{prefix}{connector}{entry.name}{'/' if entry.is_dir() else ''}")

            # 如果是文件夹，递归处理
            if entry.is_dir():
                new_prefix = prefix + ("    " if is_last else "│   ")
                build_tree(entry, new_prefix)

    build_tree(root_path)
    return "\n".join(tree_lines)

if __name__ == '__main__':
    # 使用示例
    target_path = "/home/mgh/dev/data/dataset/DevEval/python/readtime/src/" # 替换为你想要的目录
    tree_string = get_directory_tree(target_path)
    print(tree_string)


