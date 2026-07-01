#!/usr/bin/env python
# main.py
import logging
import sys

from agent_wo_two import TestAgentAppWOT
from agent_wone import TestAgentAppWONE
from utils.logger import DualOutput, setup_logging
from agent import TestAgentApp

# 步骤缩写说明:
#   P = Plan      测试计划
#   D = Design    测试设计
#   C = Context   代码上下文提取
#   X = eXecute   测试开发 + 修复循环
#   G = debuG     运行 & 分析测试报告

log = logging.getLogger("mate")


def run_single_wo_two(dataset_name: str, steps=None, stream=True, debug=False, exp=True,
                      verbose=False, mr=True):
    app = TestAgentAppWOT(
        dataset_name=dataset_name,
        steps=steps,
        stream=stream,
        debug=debug,
        max_retries=3,
        exp=exp,
    )
    app.run(verbose=verbose, mr=mr)


def run_single(dataset_name: str, steps=None, stream=True, debug=False, exp=True,
               verbose=False, mr=True):
    app = TestAgentApp(
        dataset_name=dataset_name,
        steps=steps or {1, 2, 3, 4, 5},
        stream=stream,
        debug=debug,
        max_retries=3,
        exp=exp,
    )
    app.run(verbose=verbose, mr=mr)


def run_single_wo_one(dataset_name: str, steps=None, stream=True, debug=False, exp=True,
                      verbose=False, mr=True):
    app = TestAgentAppWONE(
        dataset_name=dataset_name,
        steps=steps or {1, 2, 3, 4, 5},
        stream=stream,
        debug=debug,
        max_retries=3,
        exp=exp,
    )
    app.run(verbose=verbose, mr=mr)


def run_batch_wo_tw(dataset_list: list, steps=None, stream=True, debug=False, exp=True,
                    verbose=False, mr=True):
    total = len(dataset_list)
    succeeded, failed = [], []
    for i, name in enumerate(dataset_list, 1):
        log.info(f"[Batch] ({i}/{total}) Starting dataset: {name}")
        try:
            run_single_wo_two(name, steps=steps, stream=stream, debug=debug,
                              exp=exp, verbose=verbose, mr=mr)
            succeeded.append(name)
            log.info(f"[Batch] ({i}/{total}) Completed: {name}")
        except Exception:
            failed.append(name)
            log.exception(f"[Batch] ({i}/{total}) Failed: {name}")

    log.info(f"[Batch] Done. {len(succeeded)}/{total} succeeded, {len(failed)} failed.")
    if failed:
        log.info(f"[Batch] Failed datasets: {failed}")


def run_batch(dataset_list: list, steps=None, stream=True, debug=False, exp=True,
              verbose=False, mr=True):
    total = len(dataset_list)
    succeeded, failed = [], []
    for i, name in enumerate(dataset_list, 1):
        log.info(f"[Batch] ({i}/{total}) Starting dataset: {name}")
        try:
            run_single(name, steps=steps, stream=stream, debug=debug,
                       exp=exp, verbose=verbose, mr=mr)
            succeeded.append(name)
            log.info(f"[Batch] ({i}/{total}) Completed: {name}")
        except Exception:
            failed.append(name)
            log.exception(f"[Batch] ({i}/{total}) Failed: {name}")

    log.info(f"[Batch] Done. {len(succeeded)}/{total} succeeded, {len(failed)} failed.")
    if failed:
        log.info(f"[Batch] Failed datasets: {failed}")


def run_batch_wo_one(dataset_list: list, steps=None, stream=True, debug=False, exp=True,
                     verbose=False, mr=True):
    total = len(dataset_list)
    succeeded, failed = [], []
    for i, name in enumerate(dataset_list, 1):
        log.info(f"[Batch] ({i}/{total}) Starting dataset: {name}")
        try:
            run_single_wo_one(name, steps=steps, stream=stream, debug=debug,
                              exp=exp, verbose=verbose, mr=mr)
            succeeded.append(name)
            log.info(f"[Batch] ({i}/{total}) Completed: {name}")
        except Exception:
            failed.append(name)
            log.exception(f"[Batch] ({i}/{total}) Failed: {name}")

    log.info(f"[Batch] Done. {len(succeeded)}/{total} succeeded, {len(failed)} failed.")
    if failed:
        log.info(f"[Batch] Failed datasets: {failed}")


# available dataset
"""
DevEval/java:
    "idcenter"
    "java_heap"
    "redis-cache"
    "Actor_relationship_game"

PT/java
   
    libraryManagement
    "CalculatorOOPS",
    "passwordGenerator",
    "PongGame",

devEval/python
     "readtime",
            "hone",
            "lice",
            "chakin",
            "ArXiv_digest",
            "geotext",
            "particle-swarm-optimization"

PT/python
    "fuzzywuzzy",
    "stock2",
    "stock4",  
    "structly",  
    "tree",
"""

if __name__ == "__main__":
    setup_logging()
    """
        devEval / python
        "readtime",
        "hone",
        "lice",
        "chakin",
        "ArXiv_digest",
        "geotext",
        "particle-swarm-optimization"

    PT / python
    "fuzzywuzzy",
    "stock2",
    "stock4",
    "structly",
    "tree",
    """

    # 批量运行
    # run_batch(
    #     dataset_list=[
    #         "readtime",
    #         "hone",
    #     ],
    #     steps={1, 2, 3, 4},
    #     mr=False,
    #     exp=True
    # )

    # --- 单个数据集运行 ---

    run_single(
        dataset_name='PongGame',
        steps={ 4 },
        mr=False,
        debug=False,
        exp=True
    )
    # 消融实验，没有测试计划
    # run_batch_wo_one(
    #     dataset_list=[
    #          "java_heap",
    #          "redis-cache",
    #          "Actor_relationship_game",
    #     ],
    #     steps={1, 2, 3, 4},
    #     mr=False,
    #     exp=True
    # )

    # run_single_wo_one(
    #     dataset_name='idcenter',
    #     steps={1,2,3,4},
    #     mr=False,
    #     debug=True,
    #     exp=True
    # )



    # 消融实验，没有两阶段
    # run_single_wo_two(
    #     dataset_name='PongGame',
    #     steps={1,2,3,4},
    #     mr=True,
    #     debug=True,
    #     exp=True
    # )

    # run_batch_wo_tw(
    #     dataset_list=[
    #
    #         "Actor_relationship_game"
    #     ],
    #     steps={1,2,3,4},
    #     mr=True,
    #     exp=True
    # )
