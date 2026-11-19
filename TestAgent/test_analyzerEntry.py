#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试运行和调试分析入口
直接配置变量运行，无需命令行参数
"""

import json
from pathlib import Path
from generation.agent_with_cc import Test4CA

# ===================================================================
# 配置区域 - 修改以下参数
# ===================================================================

# 被测代码 (SUT) 根目录
SUT_ROOT = r"D:\BJFU\TestAgent\dataset\RQ4\workdir\Actor_relationship_game\src\main\java"  # Java 项目示例
# SUT_ROOT = r"D:\path\to\src"  # Python 项目示例

# 项目根目录（包含 pom.xml/build.gradle 或 pytest.ini）
# 默认与 SUT_ROOT 相同，如果不同请单独指定
DATASET_ROOT = r"D:\BJFU\TestAgent\dataset\RQ4\workdir\Actor_relationship_game"

# 项目语言: 'java' 或 'python'
LANGUAGE = "java"

# Java 构建工具: 'maven' 或 'gradle'（仅 Java 项目需要）
BUILD = "gradle"

# 功能名称（用于报告标识）
FEATURE = "all_tests"

# 报告输出路径
OUTPUT_PATH = r"output\debug_report.json"

# 调试模式（打印详细日志）
DEBUG = True

# LLM 流式输出
STREAM = True

# ===================================================================
# 执行区域
# ===================================================================


def run_test_analyzer():
    print(f"{'=' * 60}")
    print(f"Test Execution & Debug Analyzer")
    print(f"{'=' * 60}")
    print(f"Language:     {LANGUAGE}")
    print(f"Build Tool:   {BUILD}")
    print(f"SUT Root:      {SUT_ROOT}")
    print(f"Dataset Root:  {DATASET_ROOT}")
    print(f"Feature:       {FEATURE}")
    print(f"{'=' * 60}")

    try:
        # 初始化分析器
        analyzer = Test4CA(
            build=BUILD,
            sut_root=SUT_ROOT,
            dataset_root=DATASET_ROOT,
            put="",
            language=LANGUAGE,
            feature=FEATURE,
            verbose=False,
            debug=DEBUG,
            stream=STREAM,
        )

        # 运行测试分析
        print("\n[INFO] Running tests...")
        report = analyzer.run()

        if report:
            # 保存报告
            output_path = Path(OUTPUT_PATH)
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

            return report
        else:
            print("Error: No report generated")
            return None

    except Exception as e:
        return None


if __name__ == "__main__":
    run_test_analyzer()
