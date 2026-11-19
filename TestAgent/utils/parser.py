# 解析各种内容
import json
import re
from typing import Tuple, Optional, Dict


def parse_file_and_code(raw: str) -> Tuple[Optional[str], str]:
    """
    从模型输出中解析「## FILE: 相对路径」和代码块，返回 (相对路径 或 None, 纯代码内容)。
    格式示例：

    ## FILE: tests/test_xxx.py
    ```python
    ...
    ```
    """
    file_code_pattern = re.compile(
        r"##\s*FILE:\s*(\S+)\s*\n.*?```(?:python|java)?\s*\n(.*?)```",
        re.DOTALL | re.IGNORECASE,
    )
    match = file_code_pattern.search(raw)
    if match:
        file_relative = match.group(1).strip()
        code = match.group(2).strip()
        return file_relative, code

    # 无 ## FILE 时回退：仅提取代码块或整段
    code_block = re.search(
        r"```(?:python|java)?\s*\n?(.*?)```", raw, re.DOTALL | re.IGNORECASE
    )
    if code_block:
        return None, code_block.group(1).strip()
    return None, raw.strip()


def parse_debug_report(raw_output: str, feature_name: str, total: int, passed: int) -> Dict:
    """尝试从 Debug Agent 的输出中解析 JSON 报告，解析失败时返回兜底结构。"""
    # 尝试直接解析
    try:
        return json.loads(raw_output.strip())
    except json.JSONDecodeError:
        pass

    # 尝试从 markdown 代码块中提取 JSON
    json_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', raw_output, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 兜底：无法解析时返回原始输出作为 summary
    print(f"[Debug] Warning: Failed to parse Debug Agent output as JSON for {feature_name}")
    return {
        "overall_pass_rate": f"{passed}/{total}",
        "summary": raw_output[:2000],
        "test_results": [],
        "sut_bug_report": raw_output[:4000]
    }