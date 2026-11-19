import json
import os
import re
from pathlib import Path

import tree_sitter_java as tsjava
import tree_sitter_python as tspython
from jinja2 import Template
from tree_sitter import Language, Parser

from utils.chat import get_ai_response
from utils.file_utils import read_file

_JAVA_LANG = Language(tsjava.language())
_PYTHON_LANG = Language(tspython.language())

_LANG_CONFIG = {
    "java": {
        "language": _JAVA_LANG,
        "ext": ".java",
        "comment": "//",
        "class_nodes": {"class_declaration", "interface_declaration", "enum_declaration"},
        "method_nodes": {"method_declaration", "constructor_declaration"},
    },
    "python": {
        "language": _PYTHON_LANG,
        "ext": ".py",
        "comment": "#",
        "class_nodes": {"class_definition"},
        "method_nodes": {"function_definition"},
    },
}


def search_definition_ast(
        root_dir: str,
        query: str,
        search_type: str,
        language: str = "java",
        ignore_case: bool = True,
) -> str:
    lang_key = language.strip().lower()
    cfg = _LANG_CONFIG.get(lang_key)
    if cfg is None:
        return f"Error: Unsupported language '{language}'. Supported: {list(_LANG_CONFIG)}"

    parser = Parser(cfg["language"])
    comment = cfg["comment"]
    ext = cfg["ext"]

    if search_type == "class":
        target_node_types = cfg["class_nodes"]
    elif search_type in ("method", "function"):
        target_node_types = cfg["method_nodes"]
    else:
        return f"Error: Unsupported search_type '{search_type}'"

    found_results = []

    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if not filename.endswith(ext):
                continue

            filepath = os.path.join(dirpath, filename)

            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    source_bytes = f.read().encode('utf-8')
            except Exception as e:
                print(f"Warning: Failed to read {filepath}: {e}")
                continue

            tree = parser.parse(source_bytes)

            stack = [tree.root_node]
            while stack:
                node = stack.pop()

                if node.type in target_node_types:
                    name_node = node.child_by_field_name('name')

                    if name_node:
                        node_name = name_node.text.decode('utf-8')

                        if ignore_case:
                            matched = (node_name.lower() == query.lower())
                        else:
                            matched = (node_name == query)

                        if matched:
                            code_snippet = source_bytes[node.start_byte:node.end_byte].decode('utf-8')

                            # 统一路径格式为正斜杠
                            normalized_path = filepath.replace('\\', '/')

                            # 提取类名（含包名）或 Python 模块名
                            class_name = ""
                            if language == "java":
                                if '/main/java/' in normalized_path:
                                    class_part = normalized_path.split('/main/java/')[-1]
                                    class_name = class_part.replace('.java', '').replace('/', '.')
                                elif '/src/' in normalized_path:
                                    class_part = normalized_path.split('/src/')[-1]
                                    class_name = class_part.replace('.java', '').replace('/', '.')
                                else:
                                    class_name = normalized_path.replace('.java', '').replace('/', '.')
                            elif language == "python":
                                if '/main/python/' in normalized_path:
                                    module_part = normalized_path.split('/main/python/')[-1]
                                    class_name = module_part.replace('.py', '').replace('/', '.')
                                elif '/src/main/' in normalized_path:
                                    module_part = normalized_path.split('/src/main/')[-1]
                                    class_name = module_part.replace('.py', '').replace('/', '.')
                                elif '/src/' in normalized_path:
                                    module_part = normalized_path.split('/src/')[-1]
                                    class_name = module_part.replace('.py', '').replace('/', '.')
                                else:
                                    class_name = normalized_path.replace('.py', '').replace('/', '.')

                            # 提取方法名（仅针对方法声明）
                            method_name = ""
                            if node.type in {"method_declaration", "function_definition", "constructor_declaration"}:
                                code_lines = code_snippet.split('\n')
                                for line in code_lines:
                                    line_stripped = line.strip()
                                    if not line_stripped or line_stripped.startswith(comment):
                                        continue
                                    # 匹配: ReturnType methodName( 或 def methodName(
                                    match = re.search(r'[\w<>\[\]]+\s+(\w+)\s*\(', line_stripped)
                                    if match:
                                        method_name = match.group(1)
                                        break

                            # 直接生成格式化结果
                            formatted_lines = [
                                f"{comment} File: {filepath}",
                                f"{comment} AST Type: {node.type}"
                            ]
                            if class_name:
                                formatted_lines.append(f"{comment} Class: {class_name}")
                            if method_name:
                                formatted_lines.append(f"{comment} Method: {method_name}")
                            formatted_lines.append(code_snippet)
                            formatted_lines.append("-" * 50)

                            found_results.append('\n'.join(formatted_lines))

                for child in node.children:
                    stack.append(child)

    if not found_results:
        return f"Could not find any {search_type} matching '{query}' in {root_dir}."

    return "\n\n".join(found_results)


def search_java_definition_ast(root_dir: str, query: str, search_type: str, ignore_case: bool = True) -> str:
    return search_definition_ast(root_dir, query, search_type, language="java", ignore_case=ignore_case)


def parse_and_execute_tools(llm_output: str, root_dir: str, language: str = "java") -> str:
    """解析 LLM 输出的 JSON，并循环调用 AST 检索函数，最终拼接为上下文返回"""
    print("\n=================== 解析 LLM 输出 ===================")

    json_match = re.search(r'\[.*\]', llm_output, re.DOTALL)
    if not json_match:
        print(f"❌ 无法从输出中提取 JSON:\n{llm_output}")
        return ""

    cleaned_json = json_match.group(0)

    try:
        search_tasks = json.loads(cleaned_json)
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失败: {e}\n原文:\n{cleaned_json}")
        return ""

    print(f"✅ 成功解析出 {len(search_tasks)} 个检索任务。\n")

    collected_code = []

    for task in search_tasks:
        query = task.get("query")
        search_type = task.get("search_type")

        if not query or not search_type:
            continue

        print(f"🔍 [AST 检索中] -> 类型: {search_type.upper():<6} | 目标: {query}")

        result_code = search_definition_ast(
            root_dir=root_dir,
            query=query,
            search_type=search_type,
            language=language,
        )

        collected_code.append(
            f"{result_code}\n"
        )
        print("   ✅ 检索完成。")

    return "\n".join(collected_code)


def get_code_context(project_root: str, test_case_input: str, language: str = "java", uml_class: str = '') -> str:
    template = Template(read_file(Path('prompt/test_development/code_retrieval.md')))
    prompt = template.render({"test_case_input": test_case_input, "language": language, "uml_class": uml_class})
    llm_decision = get_ai_response(prompt)
    print(llm_decision)
    return parse_and_execute_tools(llm_decision, project_root, language=language)


if __name__ == '__main__':
    PROJECT_ROOT = "/home/mgh/dev/data/dataset/DevEval/python/readtime/src"
    res = get_code_context(PROJECT_ROOT, test_case_input=read_file('memory/working_memory/ts_html_entry_point.json'),
                           language="python")
    print(res)
