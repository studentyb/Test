import ast
import os
import importlib.util
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class CodeContext:
    file_path: str = ""
    import_statements: List[str] = field(default_factory=list)
    sut_type: str = "function"  # function, method, static_method, class_method
    sut_signature: str = ""
    parent_class: Optional[str] = None
    class_init_signature: Optional[str] = None  # 如果是实例方法，需要__init__
    return_type_hint: Optional[str] = None
    return_class_definition: Optional[str] = None  # 返回值类的简要定义


class CodeContextBuilder:
    def __init__(self, project_root: str):
        self.project_root = os.path.abspath(project_root)

    def build_context(self, target_module: str, target_name: str) -> Dict[str, Any]:
        """
        构建代码上下文。
        :param target_module: 模块路径，例如 "readtime.api"
        :param target_name: 函数/类名，例如 "of_text" 或 "ReadTime.of_text"
        """
        context = CodeContext()

        # 1. 定位文件路径
        file_path = self._resolve_file_path(target_module)
        if not file_path:
            return {"error": f"Module {target_module} not found"}
        context.file_path = file_path

        # 2. 解析 AST
        with open(file_path, "r", encoding="utf-8") as f:
            source_code = f.read()
        tree = ast.parse(source_code)

        # 3. 提取 Imports
        context.import_statements = self._extract_imports(tree)

        # 4. 查找目标定义 (SUT)
        target_node = self._find_definition(tree, target_name)

        if target_node:
            context.sut_signature = self._get_signature(target_node, source_code)

            if isinstance(target_node, ast.FunctionDef):
                # 检查是否在类中 (这一步简化处理，假设输入 target_name 包含了类名信息如果是在类中)
                # 如果 target_name 是 "ClassName.method_name"，我们需要特殊处理
                if "." in target_name:
                    class_name, method_name = target_name.split(".")
                    class_node = self._find_definition(tree, class_name)
                    if isinstance(class_node, ast.ClassDef):
                        context.parent_class = class_name
                        self._analyze_method_type(target_node, context, class_node, source_code)
                else:
                    context.sut_type = "function"

            # 5. 提取返回值类型信息
            if target_node.returns:
                # 获取返回值类型注解的名称
                return_type = self._get_annotation_name(target_node.returns)
                context.return_type_hint = return_type

                # 尝试在当前文件或导入中寻找该类的定义
                # (这里简化为只在当前项目根目录下搜索该类定义)
                return_def = self._find_class_definition_global(return_type)
                if return_def:
                    context.return_class_definition = return_def

        return context.__dict__

    def _resolve_file_path(self, module_name: str) -> Optional[str]:
        # 简单映射：module.a.b -> root/module/a/b.py
        relative_path = module_name.replace(".", os.sep) + ".py"
        full_path = os.path.join(self.project_root, relative_path)

        # 处理 __init__.py 的情况
        if not os.path.exists(full_path):
            package_path = os.path.join(self.project_root, module_name.replace(".", os.sep), "__init__.py")
            if os.path.exists(package_path):
                return package_path

        return full_path if os.path.exists(full_path) else None

    def _extract_imports(self, tree: ast.AST) -> List[str]:
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(f"import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = ", ".join([n.name for n in node.names])
                level = "." * node.level
                imports.append(f"from {level}{module} import {names}")
        return imports

    def _find_definition(self, tree: ast.AST, name: str) -> Optional[ast.AST]:
        # 支持 "func" 或 "Class.method"
        search_parts = name.split(".")

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == search_parts[0]:
                if len(search_parts) == 1:
                    return node
                # 如果是 Class.method，继续深入
                elif isinstance(node, ast.ClassDef):
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name == search_parts[1]:
                            return item
        return None

    def _analyze_method_type(self, method_node: ast.FunctionDef, context: CodeContext, class_node: ast.ClassDef,
                             source: str):
        is_static = False
        is_class = False
        for decorator in method_node.decorator_list:
            if isinstance(decorator, ast.Name):
                if decorator.id == 'staticmethod': is_static = True
                if decorator.id == 'classmethod': is_class = True

        if is_static:
            context.sut_type = "static_method"
        elif is_class:
            context.sut_type = "class_method"
        else:
            context.sut_type = "method"  # 实例方法
            # 提取 __init__ 用于实例化
            for item in class_node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    context.class_init_signature = self._get_signature(item, source)
                    break

    def _get_signature(self, node: ast.AST, source: str) -> str:
        # 使用 ast.get_source_segment 获取源码片段 (Python 3.8+)
        # 简单起见，这里只提取 def ... : 这一行
        lines = source.splitlines()
        start = node.lineno - 1
        # 简单拼接，实际可能跨行
        return lines[start].strip()

    def _get_annotation_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Str):  # Forward reference "Result"
            return node.s
        return "Unknown"

    def _find_class_definition_global(self, class_name: str) -> Optional[str]:
        # 在整个项目目录搜索该类的定义文件
        # 这只是一个极其简化的搜索，实际项目可能需要索引
        for root, dirs, files in os.walk(self.project_root):
            for file in files:
                if file.endswith(".py"):
                    path = os.path.join(root, file)
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            tree = ast.parse(f.read())
                        for node in tree.body:
                            if isinstance(node, ast.ClassDef) and node.name == class_name:
                                # 找到类定义，提取类名和属性/方法名作为上下文
                                props = [n.targets[0].id for n in node.body if isinstance(n, ast.Assign)]
                                methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                                return f"class {class_name}: Properties={props}, Methods={methods}"
                    except:
                        continue
        return None


# ---------- 模拟使用 ----------
if __name__ == "__main__":



    try:
        builder = CodeContextBuilder(project_root="/home/mgh/dev/data/dataset/DevEval/python/readtime/src")

        # 模拟：我们想为 readtime.api.of_text 生成测试
        # 输入信息来自 Feature: module="readtime.api", method="of_text"
        ctx = builder.build_context("result", "seconds")

        import json

        print(json.dumps(ctx, indent=2))

    except Exception as e:
        print(e)


