# set env
```shell
export MODEL="your-model-name"
export OPENAI_API_KEY="your-api-key"
export OPENAI_BASE_URL="https://api.example.com"
```

# 下载向量化模型
[bge-large-en-v1.5](https://huggingface.co/BAAI/bge-large-en-v1.5/tree/main)

下载的模型文件放到 rag/models 目录下

# 从 YAML 创建环境
conda env create -f environment.yaml

# 设置数据集
export DATASET_ROOT="/path/to/dataset/DevEval/python"

数据集目录示例
```text
目录结构
java
DATASET_ROOT
    |--project1
    |   |--docs
    |   |--src
    |--project2

python
DATASET_ROOT
    |--project1
    |   |--docs
    |   |--src
    |--project2

```


## 可用数据集
- DevEval
  - python
    - readtime
    - hone
    - lice
    - chakin
    - ArXiv_digest
    - geotext
    - particle-swarm-optimization
  - java
    - idcenter
    - java_heap
    - redis-cache
    - Actor_relationship_game
- ProjectTest
  - python
    -  "fuzzywuzzy"
    - "stock2"
    - "stock4" 
    - "structly"
    - "tree"
  - java
    -  libraryManagement
    - "CalculatorOOPS"
    - "passwordGenerator"
    - "PongGame"
    
    
# 运行程序
修改 main.py

```shell
python main.py
```
```python
# ---  ---
"""
    单个数据集运行

    :param dataset_name: 数据集名称
    :param mr: boolean 是否使用蜕变关系，用于消融实验
    :param debug: 打印详细日志
    :param exp: 是否使用经验，用于消融实验
    """
run_single(
        dataset_name='readtime',
        steps={1, 2, 3, 4, 5},
        mr=False,
        debug=True,
        exp=True
)

```

## 运行消融实验，没有两阶段
在main.py 取消对下面的代码的注释
```python
    # 消融实验，没有两阶段
    run_single_wo_two(
        dataset_name='structly',
        steps={1,2,3,4,5},
        mr=True,
        debug=True,
        exp=True
    )
```

## 运行消融实验，没有测试计划
在main.py 取消对下面的代码的注释
```python

    run_single_wo_one(
        dataset_name='readtime',
        steps={1,2,3,4},
        mr=False,
        debug=True,
        exp=True
    )
```
# 查看测试结果
生成的测试用例位于 $DATASET_ROOT/dataset_name/tests(python)

$DATASET_ROOT/dataset_name/src/test/java(java)

# 统计测试结果
```shell
python run_all_tests.py
```

```shell

watch -n1 cat .mate_progress
# 运行测试
pytest
# 查看覆盖
pytest --cov=.

pytest --cov=<被测代码目录> <测试代码目录> --cov-branch

```



