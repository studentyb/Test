#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from pathlib import Path


def collect_files(root_dir, extensions=['.java', '.py'], ignore_tests=True):
    """
    递归收集指定目录下所有指定扩展名的文件
    :param root_dir: 根目录
    :param extensions: 需要收集的文件扩展名
    :param ignore_tests: 是否忽略测试代码 (Java忽略src/test/java, Python忽略tests目录)
    """
    matched_files = []
    root_path = Path(root_dir).resolve()

    if not root_path.exists():
        print(f"错误: 目录 '{root_dir}' 不存在")
        return matched_files

    if not root_path.is_dir():
        print(f"错误: '{root_dir}' 不是一个目录")
        return matched_files

    for file_path in root_path.rglob('*'):
        if file_path.is_file() and file_path.suffix in extensions:

            # =============== 新增：过滤测试文件的逻辑 ===============
            if ignore_tests:
                # 将路径统一转换为用 '/' 分隔的字符串，保证跨平台兼容性
                posix_path = file_path.as_posix()
                # 获取路径的所有组成部分（例如：('src', 'tests', 'test_main.py')）
                path_parts = file_path.parts

                # Java: 忽略路径中包含 'src/test/java' 的文件
                if file_path.suffix == '.java' and 'src/test/java' in posix_path:
                    continue

                # Python: 忽略位于 'tests' 文件夹中的文件
                # 使用 path_parts 检查可以避免误伤名为 'tests.py' 的普通文件
                if file_path.suffix == '.py' and 'tests' in path_parts:
                    continue
            # ======================================================

            matched_files.append(file_path)

    return matched_files


def build_tree_structure(root_dir, file_paths):
    """
    根据文件路径列表构建树形目录结构
    返回一个字典，表示目录树
    """
    tree = {}
    root_path = Path(root_dir).resolve()

    for file_path in file_paths:
        # 获取相对于根目录的路径部分
        rel_path = file_path.relative_to(root_path)
        parts = rel_path.parts

        current = tree
        for i, part in enumerate(parts):
            if i == len(parts) - 1:  # 文件
                current.setdefault('files', []).append(part)
            else:  # 目录
                current = current.setdefault('dirs', {}).setdefault(part, {})

    return tree


def render_tree(tree, prefix=''):
    """
    将树形结构渲染为字符串
    """
    lines = []
    dirs = tree.get('dirs', {})
    files = tree.get('files', [])

    # 先处理目录（排序）
    dir_items = sorted(dirs.items())
    for i, (dir_name, subtree) in enumerate(dir_items):
        is_last = (i == len(dir_items) - 1) and not files
        lines.append(f"{prefix}{'└── ' if is_last else '├── '}{dir_name}/")
        # 递归渲染子目录，注意前缀的变化
        extension = '    ' if is_last else '│   '
        lines.extend(render_tree(subtree, prefix + extension))

    # 再处理文件（排序）
    file_items = sorted(files)
    for i, file_name in enumerate(file_items):
        is_last = (i == len(file_items) - 1)
        lines.append(f"{prefix}{'└── ' if is_last else '├── '}{file_name}")

    return lines


def generate_tree_string(root_dir, file_paths):
    """
    生成树形目录结构的字符串
    """
    root_path = Path(root_dir).resolve()
    tree = build_tree_structure(root_path, file_paths)

    lines = [f"{root_path.name}/"]
    lines.extend(render_tree(tree))
    return '\n'.join(lines)


def concatenate_files(file_paths, output_file=None, tree_string=None):
    """
    将树形结构和多个文件内容拼接成一个大的文本
    """
    result = []

    # 如果提供了树形结构，先写入
    if tree_string:
        result.append("#" + "=" * 78 + "\n")
        result.append("# 项目目录结构 (已过滤测试文件)\n")
        result.append("#" + "=" * 78 + "\n\n")
        result.append(tree_string)
        result.append("\n\n")
        result.append("#" + "=" * 78 + "\n")
        result.append("# 文件内容\n")
        result.append("#" + "=" * 78 + "\n\n")

    # 写入每个文件的内容
    for file_path in file_paths:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            result.append(f"\n{'=' * 80}\n")
            result.append(f"// 文件: {file_path}\n")
            result.append(f"{'=' * 80}\n\n")
            result.append(content)
            result.append("\n\n")

        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='gbk') as f:
                    content = f.read()
                result.append(f"\n{'=' * 80}\n")
                result.append(f"// 文件: {file_path} (使用GBK编码)\n")
                result.append(f"{'=' * 80}\n\n")
                result.append(content)
                result.append("\n\n")
            except Exception as e:
                error_msg = f"// 无法读取文件 {file_path}: {str(e)}\n"
                result.append(error_msg)
        except Exception as e:
            error_msg = f"// 处理文件 {file_path} 时出错: {str(e)}\n"
            result.append(error_msg)

    final_content = ''.join(result)

    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(final_content)
        return output_file
    else:
        return final_content


# ==================== 配置区域 ====================
# 请修改下面的变量为你的实际目录和输出文件名
input_directory = "/home/mgh/dev/data/dataset/PT/JAVA/PongGame"  # 要遍历的根目录
output_file = "merged_output_without_tests.txt"  # 输出文件名（可包含路径）
# =================================================


if __name__ == "__main__":
    print(f"正在扫描目录: {input_directory}")

    # 默认开启 ignore_tests=True，过滤掉测试文件
    files = collect_files(input_directory, ignore_tests=True)

    if not files:
        print("没有找到任何非测试的 .java 或 .py 文件")
    else:
        print(f"过滤后共找到 {len(files)} 个核心源码文件")
        print("正在生成目录树...")
        tree_str = generate_tree_string(input_directory, files)
        print("正在合并文件内容...")
        result_path = concatenate_files(files, output_file, tree_str)
        print(f"合并完成！输出文件: {result_path}")
        print(f"文件大小: {os.path.getsize(result_path):,} 字节")
