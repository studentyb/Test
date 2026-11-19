#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import shutil
import sys
from pathlib import Path

from generation.agent_with_ca import Test4CA

uml_class = """
@startuml class_diagram
title Hone — Class Diagram

class Hone {
  .. Class Attributes ..
  + {static} DEFAULT_DELIMITERS : list = [",", "_", " "]

  .. Instance Attributes ..
  + delimiters : list
  + csv_filepath : str | None
  + csv : CSVUtils

  .. Public Methods ..
  + __init__(delimiters: list = DEFAULT_DELIMITERS)
  + convert(csv_filepath: str, schema: dict = None) : list
  + get_schema(csv_filepath: str) : dict
  + generate_full_structure(column_names: list) : dict
  + get_nested_structure(parent_structure: dict) : dict
  + populate_structure_with_data(structure: dict, column_names: list, data_rows: list) : list
  + get_leaves(structure: dict, path: str = "", result: dict = {}) : dict
  + get_valid_splits(column_name: str) : list
  + get_split_suffix(split: str, column_name: str = "") : str
  + clean_split(split: str) : str
  + is_valid_prefix(prefix: str, base: str) : bool
  + set_csv_filepath(csv_filepath: str) : None
  + escape_quotes(string: str) : str
}

class CSVUtils {
  .. Instance Attributes ..
  + filepath : str | None

  .. Public Methods ..
  + __init__(csv_filepath: str)
  + get_column_names() : list
  + get_data_rows() : list
  + open_csv(mode: str = 'r', newline: str = '') : contextmanager
}

package "json_utils (module)" as json_utils_pkg {
  class "<<module>> json_utils" as json_utils {
    + {static} output_json(json_struct, json_filepath: str) : None
  }
}

package "test_utils (module)" as test_utils_pkg {
  class "<<module>> test_utils" as test_utils {
    + {static} parse_json_file(json_filepath: str) : object
    + {static} parse_csv_file(csv_filepath: str) : list
  }
}

Hone "1" *-- "1" CSVUtils : csv (composition)
Hone ..> json_utils : <<optional usage>>

note bottom of Hone
  Primary class under test.
  Encapsulates all conversion logic.
end note

note bottom of CSVUtils
  CSV I/O component.
  Accessed via Hone.csv attribute.
end note

@enduml
"""




def main():
    parser = argparse.ArgumentParser(description='test agent命令行参数')

    parser.add_argument('--build', type=str, default='maven',
                        help='构建工具 (maven/gradle)')
    parser.add_argument('--sut_root', type=str, required=True,
                        help='被测代码根目录')
    parser.add_argument('--dataset_root', type=str, default=None,
                        help='项目根目录（pom.xml/build.gradle 所在目录，默认与 sut_root 相同）')
    parser.add_argument('--put', type=str, default=None,
                        help='被测代码、需求描述等prompt（直接传字符串）')
    parser.add_argument('--put_file', type=str, default=None,
                        help='被测代码文件路径（与 --put 二选一，优先级更高，推荐大段代码使用）')
    parser.add_argument('--l', type=str, default='java',
                        help='语言 java/python')
    parser.add_argument('--feature', type=str, required=True,
                        help='被测功能')
    parser.add_argument('--debug', action='store_true',
                        help='为 true 时打印流式 chunk 内容')
    parser.add_argument('--no_stream', action='store_true',
                        help='为 true 时禁用大模型流式输出（改为一次性返回）')
    parser.add_argument('--no_exp', action='store_true',
                        help='禁用经验检索与复用')
    parser.add_argument('--max_retries', type=int, default=3,
                        help='最大修复轮次（默认 3）')
    parser.add_argument('--report_path', type=str, default=None,
                        help='测试报告 JSON 输出路径（默认写入 output/test_report_<feature>.json）')

    parser.add_argument('--uml_class', type=str, default=None,
                        help='类图')
    put = """
    "signature": "def add(a,b):->int ",
    "semantic": "计算两个数的和"

        """

    # args = [
    #     '--build', 'maven',
    #     '--sut_root', r'D:\BJFU\TestAgent\dataset\RQ4\workdir\hone\src',
    #     '--dataset_root',r'D:\BJFU\TestAgent\dataset\RQ4\workdir\hone',
    #     '--put', put,
    #     '--l', 'python',
    #     '--feature', 'utils_test',
    #     '--debug',
    #     '--max_retries', '3',
    #     '--report_path', r'D:/BJFU/TestAgent/output/test_report_user_register.json',
    #     '--uml_class', uml_class
    # ]
    args = parser.parse_args()

    # --put_file 优先；其次 --put；都没有则用内置 example
    if args.put_file:
        put = Path(args.put_file).read_text(encoding='utf-8')
    elif args.put:
        put = args.put
    else:
        put = None

    app = Test4CA(
        build=args.build,
        sut_root=args.sut_root,
        dataset_root=args.dataset_root,
        put=put,
        language=args.l,
        feature=args.feature,
        verbose=False,
        debug=args.debug,
        stream=not args.no_stream,
        exp=not args.no_exp,
        max_retries=args.max_retries,
        # todo
        uml_class=args.uml_class
    )
    app.run()

    if args.report_path:
        report_path = Path(args.report_path)
        source_path = Path(f"memory/working_memory/debug_report_{args.feature}.json")
        if source_path.exists():
            report_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, report_path)
        else:
            print(f"Warning: Source file {source_path} does not exist")


if __name__ == "__main__":
    main()
"""
通过feature判断是否为同一个被测功能


每测试完一个，就转存测试

测试修复只修非assert

"""
