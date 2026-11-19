"""
调用方客户端：通过 subprocess 调用 ta.py 进行测试生成。
可直接复制到调用方项目中使用，无需依赖 matev1 的任何模块。

用法示例::

    from ta_client import run_test_generation

    # 单次调用
    result = run_test_generation(
        ta_project_root="/path/to/matev1",
        sut_root="/path/to/project",
        put="被测代码...",
        feature="addExam",
        conda_env="matev1_env",
    )
    print(result["passed"], result["final_code"])


"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional


def run_test_generation(
    *,
    ta_project_root: str,
    sut_root: str,
    put: str,
    feature: str,
    build: str = "maven",
    language: str = "java",
    dataset_root: str = None,
    conda_env: str = None,
    debug: bool = False,
    stream: bool = False,
    exp: bool = True,
    max_retries: int = 3,
    report_path: str = None,
    timeout: int = 600,
    uml_class: str
) -> dict:
    """通过 subprocess 调用 ta.py 生成测试，跨平台兼容 Windows / Linux。

    Args:
        ta_project_root: matev1 项目根目录的绝对路径。
        sut_root:        被测代码根目录。
        put:             被测代码 / 需求描述（任意长度字符串，内部通过临时文件传递）。
        feature:         被测功能名称。
        build:           构建工具，"maven" 或 "gradle"。
        language:        语言，"java" 或 "python"。
        dataset_root:    项目根目录（pom.xml 所在），默认与 sut_root 相同。
        conda_env:       matev1 所在的 conda 环境名。为 None 时使用当前 Python。
        debug:           是否开启 debug 打印。
        stream:          是否启用大模型流式输出。
        exp:             是否启用经验检索与复用。
        max_retries:     最大修复轮次。
        report_path:     报告输出路径，为 None 时自动使用临时文件。
        timeout:         子进程超时秒数（默认 600s / 10min）。

    Returns:
        dict: 至少包含以下字段::

            {
                "feature":     str,
                "passed":      bool,
                "status":      "passed" | "failed" | "error" | "timeout",
                "final_code":  str,   # 生成的测试代码
                "last_report": str,   # 最后一轮测试运行报告
            }
    """
    ta_root = Path(ta_project_root).resolve()
    ta_script = ta_root / "ta.py"

    # ---- 将 put 写入临时文件，避免 CLI 转义问题 ----
    fd, put_file_str = tempfile.mkstemp(suffix=".txt", prefix="ta_put_")
    put_file = Path(put_file_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(put)
    except Exception:
        os.close(fd)
        raise

    # ---- 报告文件 ----
    auto_report = report_path is None
    if auto_report:
        rfd, report_file_str = tempfile.mkstemp(suffix=".json", prefix="ta_report_")
        os.close(rfd)
        report_file = Path(report_file_str)
    else:
        report_file = Path(report_path).resolve()

    try:
        # ---- 构造 ta.py 命令参数 ----
        python_bin = "python" if conda_env else sys.executable
        cmd_args = [
            python_bin,
            str(ta_script),
            "--sut_root", str(Path(sut_root).resolve()),
            "--put_file", str(put_file),
            "--feature", feature,
            "--build", build,
            "--l", language,
            "--max_retries", str(max_retries),
            "--report_path", str(report_file),
        ]

        if dataset_root:
            cmd_args.extend(["--dataset_root", str(Path(dataset_root).resolve())])
        if debug:
            cmd_args.append("--debug")
        if not stream:
            cmd_args.append("--no_stream")
        if not exp:
            cmd_args.append("--no_exp")
        if uml_class:
            cmd_args.append("--uml_class", uml_class)

        # conda 环境包裹
        if conda_env:
            cmd_args = [
                "conda", "run", "-n", conda_env, "--no-capture-output",
            ] + cmd_args

        # ---- 执行 ----
        result = subprocess.run(
            cmd_args,
            cwd=str(ta_root),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )

        # ---- 读取报告 ----
        if report_file.exists():
            report = json.loads(report_file.read_text(encoding="utf-8"))
        else:
            report = {
                "feature": feature,
                "passed": False,
                "status": "error",
                "final_code": "",
                "last_report": "",
                "error": result.stderr[-2000:] if result.stderr else "No report generated",
            }

        report["returncode"] = result.returncode
        return report

    except subprocess.TimeoutExpired:
        return {
            "feature": feature,
            "passed": False,
            "status": "timeout",
            "final_code": "",
            "last_report": "",
            "error": f"Timed out after {timeout}s",
        }
    except Exception as e:
        return {
            "feature": feature,
            "passed": False,
            "status": "error",
            "final_code": "",
            "last_report": "",
            "error": str(e),
        }
    finally:
        # 清理临时文件
        try:
            if put_file.exists():
                put_file.unlink()
        except OSError:
            pass
        try:
            if auto_report and report_file.exists():
                report_file.unlink()
        except OSError:
            pass

if __name__ == '__main__':
    # 单次调用
    result = run_test_generation(
        ta_project_root="/path/to/matev1",
        sut_root="/path/to/project",
        put="被测代码...",
        feature="addExam",
        conda_env="matev1_env",
    )
    print(result["passed"], result["final_code"])