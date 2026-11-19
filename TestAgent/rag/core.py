import os
import re
import uuid

import chromadb
import torch
from sentence_transformers import SentenceTransformer


class MRVectorStore:
    def __init__(self, db_path="./chroma_db", model_path="rag/models/bge-m3"):
        # --- 1. 模型加载 (仅在初始化时执行一次) ---
        print(f"🚀 正在加载本地 BGE 模型: {model_path} ...")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = SentenceTransformer(model_path, device=device)
        print(f"✅ 模型已就绪 (运行设备: {device})")

        # --- 2. 连接数据库 ---
        self.chroma_client = chromadb.PersistentClient(path=db_path)

        # 语义/意图集合
        self.semantic_collection = self.chroma_client.get_or_create_collection(
            name="mr_semantic_collection", metadata={"hnsw:space": "cosine"}
        )
        # 代码结构集合
        self.code_collection = self.chroma_client.get_or_create_collection(
            name="mr_code_collection", metadata={"hnsw:space": "cosine"}
        )
        # 经验总结集合 (包含成功与失败案例)
        self.experience_collection = self.chroma_client.get_or_create_collection(
            name="mr_experience_collection", metadata={"hnsw:space": "cosine"}
        )

    # --- 原有功能：数据处理与通用检索 ---

    def process_jsonl_and_store(self, jsonl_file_path: str, mode="semantic"):
        """处理 JSONL 文件并批量存入数据库"""
        # 这里仅作逻辑示例，实际需根据你的 JSONL 结构解析
        print(f"正在处理文件: {jsonl_file_path} ...")
        # 示例：解析后调用 self.semantic_collection.add(...)
        pass

    def search(self, query: str, top_k: int = 3, mode: str = "semantic"):
        """执行通用检索 (语义或代码模式)"""
        target_collection = self.code_collection if mode == "code" else self.semantic_collection

        query_embedding = self.model.encode(query, normalize_embeddings=True).tolist()

        results = target_collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )
        return self._format_results(results)

    def _format_results(self, results):
        """格式化输出通用搜索结果"""
        if not results['ids'] or len(results['ids'][0]) == 0:
            return []

        parsed_results = []
        for i in range(len(results['ids'][0])):
            item = {
                "id": results['ids'][0][i],
                "content": results['documents'][0][i],
                "metadata": results['metadatas'][0][i],
                "similarity": 1 - results['distances'][0][i]
            }
            parsed_results.append(item)
        return parsed_results

    # --- 核心功能：经验库存储与检索 (已重写) ---

    def add_experience(self, error_type, error_log, scenario, is_successful, solution):
        """
        存储修复经验
        :param is_successful: True 为成功修复，False 为尝试失败
        :param solution: 成功时的修复方法 或 失败时的尝试方法
        """
        # 任务隔离：允许检索，禁止把本次基准任务的经验写回。
        if os.environ.get("CMATG_LTM_READONLY") == "1":
            print(f"ltm readonly: skip add_experience {error_type}")
            return
        # 组合 Log 和 Scenario 形成唯一指纹
        document_content = f"Error Type: {error_type}\nLog: {error_log}\nScenario: {scenario}"

        embedding = self.model.encode(document_content, normalize_embeddings=True).tolist()

        metadata = {
            "error_type": error_type,
            "is_successful": is_successful,
            "solution": solution
        }

        # 使用 upsert 确保 ID 重复时自动更新
        self.experience_collection.upsert(
            embeddings=[embedding],
            documents=[document_content],
            metadatas=[metadata],
            ids=[f"exp_{uuid.uuid4()}"]
        )
        status = "✅ 成功" if is_successful else "❌ 失败"
        print(f"已录入记录 [{status}] {error_type}")

    def search_experience(self, query_log, query_scenario, error_type=None, top_k=2, only_success=False):
        """
        经验专属检索
        :param only_success: True 则只返回修好的方案
        """
        query_text = f"Log: {query_log}\nScenario: {query_scenario}"
        query_embedding = self.model.encode(query_text, normalize_embeddings=True).tolist()

        # 构造过滤条件
        filters = []
        if error_type:
            filters.append({"error_type": {"$eq": error_type}})
        if only_success:
            filters.append({"is_successful": {"$eq": True}})

        where_clause = None
        if len(filters) > 1:
            where_clause = {"$and": filters}
        elif len(filters) == 1:
            where_clause = filters[0]

        results = self.experience_collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_clause,
            include=["documents", "metadatas", "distances"]
        )

        # 格式化经验输出
        if not results['ids'] or len(results['ids'][0]) == 0:
            return []

        formatted_exps = []
        for i in range(len(results['ids'][0])):
            meta = results['metadatas'][0][i]
            # 提取对应的 document 内容
            doc = results['documents'][0][i]

            formatted_exps.append({
                "is_successful": meta['is_successful'],
                "solution": meta['solution'],
                "document": doc,  # 将 document 添加到返回结果字典中
                "similarity": 1 - results['distances'][0][i]
            })
        return formatted_exps



# ==========================================
# 1. 签名解析函数 (保持不变)
# ==========================================
def extract_class_and_method(signature: str) -> str:
    sig_no_params = signature.split('(')[0]
    parts = sig_no_params.split('.')
    if len(parts) < 2: return signature
    class_name = parts[-2]
    method_name = parts[-1]
    class_name_clean = re.sub(r'Test$', '', class_name, flags=re.IGNORECASE)
    class_name_clean = re.sub(r'^Test', '', class_name_clean, flags=re.IGNORECASE)
    method_name_clean = re.sub(r'^test', '', method_name)
    if method_name_clean:
        method_name_clean = method_name_clean[0].upper() + method_name_clean[1:]
    return f"{class_name_clean} {method_name_clean}"


