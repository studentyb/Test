from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class TestCaseResult:
    """单个测试用例的运行结果"""
    class_name: str
    test_name: str
    status: str  # "PASSED", "FAILED", "ERROR", "SKIPPED"
    error_type: Optional[str] = None
    message: Optional[str] = None


@dataclass
class TestRunResult:
    """整体测试运行的结果封装"""
    success: bool
    build_failed: bool = False
    error_msg: str = ""
    test_cases: List[TestCaseResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
