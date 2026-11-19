# main.py
from pathlib import Path

from rag.db_instance import vector_db
from utils.chat import get_ai_response
from utils.file_utils import read_file

import json
import re
from pathlib import Path
from jinja2 import Template


def summarize_experience(feature_name, summarize_failures=False):
    print("debug pass")
    pass
    file_path = Path(f"memory/working_memory/experiment/{feature_name}.log")

    # 如果日志不存在，直接返回
    if not file_path.exists():
        print(f"⚠️ 找不到日志文件: {file_path}")
        return

    # 读取日志内容
    with open(file_path, "r", encoding="utf-8") as f:
        repair_log = f.read()

    # 加载 prompt 模板
    # 假设 read_file 是你自定义的读取文件内容的函数
    success_template = Template(read_file(Path(f"prompt/exp_summary/success_summary.md")))
    fail_template = Template(read_file(Path(f"prompt/exp_summary/fail_summary.md")))

    # 拼接 prompt
    success_prompt = success_template.render(repair_log=repair_log)
    fail_prompt=fail_template.render(repair_log=repair_log)

    # --- 处理成功经验 ---
    # 获取大模型回答
    res = get_ai_response(prompt=success_prompt)
    print(res)

    # 解析回答，获取相关字段
    try:
        # 修改正则表达式：优先匹配 JSON 数组 [...]，以支持多条经验
        json_match = re.search(r'\[.*\]', res, re.DOTALL)

        # 兼容处理：如果大模型仍然只返回了单个 JSON 对象 {...}
        if not json_match:
            json_match = re.search(r'\{.*\}', res, re.DOTALL)
            if not json_match:
                raise ValueError("大模型返回的内容中未找到 JSON 结构 (Array 或 Object)。")
            # 将单个字典用列表包裹，统一后续遍历逻辑
            parsed_data = [json.loads(json_match.group(0))]
        else:
            parsed_data = json.loads(json_match.group(0))

        # 遍历解析出的多条经验
        for index, exp in enumerate(parsed_data):
            error_type = exp.get("error_type", "UnknownError")
            error_log = exp.get("error_log", "No error log extracted")
            scenario = exp.get("scenario", f"Testing {feature_name}")
            solution = exp.get("solution", "No solution extracted")

            # --- 插入前检索去重逻辑 ---
            # 检索当前错误类型和场景下，最相似的 1 条历史成功经验
            existing_exps = vector_db.search_experience(
                query_log=error_log,
                query_scenario=scenario,
                error_type=error_type,
                top_k=1,
                only_success=True
            )

            is_duplicate = False
            if existing_exps:
                # 获取检索结果的相似度 (search_experience 已经计算了 1 - distance)
                highest_sim = existing_exps[0].get("similarity", 0)
                if highest_sim > 0.9:
                    is_duplicate = True
                    print(f"⏭️ 发现高度相似经验 (相似度: {highest_sim:.4f} > 0.9)，跳过插入: {error_type}")

            # 如果不存在高相似度经验，则执行插入
            if not is_duplicate:
                vector_db.add_experience(
                    error_type=error_type,
                    error_log=error_log,
                    scenario=scenario,
                    is_successful=True,
                    solution=solution
                )
                print(f"✅ 成功提取并插入【成功经验 {index + 1}】: {error_type} - {feature_name}")

    except Exception as e:
        print(f"⚠️ 解析大模型输出失败: {e}")
        print(f"原始输出: {res}")

    # --- 处理失败经验 (如果启用) ---
    if summarize_failures:
        print("\n📋 开始总结失败经验...")
        fail_res = get_ai_response(prompt=fail_prompt)
        print(fail_res)

        try:
            # 解析失败经验的大模型输出
            json_match = re.search(r'\[.*\]', fail_res, re.DOTALL)

            if not json_match:
                json_match = re.search(r'\{.*\}', fail_res, re.DOTALL)
                if not json_match:
                    print("⚠️ 失败经验总结：大模型返回的内容中未找到 JSON 结构")
                    return
                parsed_data = [json.loads(json_match.group(0))]
            else:
                parsed_data = json.loads(json_match.group(0))

            # 遍历解析出的失败经验
            for index, exp in enumerate(parsed_data):
                error_type = exp.get("error_type", "UnknownError")
                error_log = exp.get("error_log", "No error log extracted")
                scenario = exp.get("scenario", f"Testing {feature_name}")
                solution = exp.get("solution", "No solution extracted")

                # --- 插入前检索去重逻辑 ---
                # 检索当前错误类型和场景下，最相似的 1 条历史失败经验
                existing_exps = vector_db.search_experience(
                    query_log=error_log,
                    query_scenario=scenario,
                    error_type=error_type,
                    top_k=1,
                    only_success=False
                )

                is_duplicate = False
                if existing_exps:
                    highest_sim = existing_exps[0].get("similarity", 0)
                    if highest_sim > 0.9:
                        is_duplicate = True
                        print(f"⏭️ 发现高度相似失败经验 (相似度: {highest_sim:.4f} > 0.9)，跳过插入: {error_type}")

                # 如果不存在高相似度经验，则执行插入
                if not is_duplicate:
                    vector_db.add_experience(
                        error_type=error_type,
                        error_log=error_log,
                        scenario=scenario,
                        is_successful=False,  # 标记为失败经验
                        solution=solution
                    )
                    print(f"✅ 成功提取并插入【失败经验 {index + 1}】: {error_type} - {feature_name}")

        except Exception as e:
            print(f"⚠️ 解析失败经验大模型输出失败: {e}")
            print(f"原始输出: {fail_res}")

def search_exp(error_type, query_log, query_scenario, top_k, only_success=True):
    print("\n🔍 正在检索修复建议...")

    # 执行检索
    results = vector_db.search_experience(
        query_log=query_log,
        query_scenario=query_scenario,
        error_type=error_type,
        top_k=top_k,
        only_success=only_success
    )

    # 如果没有检索到结果，返回提示信息
    if not results:
        return None

    # 初始化用于拼接字符串的列表
    output_lines = ["检索到的历史修复经验如下：\n"]

    # 遍历结果并格式化
    for index, res in enumerate(results, start=1):
        status = "✅ 成功修复" if res.get('is_successful') else "❌ 失败尝试"
        similarity = res.get('similarity', 0)

        # 构建单条经验的文本描述
        exp_text = (
            f"--- 经验 {index} ({status}, 相似度: {similarity:.4f}) ---\n"
            f"【历史错误上下文】\n{res.get('document', '无历史日志记录')}\n\n"
            f"【建议的修复方案】\n{res.get('solution', '无修复方案记录')}\n"
        )

        output_lines.append(exp_text)

    # 使用换行符将所有字符串拼接并返回
    return "\n".join(output_lines)

if __name__ == "__main__":
    log="It is not possible to mock static methods of java.lang.System to avoid interfering with class loading what leads to infinite loops \
        at app//com.sohu.idcenter.SidWorkerTest.TC_007_Back_to_back_calls_with_increasing_timestamps_reset_sequence(SidWorkerTest.java:163)"
    res=search_exp('MockitoException',log,query_scenario="Testing the ID generation logic in SidWorker, which relies on timestamps obtained from System.currentTimeMillis. The tests initially attempted to mock static methods of System, leading to failures.",top_k=2,only_success=True)
    print(res)
    # summarize_experience('generate_timestamp_id')