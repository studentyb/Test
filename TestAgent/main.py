#!/usr/bin/env python
# src/research_crew/main.py
import sys
import argparse


from utils.logger import DualOutput

from agent import TestAgentApp

# dataset_root
"""
project test:/home/mgh/dev/data/dataset/PT/JAVA

dev eval=/home/mgh/dev/data/dataset/DevEval/python

"""


# available dataset
"""
DevEval/java:
idcenter
java_heap
redis-cache
Actor_relationship_game

PT/java
bankingApplication
libraryManagement

python
readtime
hone


"""

if __name__ == "__main__":

# 环境变量指定数据集根目录
    app = TestAgentApp(dataset_name='libraryManagement', stream=True,debug=False,exp=False)
    app.run(verbose=False, mr=False)


