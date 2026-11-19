# db_instance.py
from rag.core import MRVectorStore

# 这里指定你的模型和数据库实际路径
import os
DB_PATH = os.environ.get("CMATG_DB_PATH", "rag/mr_chroma_db")
MODEL_PATH = os.environ.get("CMATG_MODEL_PATH", "rag/models/bge-m3")

# 全局单例对象
print("--- 初始化系统全局变量 ---")
vector_db = MRVectorStore(db_path=DB_PATH, model_path=MODEL_PATH)