import os

os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"

from crewai import Agent
from crewai import LLM
from tools.code_search import CodeSearchTool, SearchJavaCodeTool


# llm = LLM(
#     model='qwen3-coder-next',
#     api_key=os.environ["DASHSCOPE_API_KEY"],
#     base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
#     temperature=0,
#     max_tokens=8192
# )
# Default: ARK_API_KEY, base https://ark.cn-beijing.volces.com/api/coding/v3, model DeepSeek-V3.2.
# Override: AIGC_API_KEY. AIGC_BASE_URL defaults to https://api2.aigcbest.top
# (a bare host is sent as {host}/v1). AIGC_MODEL overrides the model id.
def _resolve_llm_endpoint():
    aigc_key = os.environ.get("AIGC_API_KEY", "").strip()
    if aigc_key:
        base_url = os.environ.get("AIGC_BASE_URL", "").strip() or "https://api2.aigcbest.top"
        base_url = base_url.rstrip("/")
        if base_url.count("/") == 2:
            base_url = base_url + "/v1"
        model = os.environ.get("AIGC_MODEL", "").strip() or "DeepSeek-V3.2"
        # the proxy speaks the OpenAI protocol; CrewAI picks its client from the prefix
        return "openai/" + model, aigc_key, base_url
    return (
        "DeepSeek-V3.2",
        os.environ["ARK_API_KEY"],
        "https://ark.cn-beijing.volces.com/api/coding/v3",
    )


_model, _api_key, _base_url = _resolve_llm_endpoint()
llm = LLM(
    model=_model,
    api_key=_api_key,
    base_url=_base_url,
    temperature=0,
    max_tokens=8192
)







def create_test_architect():
    return Agent(
        role="Test Architect",
        goal="""
            Unit testing of the entire system is difficult, as you need to break it down into several functional modules. 
            Each functional module contains several features, and each feature contains several methods. 
            They have dependencies and work together to complete a set of functional requirements. 
            The partitioned features will serve as the smallest unit of work, and testers will generate unit tests for all methods in a feature each time, ensuring that each feature is independent and contains sufficient contextual information. 
            Output the divided functional modules as the test plan.
        """,
        backstory="A testing architect who excels in breaking down the entire project and specifying testing plans based on the principle of high cohesion and low coupling.",
        llm=llm
    )


def create_test_designer():
    return Agent(
        role="Test Designer",
        goal="Design comprehensive unit test cases based on requirement descriptions, which are described in text form and do not rely on programming languages.",
        backstory="An experienced software testing engineer designs diverse and sufficient test cases for each functional requirement in the requirements document.",
        llm=llm
    )


def create_test_development_engineer():
    return Agent(
        role="Test Development Engineer",
        goal="Develop text unit test cases into automated code, using Junit or UnitTest frameworks to ensure that the code is compiled correctly, and use a range of tools to assist you in coding.",
        backstory="Experienced test and development engineer, skilled in developing test cases into test code based on text test cases and project code structures written by testers, proficient in Junit and UnitTest frameworks.",
        llm=llm,
        max_iter=10,
        cache=True,  # 开启缓存，避免重复调用相同的工具
        allow_delegation=False

    )

def create_test_reviewer():
    return Agent(
        role="Test Reviewer",
        goal="Review test case designs to ensure they meet quality standards, completeness, and correctness. Provide constructive feedback for improvement.",
        backstory="""
        You are a senior test quality assurance engineer with extensive experience in test case review and quality control.
        You have been working in software testing for many years, specializing in reviewing test case designs,
        identifying gaps in test coverage, ensuring test cases align with requirements, and providing actionable feedback
        to improve test case quality. You are meticulous, detail-oriented, and focus on ensuring test cases are
        comprehensive, well-structured, and follow best practices.
        """,
        llm=llm
    )


def create_test_debugger():
    return Agent(
        role="Test Debugger",
        goal="Run test cases, provide test reports, and provide effective feedback for test cases that fail to run.",
        backstory="""
        You are a senior testing and debugging engineer with years of experience in software testing and debugging 
        You have been working in complex systems and high reliability software projects for a long time, 
        familiar with the complete process from unit testing to system testing, especially skilled in executing test cases, 
        analyzing failure reasons, locating defect root causes, and structuring the results into reproducible and traceable test reports.
        """,
        llm=llm
    )

def create_mr_parser():
    return Agent(
        role="Metamorphic Relation Architect",
        goal="Analyze requirement specifications and source code signatures to discover, define, and formalize high-confidence Metamorphic Relations (MRs) that verify system behavior without requiring a specific test oracle.",
        backstory="""
        You are a distinguished Software Test Architect specializing in 'Test Oracle Construction' and formal logic. While traditional testers ask "What is the correct result for input X?", you ask "If I change input X to Y, how exactly should the result change?"

        You possess a unique ability to map abstract business rules to mathematical and logical properties, such as:
        1.  **Monotonicity**: "If the tax rate increases, the total cost must non-decrease."
        2.  **Symmetry/Permutation**: "Sorting a list [A, B] should yield the same result as sorting [B, A]."
        3.  **Idempotency**: "Converting the same CSV to JSON twice should result in identical JSON strings."
        4.  **Additivity**: "The audio volume of (Track A + Track B) should not exceed the sum of their individual volumes."

        Your primary objective is to solve the 'Oracle Problem.' You view the software under test as a black box with invariant behaviors. You do not write the final Python code, but you provide the strict logical blueprints (Source Input -> Follow-up Input -> Output Relation) that the coding agents will implement.
        """,
        llm=llm

    )

def create_context_retriever():
    return Agent(
        role="Code Context Retrieval Specialist",
        goal="Analyze the provided test case specification (JSON format) and retrieve all necessary code context from the codebase, including the focal method and all mocked dependencies.",
        backstory="""
            Your job is to read the test case JSON, extract the `focal_method` and all `mocks` targets, 
            and use your search tools to find the actual source code definitions for all of them. 
            You gather the exact implementation of the SUT and the signatures/class definitions of the mocks, 
            providing the full context needed for a developer or an AI to write the actual test code later.
        """,
        llm=llm,
        cache=False,
        max_iter=2,
        max_reasoning_attempts=2

    )


def create_summary():
    return Agent(
        role="Code Context Retrieval Specialist",
        goal="Analyze the provided test case specification (JSON format) and retrieve all necessary code context from the codebase, including the focal method and all mocked dependencies.",
        backstory="""
            You are an expert Software Development Engineer in Test (SDET) and a master of static code analysis. 
            You know that a test specification outlines not just the System Under Test (SUT), but also its dependencies 
            (mocks, observables, custom types). 
            Your job is to read the test case JSON, extract the `focal_method` and all `mocks` targets, 
            and use your search tools to find the actual source code definitions for all of them. 
            You gather the exact implementation of the SUT and the signatures/class definitions of the mocks, 
            providing the full context needed for a developer or an AI to write the actual test code later.
        """,
        llm=llm,
        max_iter=1,
        max_reasoning_attempts=2

    )

if __name__ == '__main__':
    print(os.environ.get("MODEL"))
    print(os.environ.get("API_KEY"))
    print(os.environ.get("BASE_URL"))
    print(os.environ.get("DATASET_ROOT"))


