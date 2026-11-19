import json
import os
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI

# ================= 配置区域 =================


INPUT_FILE = "input.jsonl"  # 输入的 jsonl 文件路径
OUTPUT_FILE = "output.jsonl"  # 输出的 jsonl 文件路径
API_KEY = os.environ["DEEPSEEK_API_KEY"]  # 替换为你的大模型 API KEY
BASE_URL = "https://api.deepseek.com"  # 如果使用其他模型(如DeepSeek/千问)，请修改此URL
MODEL_NAME = "deepseek-reasoner"  # 替换为你使用的模型名称
MAX_RETRIES = 2  # API 请求失败时的最大重试次数

# --- 新增多线程配置 ---
MAX_WORKERS = 20  # 线程数：建议设置为 5~20 之间，取决于你的 API 并发额度
# ============================================

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

# 创建一个写入锁，确保多线程写入文件时不会发生冲突交错
write_lock = threading.Lock()


def build_prompt(data):
    """Construct the prompt for the LLM request"""
    target_code = data.get("target_method_code", "")
    target_comments = data.get("target_method_comments", "")
    test_code = data.get("test_method_code", "")

    prompt = f"""You are a senior software testing expert. I will provide a target function (including its code and comments) along with the code that tests it.
    Please analyze the logic of the test code and infer the underlying "Metamorphic Relation" (MR).

    [Input Information]
    Target function comments:
    {target_comments}

    Target function code:
    {target_code}

    Test function code:
    {test_code}

    You need to understand the functional requirements of the code under test based on the comments and the test itself, and analyze whether the test contains a Metamorphic Relation. An MR typically involves multiple invocations of the target method and assertions comparing the results of these multiple invocations.
    If an assertion compares a variable to a hardcoded constant (e.g., `assert(4, var)`), this is a traditional test oracle, not a Metamorphic Relation. In such cases, do not output the <MR> tag.
    Ensure that the inferred Metamorphic Relation is generally applicable to other inputs, rather than being a coincidental artifact of the specific test data used.

    [Output Requirements]
    1. Summarize the Metamorphic Relation in a single sentence.
    2. You must strictly follow this sentence structure: "For a function implementing [XXX functionality], if the input undergoes [YYY change], the output should [ZZZ change]."
    3. For automated extraction purposes, you must wrap this summary sentence within <MR> and </MR> tags.

    Examples:
    <MR>For a function implementing an array sorting feature, if a new element is added to the input array, the output array should contain this new element while maintaining the sorted order of the original elements.</MR>
    <MR>For a function implementing string concatenation, if the order of the two input strings is swapped, the length of the output string should remain unchanged.</MR>

    Please directly output the inferred result containing the tags:"""
    return prompt


def get_mr_from_llm(prompt):
    """调用大模型并提取 MR"""

    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": "You are a rigorous software testing expert skilled in analyzing code and extracting metamorphic relations."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                timeout=60  # 增加超时时间防止多线程拥堵
            )
            content = response.choices[0].message.content
            match = re.search(r"<MR>(.*?)</MR>", content, re.DOTALL)
            if match:
                return match.group(1).strip()
            else:
                return None
        except Exception as e:
            time.sleep(2)  # 失败后稍作停顿再重试
    return None


def process_single_task(line_num, data, fout):
    """单个线程要执行的任务：请求LLM并安全写入文件"""
    signature = data.get("fullyQualifiedSignature", "Unknown")

    prompt = build_prompt(data)
    mr_text = get_mr_from_llm(prompt)

    if mr_text:
        data["MR"] = mr_text
        json_str = json.dumps(data, ensure_ascii=False) + '\n'

        # 【关键】加锁写入文件，避免多个线程同时写入导致格式错乱
        with write_lock:
            fout.write(json_str)
            fout.flush()

        print(f"[成功 - 行 {line_num}] {signature[:50]}... -> {mr_text}")
        return True
    else:
        print(f"[失败 - 行 {line_num}] 无法生成或提取 MR -> {signature[:50]}...")
        return False


def main():
    # 1. 初始化断点续传集合
    processed_signatures = set()
    if os.path.exists(OUTPUT_FILE):
        print(f"发现已存在的输出文件，正在读取记录以实现断点续传...")
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        data = json.loads(line)
                        if "fullyQualifiedSignature" in data:
                            processed_signatures.add(data["fullyQualifiedSignature"])
                    except json.JSONDecodeError:
                        continue
        print(f"已加载 {len(processed_signatures)} 条历史记录。\n")

    # 2. 读取输入文件，筛选出需要处理的任务
    tasks = []  # 存放所有待处理的任务
    skipped_count = 0

    with open(INPUT_FILE, 'r', encoding='utf-8') as fin:
        for line_num, line in enumerate(fin, 1):
            if not line.strip():
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            signature = data.get("fullyQualifiedSignature")

            # 过滤1：已经处理过的
            if signature in processed_signatures:
                skipped_count += 1
                continue

            # 过滤2：测试代码为空的
            if not data.get("test_method_code"):
                skipped_count += 1
                continue

            # 将真正需要处理的数据加入任务列表
            tasks.append((line_num, data))

    print(f"数据扫描完毕：共跳过 {skipped_count} 条，即将进行多线程处理 {len(tasks)} 条任务...")
    print(f"启动线程池，并发数：{MAX_WORKERS}\n")

    # 3. 多线程处理并写入
    processed_count = 0
    error_count = 0

    # 以追加模式打开输出文件（由所有线程共享这个文件对象）
    with open(OUTPUT_FILE, 'a', encoding='utf-8') as fout:
        # 使用 ThreadPoolExecutor 管理线程
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # 提交所有任务到线程池
            # dictionary 映射 future 到任务信息，方便获取结果时知道是哪个任务
            future_to_task = {
                executor.submit(process_single_task, task[0], task[1], fout): task
                for task in tasks
            }

            # 只要有线程完成一个任务，就会执行这里的逻辑
            for future in as_completed(future_to_task):
                try:
                    is_success = future.result()
                    if is_success:
                        processed_count += 1
                    else:
                        error_count += 1
                except Exception as exc:
                    print(f"线程执行发生异常: {exc}")
                    error_count += 1

    print("\n" + "=" * 40)
    print("并发任务处理完成！")
    print(f"本次新成功处理: {processed_count} 条")
    print(f"失败/提取异常: {error_count} 条")
    print(f"总计跳过(已处理/为空): {skipped_count} 条")
    print("=" * 40)


if __name__ == "__main__":
    main()