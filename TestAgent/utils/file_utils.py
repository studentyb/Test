from datetime import datetime
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Optional, Tuple
from typing import Union

from utils.memory_utils import Memory


def archive_working_memory():
    src_dir = "memory/working_memory"
    if not os.path.exists(src_dir):
        return

    # 检查目录是否为空
    if not os.listdir(src_dir):
        return

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model = os.environ.get("MODEL", "")

        dst_dir = os.path.join("memory/Long-Term", f"{timestamp}_working_memory_{model}")
        os.makedirs(dst_dir, exist_ok=True)

        for name in os.listdir(src_dir):
            src_path = os.path.join(src_dir, name)
            dst_path = os.path.join(dst_dir, name)
            shutil.move(src_path, dst_path)

        print(f"[Archive] Archived working memory to: {dst_dir}")

    except Exception as e:
        print(f"[Archive] Failed to archive working memory: {e}")


def normalize_display_newlines(s: str) -> str:
    """将字符串中的字面量 \\n 转为实际换行，便于控制台正确显示。"""
    if not isinstance(s, str):
        s = str(s)
    return s.replace("\\n", "\n")


def collect_output(output, *, result_attr: str = "result") -> str:
    """
    统一处理 CrewAI 的流式与非流式输出，返回完整文本内容。

    :param output: PipelineStep.run() 的返回值（流式迭代器或结果对象）
    :param result_attr: 非流式时从 output 上取结果的属性名（默认 "result"，step1 用 "raw"）
    """
    if hasattr(output, '__iter__') and not isinstance(output, str):
        parts = []
        for chunk in output:
            content = getattr(chunk, "content", str(chunk))
            print(normalize_display_newlines(content), end="", flush=True)
            parts.append(content)
        return "".join(parts)
    text = getattr(output, result_attr, str(output))
    print(normalize_display_newlines(text), end="", flush=True)
    return text


def read_file(path: Union[str, Path], encoding: str = "utf-8") -> str:
    # 自动将字符串转为 Path，方便后续处理
    file_path = Path(path)

    # 判断文件是否存在
    if not file_path.is_file():
        raise FileNotFoundError(f"未找到文件: {file_path.resolve()}")

    # 读取并返回
    return file_path.read_text(encoding=encoding)


def write_file(
        path: Union[str, Path],
        content: str,
        *,
        encoding: str = "utf-8",
        overwrite: bool = True,
        create_parent: bool = True,
) -> None:
    """
    将内容写入指定文件

    :param path: 文件路径（str 或 Path）
    :param content: 要写入的内容
    :param encoding: 文件编码
    :param overwrite: 是否覆盖已有文件（True=覆盖，False=追加）
    :param create_parent: 是否自动创建父目录
    """
    file_path = Path(path)

    # 创建父目录
    if create_parent:
        file_path.parent.mkdir(parents=True, exist_ok=True)

    # 写入模式
    mode = "w" if overwrite else "a"

    file_path.write_text(content, encoding=encoding) if mode == "w" else \
        file_path.open(mode, encoding=encoding).__enter__().write(content)


def write_marked_block(feature_name: str, tag: str, content: str):
    """
    将内容包装为指定标记并写入文件，自动创建不存在的目录和文件。
    """

    # 1. 定义完整的文件路径
    file_path = Path(f"memory/working_memory/experiment/{feature_name}.log")

    # 2. 核心修改：确保父级目录存在
    # parents=True 会递归创建所有缺失的父目录
    # exist_ok=True 如果目录已存在则不会报错
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # 3. 构建要写入的块
    block = f"""<<<{tag}>>>
{content}
<<</{tag}>>>
"""

    # 4. 使用 'a' 模式：文件不存在会自动创建，存在则在末尾追加
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(block + "\n")


# 默认配置路径（可根据需要修改）
DEFAULT_QUARANTINE_DIR = "memory/working_memory/quarantine"
DEFAULT_LOG_FILE = "memory/working_memory/recovery_map.json"


def move_to_quarantine(
        file_path: str,
        feature_name: str,
        quarantine_dir: str = DEFAULT_QUARANTINE_DIR,
        log_file: str = DEFAULT_LOG_FILE
) -> Optional[str]:
    """
    将测试文件移入隔离区，并记录原始路径。
    """
    original_p = Path(file_path)
    q_dir_p = Path(quarantine_dir)
    log_p = Path(log_file)

    if not original_p.exists():
        print(f"[Warning] File not found: {file_path}")
        return None

    # 确保目录存在
    q_dir_p.mkdir(parents=True, exist_ok=True)
    log_p.parent.mkdir(parents=True, exist_ok=True)

    # 1. 生成唯一的隔离文件名 (Feature_时间戳_文件名)
    timestamp = int(time.time())
    q_filename = f"{feature_name}_{timestamp}_{original_p.name}"
    target_p = q_dir_p / q_filename

    try:
        # 2. 更新日志
        history = {}
        if log_p.exists():
            with open(log_p, 'r', encoding='utf-8') as f:
                try:
                    history = json.load(f)
                except json.JSONDecodeError:
                    history = {}

        history[str(target_p.absolute())] = str(original_p.absolute())

        with open(log_p, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=4, ensure_ascii=False)

        # 3. 执行移动
        shutil.move(str(original_p), str(target_p))
        print(f"[Quarantine] {original_p.name} -> {target_p}")
        return str(target_p)

    except Exception as e:
        print(f"[Error] Failed to quarantine {file_path}: {e}")
        return None


def restore_all(
        log_file: str = DEFAULT_LOG_FILE
):
    """
    根据日志将所有隔离文件移回原始位置。
    """
    log_p = Path(log_file)
    if not log_p.exists():
        print("[Info] No quarantine log found. Nothing to restore.")
        return

    try:
        with open(log_p, 'r', encoding='utf-8') as f:
            history = json.load(f)

        for q_path_str, ori_path_str in history.items():
            q_p = Path(q_path_str)
            ori_p = Path(ori_path_str)

            if q_p.exists():
                ori_p.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(q_p), str(ori_p))
                print(f"[Restore] {q_p.name} -> {ori_p}")
            else:
                print(f"[Warning] Quarantined file missing: {q_path_str}")

        # 清理日志
        log_p.unlink()
        print("[Success] All tests restored and log cleared.")

    except Exception as e:
        print(f"[Error] Restoration failed: {e}")


def save_code_to_file(code: str, path: str):
    pattern = r"```(?:python|java)\s+(.*?)```"
    # 搜索代码块
    match = re.search(pattern, code, re.DOTALL | re.IGNORECASE)
    if match:
        # 如果找到了代码块，提取组1的内容（即代码本身），并去除首尾空白
        content_to_write = match.group(1).strip()
    else:
        # 如果找不到 Markdown 代码块，则假设原始内容即为代码
        content_to_write = code.strip()
    # 确保目录存在
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # 写入处理后的内容
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content_to_write)

if __name__ == '__main__':
    restore_all('../memory/working_memory/recovery_map.json')