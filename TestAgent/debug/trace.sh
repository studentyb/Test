#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT=${1:?"用法: $0 <项目路径> <被测类> <被测方法> <测试类#方法>"}
CLASS=${2:?"缺少被测类名"}
METHOD=${3:?"缺少被测方法名"}
TEST=${4:?"缺少测试方法 (如 com.example.MyTest#testXxx)"}

# 编译
if [ ! -f "$SCRIPT_DIR/target/line-tracer-1.0-SNAPSHOT.jar" ]; then
    echo "📦 首次运行，编译 LineTracer..."
    mvn -f "$SCRIPT_DIR/pom.xml" package -q -DskipTests
fi

java --add-modules jdk.jdi \
     -jar "$SCRIPT_DIR/target/line-tracer-1.0-SNAPSHOT.jar" \
     --project "$PROJECT" \
     --class "$CLASS" \
     --method "$METHOD" \
     --test "$TEST" \
     --verbose
