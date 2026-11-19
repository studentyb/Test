#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试运行和调试分析入口脚本
运行被测项目的现有测试用例，分析失败测试，生成调试报告
"""

import argparse
import json
import sys
from pathlib import Path

# 智能导入，适配不同的项目结构
try:
    from generation.agent_with_cc import Test4CA
except ImportError:
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from generation.agent_with_cc import Test4CA
    except ImportError:
        print("Error: Cannot import Test4CA. Please ensure the file exists.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='运行现有测试并生成调试报告',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # Java Maven 项目
  python test_analyzer.py --sut_root ./src/main/java --dataset_root ./ --language java --build maven

  # Java Gradle 项目
  python test_analyzer.py --sut_root ./src/main/java --dataset_root ./ --language java --build gradle

  # Python 项目
  python test_analyzer.py --sut_root ./src --dataset_root ./ --language python

  # 指定输出路径
  python test_analyzer.py --sut_root ./src/main/java --language java --output output/report.json
        """
    )

    parser.add_argument('--sut_root', type=str, required=True,
                        help='被测代码 (SUT) 根目录')
    parser.add_argument('--dataset_root', type=str, default=None,
                        help='项目根目录（包含 pom.xml/build.gradle 或 pytest.ini，默认与 sut_root 相同）')
    parser.add_argument('--language', type=str, default='java', choices=['java', 'python'],
                        help='项目语言: java 或 python')
    parser.add_argument('--build', type=str, default='maven', choices=['maven', 'gradle'],
                        help='Java 构建工具: maven 或 gradle（仅 Java）')
    parser.add_argument('--feature', type=str, default='all_tests',
                        help='功能名称（用于报告标识，默认: all_tests）')
    parser.add_argument('--output', type=str, default='output/debug_report.json',
                        help='报告输出路径（默认: output/debug_report.json）')
    parser.add_argument('--debug', action='store_true',
                        help='启用调试模式，打印详细日志')
    parser.add_argument('--no_stream', action='store_true',
                        help='禁用 LLM 流式输出')

    args = parser.parse_args()

    print(f"{'=' * 60}")
    print(f"Test Execution & Debug Analyzer")
    print(f"{'=' * 60}")
    print(f"Language:     {args.language}")
    print(f"Build Tool:   {args.build}")
    print(f"SUT Root:      {args.sut_root}")
    print(f"Dataset Root:  {args.dataset_root or args.sut_root}")
    print(f"Feature:       {args.feature}")
    print(f"{'=' * 60}")

    try:
        # 初始化分析器
        analyzer = Test4CA(
            build=args.build,
            sut_root=args.sut_root,
            dataset_root=args.dataset_root,
            put="",
            language=args.language,
            feature=args.feature,
            verbose=False,
            debug=args.debug,
            stream=not args.no_stream,
        )

        # 运行测试分析
        print("\n[INFO] Running tests...")
        report = analyzer.run()

        if report:
            # 保存报告
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)

            # 打印摘要
            print(f"\n{'=' * 60}")
            print(f"Report saved to: {output_path}")
            print(f"{'=' * 60}")
            print(f"\nSummary:")
            print(f"  Overall Pass Rate: {report.get('overall_pass_rate', 'N/A')}")
            print(f"  Summary: {report.get('summary', 'N/A')}")

            test_results = report.get('test_results', [])
            passed = sum(1 for t in test_results if t.get('status') == 'PASSED')
            failed = sum(1 for t in test_results if t.get('status') == 'SUT_BUG')

            print(f"  Total Tests: {len(test_results)}")
            print(f"  Passed: {passed}")
            print(f"  SUT Bugs: {failed}")

            # 打印失败的测试详情
            sut_bugs = [t for t in test_results if t.get('status') == 'SUT_BUG']
            if sut_bugs:
                print(f"\n  Failed Tests Details:")
                for bug in sut_bugs:
                    print(f"    - {bug.get('test_name', 'Unknown')}: {bug.get('reason', 'No reason')[:100]}")

            return 0
        else:
            print("Error: No report generated")
            return 1

    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 130
    except Exception as e:
        print(f"Error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
