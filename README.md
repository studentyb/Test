# Test(CMATG)

CMATG generates unit tests for a whole project from its requirement and design documents. Several LLM agents (built on CrewAI) split the project into features, derive metamorphic relations (MRs) for each feature, design test cases, write the test code, run it and repair it. Python (pytest) and Java (Maven or Gradle, JUnit 5) projects are supported.

This folder contains the source code only. It does not contain datasets, baseline tools, experiment outputs or run logs. The datasets are described in [Datasets](#datasets), with where to put each one.

## Contents

```
Test(CMATG)/
|-- README.md
|-- TestAgent/                  the CMATG pipeline
|   |-- main.py                 minimal entry point
|   |-- agent.py                TestAgentApp: the six-step pipeline
|   |-- agents/agents.py        agent definitions and the LLM endpoint
|   |-- piplines/core.py        one prompt template -> one CrewAI task
|   |-- prompt/                 Jinja2 templates, one folder per stage
|   |-- rag/                    vector store code for the MR library
|   |-- experience/             repair-experience summarisation and retrieval
|   |-- tools/, utils/          code search, test runners, parsers, token ledger
|   |-- debug/, line_tracer/    Java line tracer used for failure analysis
|   |-- generation/, ta.py      method-level and code-agent variants (RQ4)
|   |-- eval/                   HumanEval+ loading and output comparison scripts
|   |-- data_process/           scripts that built the MR corpus and the documents
|   `-- memory/                 working memory (cleared per run) and long-term memory

```

## How CMATG works

`TestAgentApp.run()` in `TestAgent/agent.py` runs these steps:

1. **Load the inputs.** `utils/dataset_utils.load_dataset` reads `config.json` of the project and the four documents it names: requirements (SRS), UML class diagram, UML sequence diagram and architecture design.
2. **Test plan** (once per project, `prompt/test_plan/test_plan.md`). The Test Architect splits the project into modules and features; each feature lists its methods and requirements. The output is `memory/working_memory/test_plan.json`. Later steps see only the summary of one feature.
3. **MR lifecycle** (per feature, `prompt/mr_parse/`). Three similar MRs are retrieved from the MR library by BGE-M3 embedding. The MR Parser generates MRs for the feature, a reviewer labels each MR Valid, Risky or Invalid, and a fix step rewrites them. This repeats until no MR is Invalid or Risky, or until `max_review_iterations` is reached; at the limit the current MRs are kept.
4. **Test design** (per feature, `prompt/test_design/test_design.md`). The Test Designer writes test cases that use the MRs where possible and exact expected values otherwise. Output: `ts_<feature>.json`.
5. **Code context** (per feature). The LLM names the classes and methods it needs; `tools/grep.py` returns their full source with tree-sitter.
6. **Develop, run and repair** (per feature, `prompt/test_development/`). The Test Development Engineer writes the test file, which is then run. On a failure the experience store is searched first; after that up to `max_retries` LLM repairs follow (`self_fix.md`). Successful and failed repairs are summarised into the experience store. Generated tests are moved to a quarantine folder between features and restored at the end.

`TestAgentApp.DEBUG_RUN` selects which steps run. `{1, 2, 4, 6}` runs the full pipeline.

Behaviour to be aware of:

- The repair loop treats assertion failures as results, not as errors. Python: only collection, setup and non-assertion runtime errors trigger a repair. Java: a run whose only failures are `AssertionFailedError` counts as successful. `self_fix.md` forbids changing test inputs or assertions.
- The class diagram is read in step 1 but is not passed to test design, development or repair.
- The review of abstract test cases (`prompt/test_review/`) is present but disabled in `agent.py`.

## Requirements

- Python 3.12. The pipeline was run with:
  - crewai 0.165.1 and crewai-tools 0.62.3
  - chromadb 1.5.9
  - sentence-transformers 4.1.0 and torch 2.7.0
  - openai 1.99.9 and litellm 1.74.9
  - Jinja2 3.1.6, pydantic 2.11.4, tree-sitter 0.26.1
  - pytest 8.4.1, pytest-json-report, pytest-cov
- Java projects: a JDK and Maven or Gradle on `PATH`.
- The BGE-M3 embedding model ([BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3)), about 2.2 GB, placed in `TestAgent/rag/models/bge-m3`.
- An OpenAI-compatible chat endpoint. Temperature is 0 and `max_tokens` is 8192 (`agents/agents.py`).

crewai-tools 0.62.3 declares chromadb 0.5.23, but chromadb 1.5.9 is needed to open the library built by `build_mr_db.py`. Install chromadb 1.5.9 after crewai-tools.

## Setup

1. Install the packages above.
2. Download BGE-M3 into `TestAgent/rag/models/bge-m3`.
3. Put the MR corpus files in place (see [MR corpus](#mr-corpus)): `TestAgent/rag/MRs.jsonl` and `TestAgent/data_process/mr_process/MTC_Dataset.json`.
4. Build the MR library (about 15 minutes on CPU):

   ```bash
   python scripts/build_mr_db.py
   ```

   This writes `TestAgent/rag/mr_chroma_db` and `TestAgent/rag/mr_chroma_db.manifest.json`. It stores every record of `rag/MRs.jsonl` that carries an MR sentence, and leaves out records whose test comes from a repository that is also an evaluation subject (`EXCLUDE_PROJECTS` in the script; the repository is looked up in `MTC_Dataset.json`). Use `--db` and `--model` to choose other locations.

5. Set the environment variables.
6. Prepare the projects to test (see [Datasets](#datasets)).

## Environment variables

Never put key values into source files.

| Variable | Used by | Meaning |
|---|---|---|
| `AIGC_API_KEY` | `agents/agents.py`, `utils/chat.py` | Key of an OpenAI-compatible endpoint. When it is set, it overrides the defaults below. |
| `AIGC_BASE_URL` | same | Base URL of that endpoint. A bare host is sent as `<host>/v1`. |
| `AIGC_MODEL` | same | Model id, e.g. `deepseek-ai/DeepSeek-V3.2`. |
| `ARK_API_KEY` | `agents/agents.py` | Default endpoint (Volcano Ark, DeepSeek-V3.2) when `AIGC_API_KEY` is not set. |
| `DASHSCOPE_API_KEY` | `utils/chat.py` | Default endpoint for direct calls (experience summaries, code-context selection) when `AIGC_API_KEY` is not set. |
| `DATASET_ROOT` | `utils/dataset_utils.py` | Folder that holds the projects. |
| `CMATG_DB_PATH`, `CMATG_MODEL_PATH` | `rag/db_instance.py` | MR library and embedding model. Defaults: `rag/mr_chroma_db`, `rag/models/bge-m3`. |
| `CMATG_MAX_FEATURES` | `agent.py` | Run only the first N planned features; `0` or unset runs all. |
| `CMATG_LTM_READONLY` | `rag/core.py` | `1`: retrieve repair experience but do not write it back. |
| `CMATG_LEDGER` | `utils/token_ledger.py` | Token ledger file. Default: `memory/token_ledger.jsonl`. |
| `DEEPSEEK_API_KEY` | `data_process/mr_process/Mr_reverse.py` | Only for rebuilding the MR library from scratch. |
| `GITHUB_PAT` | `data_process/mr_process/mr_download_fast.py` | Only for rebuilding the MR library from scratch. |

`scripts/run_cmatg.py` sets `DATASET_ROOT`, the `CMATG_*` variables and `AIGC_BASE_URL` / `AIGC_MODEL` from its arguments.

## Project layout and `config.json`

Each project is one folder under `DATASET_ROOT`:

```
DATASET_ROOT/
|-- project1/
|   |-- config.json
|   |-- docs/          the four documents
|   |-- src/           Python: code under test
|   `-- tests/         Python: generated tests are written here
`-- project2/          Java
    |-- config.json
    |-- docs/
    |-- pom.xml or build.gradle
    `-- src/main/java  (tests go to src/test/java)
```

```json
{
  "language": "python",
  "srs": "docs/SRS.md",
  "uml_class": "docs/uml_class.md",
  "uml_sequence": "docs/uml_sequence.md",
  "architecture_design": "docs/ADD.md",
  "sut_root": "src"
}
```

For Java, `sut_root` is `src/main/java` and `language` is `java`. The build tool is detected from `pom.xml` or `build.gradle`. Python projects should have a `pytest.ini` with `pythonpath = .` and `testpaths = tests`.

Remove existing tests from the project before a run. CMATG writes into the project folder.

## Running

### One project, with artefacts collected

```bash
python scripts/run_cmatg.py --dataset_root <DATASET_ROOT> --project <name> \
    --model deepseek-ai/DeepSeek-V3.2 --base_url <endpoint> \
    --max_review_iterations 3 --max_retries 3
```

The API key is read from `AIGC_API_KEY`. Options:

| Option | Default | Meaning |
|---|---|---|
| `--max_review_iterations` | 3 | MR review rounds per feature. `agent.py` alone defaults to 1. |
| `--max_retries` | 3 | LLM repair attempts per test file. |
| `--max_features` | 0 | First N planned features; 0 runs all. |
| `--no_mr` | off | Ablation: no MR lifecycle; test design without MRs. |
| `--no_review`, `--no_refine` | off | Ablation: skip MR review and fixing, or review once without fixing. |
| `--no_exp` | off | Do not retrieve repair experience. |
| `--ltm_readonly` | off | Retrieve experience but do not write it back. |
| `--test_python_dir` | none | Folder put first on `PATH`, so generated tests run with that Python. |
| `--mr_db`, `--embedding_model` | under `TestAgent/rag/` | Library and model locations. |

`TestAgent/memory/working_memory` is cleared at the start of every run. Use one copy of `TestAgent` per concurrent run.

Each run writes `runs/<slice>/<project>/`:

- `console.log`
- `token_ledger.jsonl`: one row per LLM stage. Counters are cumulative per stage, so take differences of consecutive rows of the same stage to get the usage of one call; a counter that goes down starts a new call.
- `working_memory/`: test plan, MRs (retrieved, initial, per review round, final), test designs, code context, repair records
- `tests/` or `src/test/java/`: the generated tests
- `run_meta.json`: settings, status, wall time, tokens per stage, size of the MR library and of the experience store

The runner also removes per-chunk `usage` objects from streamed responses. Some OpenAI-compatible proxies attach `usage` to every chunk, and CrewAI then drops the content. Totals are unchanged.

### Without the runner

```bash
cd TestAgent
python main.py
```

`main.py` runs `TestAgentApp(dataset_name=...)` on a project of `DATASET_ROOT` with the settings written in the file. Set the environment variables yourself.

### Code-agent variant 

```bash
cd TestAgent
python ta.py --sut_root <path> --dataset_root <path> --feature <name> --l <java|python> --build <maven|gradle> --put "<requirement>"
```

This runs `Test4CA` in `generation/agent_with_ca.py`. It analyses and debugs existing tests for one requirement. `ta_client.py` calls it through a subprocess.

## Datasets

This section describes each dataset, how CMATG uses it and where its files go.

| Dataset | Role | Where it goes |
|---|---|---|
| DevEval | evaluation subjects (Python, Java) | one project per folder under `DATASET_ROOT` |
| ProjectTest | evaluation subjects (Python, Java) | one project per folder under `DATASET_ROOT` |
| TrickyBugs | bug-detection evaluation | `problems/` anywhere; adapted with `benchmarks/trickybugs/` |
| MR corpus | source of the MR library (step 3) | `TestAgent/rag/`, `TestAgent/data_process/mr_process/` |
| HumanEval+ | `eval/` scripts only | `TestAgent/eval/dataset/` |

### DevEval

DevEval (Li et al., *Prompting Large Language Models to Tackle the Full Software Development Lifecycle: A Case Study*; [open-compass/DevEval](https://github.com/open-compass/DevEval)) is a repository-level benchmark that covers the software development lifecycle. Its repositories span algorithms, databases, web services, APIs, NLP and computer vision, and each has a multi-file structure. Each repository comes with a product requirement document, a UML class diagram, a UML sequence diagram and an architecture design, which match the four inputs CMATG reads.

To use a DevEval repository with CMATG, place it under `DATASET_ROOT`, add a `config.json` that points to the four documents, and remove its tests. The documents used in our experiments were rewritten into the four-document form and are not the original DevEval files.

### ProjectTest

ProjectTest (Wang et al., *ProjectTest: A Project-level LLM Unit Test Generation Benchmark and Impact of Error Fixing Mechanisms*, arXiv:2502.06556) is a project-level unit-test generation benchmark. Its projects come from GitHub. Each has 2 to 15 source files and at most about 1,600 lines of code, so it has cross-file dependencies and still fits in a model's context.

ProjectTest projects have no requirement documents. The four documents were reverse-engineered from the source code with the prompts in `data_process/prompt.md`: an SRS with `[CodeRef:]` links, an architecture design and a PlantUML sequence diagram. The input to those prompts is the merged non-test source produced by `data_process/gen_tree.py`. `prompt.md` has no prompt for the class diagram. Place each project under `DATASET_ROOT` with a `config.json`, as for DevEval.

### TrickyBugs

[TrickyBugs](https://doi.org/10.5281/zenodo.7977255) is a dataset of corner-case bugs in plausible programs. Its 324 AtCoder tasks contain human-written buggy programs in C++, Java and Python. For some tasks it also has fixed versions, reference programs and the original test cases. See *TrickyBugs: A Dataset of Corner-case Bugs in Plausible Programs* (DOI 10.1145/3597926.3598060). Download the repository and `problems.tar.gz` as its README describes, and unpack `problems/`.

Each TrickyBugs task is a single program that reads standard input, so `benchmarks/trickybugs/` adapts it to the project layout CMATG expects.

**Subset.** `subset_140.json` lists 140 task ids, 78 Python and 62 Java, with the file names of one buggy program and the fixed program of the same name. It holds no program text. The adapter currently handles Python only.

**Adapter.** `adapt_trickybugs.py` uses fixed templates. It calls no model and does not read the program text.

```bash
python benchmarks/trickybugs/adapt_trickybugs.py --problems <TrickyBugs>/problems --out benchmarks/trickybugs/inputs
```

It writes, per task:

- `docs/SRS.md`: `problem_description.txt` verbatim, followed by a fixed interface section;
- template class diagram, sequence diagram and architecture design;
- `src/solution.py`: `solve(stdin_text) -> str`, which runs the program in a subprocess with a 20-second limit and returns standard output with leading and trailing whitespace removed;
- `src/program.py`: the buggy program, byte for byte;
- `config.json`, `pytest.ini`, an empty `tests/`, and `adapter_meta.json` (program names and hashes).

The fixed program is not copied, so CMATG never sees it.

**Generating tests.**

```bash
python scripts/run_cmatg.py --dataset_root benchmarks/trickybugs/inputs --project p02547 --slice trickybugs_python \
    --max_review_iterations 3 --no_exp --ltm_readonly
```

Run one task at a time and clear `tests/` of the task before a rerun.

**Scoring.** `score_trickybugs_cmatg.py` runs each generated suite twice in scratch copies: once as adapted (buggy program) and once with `src/program.py` replaced by the fixed program.

```bash
python benchmarks/trickybugs/score_trickybugs_cmatg.py --problems <TrickyBugs>/problems \
    --inputs benchmarks/trickybugs/inputs --runs runs/trickybugs_python --out scores
```

| Level | Label | Meaning |
|---|---|---|
| Test | valid | passes with the fixed program |
| Test | detecting | valid, and does not pass with the buggy program |
| Test | invalid | does not pass with the fixed program; a file pytest cannot collect counts as invalid |
| Task | TP | at least one detecting test |
| Task | FP | no detecting test, but an invalid test fails on the buggy program |
| Task | FN | otherwise |

Recall is TP / tasks and precision is TP / (TP + FP). The scorer writes `labels.csv`, `summary.json` and one JSON file per task.

**Add-on stages (optional).** `improve_addon.py` is a prototype outside the CMATG pipeline. It reads the requirements and the final MRs of a finished CMATG run and makes three model calls per task. None of them sees the program.

1. A generator of valid inputs, `gen_inputs.py`, written from the constraints in the problem statement.
2. `test_mr_random.py`: each final MR run on 40 generated inputs instead of one hand-written input.
3. A naive reference implementation, `reference.py`, compared with the program on 100 small generated inputs (`test_reference_diff.py`, a fixed template).

```bash
python benchmarks/trickybugs/improve_addon.py --runs runs/trickybugs_python --out runs_addon \
    --inputs benchmarks/trickybugs/inputs
```

The script writes three variants: `v1_only`, `v2_only`, and `cmatg_plus_both` (the CMATG tests plus all add-on tests). Each can be scored with the scorer above. The reference comparison is differential testing, not metamorphic testing; report it separately from the MR tests.

### MR corpus

The MR library that step 3 queries is built from metamorphic test cases mined by MR-Scout (Xu et al., *MR-Scout: Automated Synthesis of Metamorphic Relations from Existing Test Cases*, TOSEM 2024): about 11,000 test cases that encode metamorphic relations, from more than 700 open-source Java projects on GitHub. Each record has the fully qualified signature of the test, the test method code, the method under test, its comments and a one-sentence MR.

The scripts in `data_process/mr_process/` built the corpus:

1. `MTC_Dataset.json`: the list of test cases (signature, project URL, file path).
2. `mr_download_fast.py` (`GITHUB_PAT`) downloads the test and target method code into `MRs.jsonl`, without MR sentences.
3. `Mr_reverse.py` (`DEEPSEEK_API_KEY`, deepseek-reasoner) writes the MR sentence for each test.

Files expected by this code:

| File | Used by | Content |
|---|---|---|
| `TestAgent/rag/MRs.jsonl` | `scripts/build_mr_db.py` | records with an MR sentence (4,314 in our library) |
| `TestAgent/data_process/mr_process/MTC_Dataset.json` | `scripts/build_mr_db.py` | signature -> project URL, used for the overlap exclusion |

`scripts/build_mr_db.py` embeds the MR sentences with BGE-M3 into the Chroma collection `mr_semantic_collection` (cosine). Repair experience is stored in `mr_experience_collection` of the same database and starts empty.

### HumanEval+

HumanEval+ (EvalPlus, Liu et al., NeurIPS 2023; [evalplus/evalplus](https://github.com/evalplus/evalplus)) extends the HumanEval function-level tasks with many more test inputs. Only the scripts in `eval/` read it. They expect `TestAgent/eval/dataset/HumanEvalPlus.jsonl` and program-under-test variants in `TestAgent/eval/dataset/PUTs/<task_id>/put<N>.py`. The main pipeline does not need these files.



