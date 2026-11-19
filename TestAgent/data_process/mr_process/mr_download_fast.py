import json
import os
import time
import requests
import re
from urllib.parse import urlparse
import javalang

# ================= 配置区域 =================
GITHUB_PAT = os.environ["GITHUB_PAT"]  # 替换为你的 GitHub Personal Access Token
INPUT_FILE = "MTC_Dataset.json"  # 你的输入 JSON 文件路径
OUTPUT_FILE = "MRs.jsonl"  # 输出文件

BATCH_SIZE = 50  # 【优化点2】每处理 50 条数据，集中刷入一次磁盘，总共11000条，这会极大减少磁盘IO阻塞

HEADERS = {
    "Authorization": f"token {GITHUB_PAT}",
    "Accept": "application/vnd.github.v3+json"
}

IGNORE_METHODS = {
    'assertEquals', 'assertTrue', 'assertFalse', 'assertNull', 'assertNotNull',
    'assertThat', 'assertSame', 'assertNotSame', 'fail', 'assertArrayEquals',
    'mock', 'when', 'verify', 'spy', 'any', 'anyInt', 'anyString', 'doReturn', 'doThrow',
    'setUp', 'tearDown', 'initMocks', 'println', 'print', 'sleep', 'wait', 'notify',
    'getClass', 'getName', 'toString', 'equals', 'hashCode', 'size', 'length', 'get', 'set'
}

# ================= 全局缓存区域 (【优化点1】引入缓存) =================
# 1. 分支缓存
repo_branch_cache = {}
# 2. 文件内容缓存: 避免同一个类里的20个测试用例去GitHub下载20次同样的文件
file_content_cache = {}
# 3. 业务代码 AST 解析结果缓存: 避免同一个源码文件被 javalang 重复解析几十次
src_ast_methods_cache = {}


# ================= Github API & 文件下载 =================
def get_owner_repo(project_url):
    path = urlparse(project_url).path.strip('/')
    parts = path.split('/')
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None, None


def get_default_branch(owner, repo):
    cache_key = f"{owner}/{repo}"
    if cache_key in repo_branch_cache:
        return repo_branch_cache[cache_key]

    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    try:
        response = requests.get(api_url, headers=HEADERS, timeout=10)
        if response.status_code == 403 and 'X-RateLimit-Remaining' in response.headers:
            if int(response.headers.get('X-RateLimit-Remaining', 1)) == 0:
                reset_time = int(response.headers['X-RateLimit-Reset'])
                sleep_time = max(reset_time - int(time.time()), 0) + 5
                print(f"[!] API 限流，休眠 {sleep_time} 秒...")
                time.sleep(sleep_time)
                return get_default_branch(owner, repo)
        if response.status_code == 200:
            branch = response.json().get("default_branch", "master")
            repo_branch_cache[cache_key] = branch
            return branch
        else:
            print(f"    -> [Error] 获取分支失败: {response.status_code}")
    except Exception as e:
        print(f"    -> [Exception] {e}")
    return None


