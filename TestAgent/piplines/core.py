import os

os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"

from crewai import Task, Crew
from jinja2 import Template


class PipelineStep:

    def __init__(
        self,
        *,
        agent,
        template_text: str,
        expected_output: str,
        output_file: str,
        verbose: bool,
        stream: bool = True,
        debug: bool = False,
        stage=None,
    ):
        self.agent = agent
        self.template_text = template_text
        self.expected_output = expected_output
        self.output_file = output_file
        self.verbose = verbose
        # 是否使用大模型流式输出
        self.stream = stream
        self.debug = debug
        self.stage = stage

    def run(self, **kwargs):

        template = Template(self.template_text)
        description = template.render(**kwargs)
        if self.debug:
            print('=====================LLM Input=========================')
            print(description)
        task = Task(
            description=description,
            expected_output=self.expected_output,
            agent=self.agent,
            output_file=self.output_file
        )

        crew = Crew(agents=[self.agent], tasks=[task], verbose=self.verbose, stream=self.stream, tracing=False)

        from utils.token_ledger import llm_counters, record_delta
        import time as _time
        llm = getattr(self.agent, "llm", None)
        before, started = llm_counters(llm), _time.time()
        streaming_output = crew.kickoff()
        stage = self.stage or "unlabelled"
        is_stream = (
            hasattr(streaming_output, "__iter__")
            and not isinstance(streaming_output, (str, bytes, dict))
            and not hasattr(streaming_output, "raw")
        )
        if not is_stream:
            record_delta(stage, llm, before, started, streaming_output)
            return streaming_output

        class _Recorded:
            """Iterates the stream, records usage when it ends, and still exposes .result."""

            def __init__(self, inner):
                self._inner = inner

            def __iter__(self):
                try:
                    for chunk in self._inner:
                        yield chunk
                finally:
                    record_delta(stage, llm, before, started, self._inner)

            def __getattr__(self, name):
                return getattr(self._inner, name)

        return _Recorded(streaming_output)
