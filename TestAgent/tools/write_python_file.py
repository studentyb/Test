import os
from typing import Optional, Type

import datetime
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class WriteFileInput(BaseModel):
    """输入 schema: 要写入的文件路径和内容。"""
    path: str = Field(..., description="目标文件绝对路径")
    code: str = Field(..., description="要写入的代码内容")
    overwrite: Optional[bool] = Field(False, description="是否覆盖已有文件 (True = 覆盖, False = 追加)")


class WriteCodeFileTool(BaseTool):
    name: str = "write_code_file"
    description: str = "Write given code to the specified file path."
    args_schema: Type[BaseModel] = WriteFileInput

    def _run(self, path: str, code: str, overwrite: bool = False) -> str:
        # --- DEBUG 信息 ---
        abs_path = os.path.abspath(path)
        print(f"--------------------------------------------------")
        print(f"[DEBUG] 工具被触发")
        print(f"[DEBUG] 目标路径 (相对): {path}")
        print(f"[DEBUG] 目标路径 (绝对): {abs_path}")
        print(f"[DEBUG] 写入模式: {'覆写 (w)' if overwrite else '追加 (a)'}")
        print(f"[DEBUG] 代码长度: {len(code)} 字符")
        if len(code) < 10:
            print(f"[DEBUG] 警告: 代码内容似乎为空或过短: '{code}'")
        # ------------------

        # 1. 确保目标文件目录存在
        dir_name = os.path.dirname(abs_path)  # 使用绝对路径更安全
        if dir_name and not os.path.exists(dir_name):
            try:
                os.makedirs(dir_name, exist_ok=True)
                print(f"[DEBUG] 创建目录成功: {dir_name}")
            except Exception as e:
                return f"Error creating directory {dir_name}: {e}"

        # 2. 写入文件
        try:
            mode = "w" if overwrite else "a"
            with open(abs_path, mode, encoding="utf-8") as f:
                f.write(code)
                if code and not code.endswith("\n"):
                    f.write("\n")
                # 强制刷新缓冲区，确保写入磁盘
                f.flush()
                os.fsync(f.fileno())
            print(f"[DEBUG] 文件写入操作完成。")
        except Exception as e:
            print(f"[DEBUG] 写入文件失败: {e}")
            return f"Error writing to file: {e}"

        # 3. 写日志 (修复了目录不存在会报错的 BUG)
        try:
            log_path = os.path.join("log", "log.txt")  # 使用 join 更安全
            # 确保 log 目录存在
            os.makedirs(os.path.dirname(log_path), exist_ok=True)

            log_entry = (
                f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"File: {abs_path} | Overwrite: {overwrite} | Size: {len(code)}\n"
            )
            with open(log_path, "a", encoding="utf-8") as log_file:
                log_file.write(log_entry)
        except Exception as e:
            print(f"[DEBUG] 写日志失败 (但不影响主流程): {e}")

        # 4. 内存记录逻辑 (Memory)
        # ... (原有逻辑保持不变，建议也加上 os.makedirs 检查) ...
        file_name = os.path.basename(path)
        if file_name.endswith(".java") or file_name.endswith(".py"):
            memory_dir = os.path.join("memory", "working_memory")
            os.makedirs(memory_dir, exist_ok=True)
            memory_file = os.path.join(memory_dir, "generatedTest.txt")
            with open(memory_file, "a", encoding="utf-8") as mem_file:
                mem_file.write(file_name + "\n")

        return f"Successfully wrote code to {abs_path}"