def get_cached_raw_file(owner, repo, branch, filepath):
    """带缓存的 GitHub 文件下载器"""
    cache_key = f"{owner}/{repo}/{branch}/{filepath}"

    # 命中缓存，直接返回（速度从1秒降低到0.001秒）
    if cache_key in file_content_cache:
        return file_content_cache[cache_key]

    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{filepath}"
    try:
        response = requests.get(raw_url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            content = response.text
            file_content_cache[cache_key] = content
            time.sleep(0.1)  # 仅在真正发生网络请求时微微休眠，防封
            return content
    except Exception:
        pass

    # 如果下载失败（如文件不存在），也缓存为 None，防止死磕报错的URL
    file_content_cache[cache_key] = None
    return None


def infer_source_filepath(test_filepath):
    src_path = test_filepath.replace("src/test/java", "src/main/java")
    src_path = re.sub(r'Test\.java$', '.java', src_path)
    src_path = re.sub(r'Tests\.java$', '.java', src_path)
    return src_path


# ================= 核心 AST 解析与提取逻辑 =================
def _extract_code_block(lines, start_line_idx):
    open_braces = 0
    started = False
    for i in range(start_line_idx, len(lines)):
        line_str = lines[i]
        if '{' in line_str:
            open_braces += line_str.count('{')
            started = True
        if '}' in line_str:
            open_braces -= line_str.count('}')

        if started and open_braces == 0:
            return "\n".join(lines[start_line_idx:i + 1])
    return lines[start_line_idx]


def extract_test_method_ast(source_code, target_test_name):
    if not source_code: return None, None
    try:
        tree = javalang.parse.parse(source_code)
        lines = source_code.splitlines()
        for path, node in tree.filter(javalang.tree.MethodDeclaration):
            if node.name == target_test_name:
                code = _extract_code_block(lines, node.position.line - 1)
                return node, code
    except Exception:
        pass
    return None, None


def get_cached_declared_methods(source_code, cache_key):
    """带缓存的被测源码 AST 解析器"""
    if not source_code: return {}

    # 命中缓存，直接返回已解析的方法列表（极大节省 CPU 时间）
    if cache_key in src_ast_methods_cache:
        return src_ast_methods_cache[cache_key]

    declared_methods = {}
    try:
        tree = javalang.parse.parse(source_code)
        lines = source_code.splitlines()
        for path, node in tree.filter(javalang.tree.MethodDeclaration):
            code = _extract_code_block(lines, node.position.line - 1)
            doc = node.documentation if hasattr(node, 'documentation') and node.documentation else ""
            if node.name not in declared_methods:
                declared_methods[node.name] = []
            declared_methods[node.name].append({"code": code, "comments": doc})
    except Exception:
        pass

    src_ast_methods_cache[cache_key] = declared_methods
    return declared_methods


def find_method_call_for_variable(method_node, var_name):
    if not method_node: return None
    for path, decl in method_node.filter(javalang.tree.LocalVariableDeclaration):
        for declarator in decl.declarators:
            if declarator.name == var_name:
                if isinstance(declarator.initializer, javalang.tree.MethodInvocation):
                    return declarator.initializer.member
    for path, assign in method_node.filter(javalang.tree.Assignment):
        if isinstance(assign.expressionl, javalang.tree.MemberReference):
            if assign.expressionl.member == var_name:
                if isinstance(assign.value, javalang.tree.MethodInvocation):
                    return assign.value.member
    return None


def analyze_mut_strategies(test_method_node, src_declared_methods, test_method_name):
    if not src_declared_methods or not test_method_node:
        return None, None

    # 使用 set 来收集所有找到的 MUT 名称，自动去重
    target_mut_names = set()

    # ==========================================
    # 策略一：从断言（Assert）语句中寻找所有可能的目标方法
    # ==========================================
    for path, node in test_method_node.filter(javalang.tree.MethodInvocation):
        if hasattr(node, 'member') and node.member and node.member.startswith('assert'):
            if hasattr(node, 'arguments') and node.arguments:
                for arg in node.arguments:
                    # 1. 断言参数直接是方法调用
                    if isinstance(arg, javalang.tree.MethodInvocation):
                        if hasattr(arg,
                                   'member') and arg.member in src_declared_methods and arg.member not in IGNORE_METHODS:
                            target_mut_names.add(arg.member)
                    # 2. 断言参数是变量引用，向上追溯赋值来源
                    elif isinstance(arg, javalang.tree.MemberReference):
                        var_name = arg.member
                        traced_method_name = find_method_call_for_variable(test_method_node, var_name)
                        if traced_method_name and traced_method_name in src_declared_methods and traced_method_name not in IGNORE_METHODS:
                            target_mut_names.add(traced_method_name)

    # ==========================================
    # 策略二：遍历测试方法中的所有普通方法调用
    # ==========================================
    for path, node in test_method_node.filter(javalang.tree.MethodInvocation):
        if hasattr(node, 'member') and node.member in src_declared_methods and node.member not in IGNORE_METHODS:
            target_mut_names.add(node.member)

    # ==========================================
    # 策略三：基于测试方法命名约定的名称推断
    # ==========================================
    if test_method_name and test_method_name.startswith("test") and len(test_method_name) > 4:
        name_without_test = test_method_name[4:]
        inferred_name = name_without_test[0].lower() + name_without_test[1:]
        if inferred_name in src_declared_methods and inferred_name not in IGNORE_METHODS:
            target_mut_names.add(inferred_name)

    # ==========================================
    # 汇总并拼接结果
    # ==========================================
    if not target_mut_names:
        return None, None

    combined_codes = []
    combined_comments = []

    for mut_name in target_mut_names:
        # 确保方法确实存在于源码声明中
        if mut_name in src_declared_methods:
            # 假设 src_declared_methods[mut_name] 是一个列表，取第一个元素 [0]
            mut_info = src_declared_methods[mut_name][0]

            # 提取代码并添加标记以便区分
            if "code" in mut_info and mut_info["code"]:
                combined_codes.append(f"// --- Method: {mut_name} ---\n{mut_info['code']}")

            # 提取注释并添加标记以便区分
            if "comments" in mut_info and mut_info["comments"]:
                combined_comments.append(f"// --- Comments for: {mut_name} ---\n{mut_info['comments']}")

    # 如果拼接后有内容，用换行符连接；否则返回 None
    final_code = "\n\n".join(combined_codes) if combined_codes else None
    final_comments = "\n\n".join(combined_comments) if combined_comments else None

    # 如果虽然找到了名字，但是字典里没有代码/注释，也返回 None
    if not final_code and not final_comments:
        return None, None

    return final_code, final_comments


# ================= 主流程 =================

def main():
    # 【保障点3】断点重跑机制完全未动，绝对安全
    processed_signatures = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        processed_signatures.add(json.loads(line)["fullyQualifiedSignature"])
                    except:
                        pass
        print(f"[*] 检测到断点：已跳过 {len(processed_signatures)} 个历史用例。")

    if not os.path.exists(INPUT_FILE):
        print(f"[!] 找不到文件: {INPUT_FILE}")
        return

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        tasks = json.load(f)

    # 批次写入计数器
    write_count = 0

    with open(OUTPUT_FILE, 'a', encoding='utf-8') as out_f:
        for idx, task in enumerate(tasks):
            signature = task.get("fullyQualifiedSignature", "")
            project_url = task.get("project", "")
            raw_filepath = task.get("filePath", "")

            if signature in processed_signatures:
                # 默默跳过已处理的，不打印日志防止刷屏
                continue

            print(f"[{idx + 1}/{len(tasks)}] 处理: {signature}")

            test_method_name = signature.split('.')[-1].replace('()', '')
            owner, repo = get_owner_repo(project_url)

            if not owner or not repo:
                print("    -> [跳过] 提取仓库所有者失败。")
                continue

            # 处理像你给的例子里自带 repo 前缀的 filepath 路径
            prefix = f"{owner}/{repo}/"
            clean_test_filepath = raw_filepath if not raw_filepath.startswith(prefix) else raw_filepath[len(prefix):]

            branch = get_default_branch(owner, repo)
            if not branch:
                continue

            # --- A. 获取测试代码 (走缓存) ---
            test_code_full = get_cached_raw_file(owner, repo, branch, clean_test_filepath)
            test_method_node, test_code_snippet = extract_test_method_ast(test_code_full, test_method_name)

            mut_code, mut_comments = None, None

            # --- B. 获取被测源码 (走缓存) ---
            clean_src_filepath = infer_source_filepath(clean_test_filepath)
            src_code_full = get_cached_raw_file(owner, repo, branch, clean_src_filepath)

            if src_code_full and test_method_node:
                # 源码的缓存 Key 就是其绝对路径
                src_cache_key = f"{owner}/{repo}/{branch}/{clean_src_filepath}"
                # --- C. 轻量级多级策略解析被测源码 (AST也走缓存) ---
                src_declared_methods = get_cached_declared_methods(src_code_full, src_cache_key)
                mut_code, mut_comments = analyze_mut_strategies(
                    test_method_node, src_declared_methods, test_method_name
                )

            # --- D. 构建结果 ---
            result = {
                "fullyQualifiedSignature": signature,
                "test_method_code": test_code_snippet,
                "target_method_code": mut_code,
                "target_method_comments": mut_comments
            }

            out_f.write(json.dumps(result, ensure_ascii=False) + "\n")
            write_count += 1

            # 【优化点2】批次 Flush，极大提升硬盘写入效率
            if write_count % BATCH_SIZE == 0:
                out_f.flush()
                print(f"    [磁盘 I/O] -> 已同步积攒的 {BATCH_SIZE} 条数据入盘...")

            if test_code_snippet:
                print(f"    -> 提取状态: 测试代码[√] | 被测业务代码[{'√' if mut_code else 'X'}]")
            else:
                print(f"    -> [失败] 未能在文件中找到该测试方法")

        # 循环结束，把最后不足 50 条的剩余尾巴数据强制刷入磁盘
        out_f.flush()

    print(f"\n[+] 全部处理完毕！最终结果已保存为 {OUTPUT_FILE}")


if __name__ == "__main__":
    main()