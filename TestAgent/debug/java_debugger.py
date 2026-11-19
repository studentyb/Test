import subprocess
import shlex
from typing import Optional, Tuple, Dict, Any
import os


def run_java_line_tracer(
        project_path: str,
        class_name: str,
        method_name: str,
        test_method: str,
        jar_path: str = "line-tracer.jar",
        add_modules: str = "jdk.jdi",
        timeout: Optional[int] = None,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None
) -> Tuple[int, str, str]:
    """
    执行Java行追踪器命令

    Args:
        project_path: 项目路径 (--project 参数)
        class_name: 完整的类名 (--class 参数)
        method_name: 方法名 (--method 参数)
        test_method: 测试方法 (--test 参数)
        jar_path: line-tracer.jar 的路径，默认为当前目录下的line-tracer.jar
        add_modules: --add-modules 参数，默认为 "jdk.jdi"
        timeout: 命令超时时间（秒），None表示无超时
        cwd: 工作目录
        env: 环境变量字典

    Returns:
        Tuple[int, str, str]: (返回码, 标准输出, 标准错误)
    """

    # 构建命令
    cmd = [
        "java",
        f"--add-modules", add_modules,
        "-jar", jar_path,
        "--project", project_path,
        "--class", class_name,
        "--method", method_name,
        "--test", test_method
    ]

    try:
        # 执行命令
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
            check=False  # 不抛出异常，由调用者处理返回码
        )

        return result.returncode, result.stdout, result.stderr

    except subprocess.TimeoutExpired as e:
        return -1, "", f"命令执行超时（{timeout}秒）"
    except FileNotFoundError:
        return -1, "", f"找不到java命令或jar文件: {jar_path}"
    except Exception as e:
        return -1, "", f"执行出错: {str(e)}"


def run_java_line_tracer_with_output(
        project_path: str,
        class_name: str,
        method_name: str,
        test_method: str,
        jar_path: str = "line-tracer.jar",
        add_modules: str = "jdk.jdi",
        timeout: Optional[int] = None,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        print_output: bool = True
) -> Tuple[int, str, str]:
    """
    执行Java行追踪器命令，并可选择实时打印输出

    Args:
        project_path: 项目路径
        class_name: 完整的类名
        method_name: 方法名
        test_method: 测试方法
        jar_path: line-tracer.jar路径
        add_modules: --add-modules参数
        timeout: 超时时间
        cwd: 工作目录
        env: 环境变量
        print_output: 是否实时打印输出

    Returns:
        Tuple[int, str, str]: (返回码, 标准输出, 标准错误)
    """

    cmd = [
        "java",
        f"--add-modules", add_modules,
        "-jar", jar_path,
        "--project", project_path,
        "--class", class_name,
        "--method", method_name,
        "--test", test_method
    ]

    if print_output:
        print(f"执行命令: {' '.join(cmd)}")
        print("-" * 50)

    try:
        if print_output:
            # 实时打印输出
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=cwd,
                env=env
            )

            stdout_lines = []
            stderr_lines = []

            # 实时读取并打印输出
            def read_stream(stream, lines_list, stream_name):
                for line in iter(stream.readline, ''):
                    lines_list.append(line)
                    if print_output:
                        print(f"{stream_name}: {line}", end='')

            import threading
            stdout_thread = threading.Thread(
                target=read_stream,
                args=(process.stdout, stdout_lines, "STDOUT")
            )
            stderr_thread = threading.Thread(
                target=read_stream,
                args=(process.stderr, stderr_lines, "STDERR")
            )

            stdout_thread.start()
            stderr_thread.start()

            process.wait(timeout=timeout)

            stdout_thread.join()
            stderr_thread.join()

            stdout = ''.join(stdout_lines)
            stderr = ''.join(stderr_lines)

            return process.returncode, stdout, stderr

        else:
            # 不实时打印，直接获取输出
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                env=env,
                check=False
            )
            return result.returncode, result.stdout, result.stderr

    except subprocess.TimeoutExpired:
        process.kill()
        return -1, "", f"命令执行超时（{timeout}秒）"
    except FileNotFoundError:
        return -1, "", f"找不到java命令或jar文件: {jar_path}"
    except Exception as e:
        return -1, "", f"执行出错: {str(e)}"


# 使用示例
if __name__ == "__main__":

    returncode, stdout, stderr = run_java_line_tracer(
        project_path=r'D:\****\TestAgent\dataset\RQ4\workdir\Actor_relationship_game',
        class_name="Actor_relationship_game.GameplayInterface",
        method_name="findConnections",
        test_method="Actor_relationship_game.GameplayInterfaceFindConnectionsTest#testTC_002_positiveNoConnectionFoundBetweenTwoActors",
        jar_path=r"D:\BJFU\TestAgent\project\TestAgent\debug\line-tracer.jar"
    )


    print(f"返回码: {returncode}")
    print(f"标准输出: {stdout}")
    print(f"标准错误: {stderr}")

