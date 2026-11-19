import torch
from sentence_transformers import SentenceTransformer
import time

MODEL_PATH = "./models/bge-m3"   # 改成你的实际路径

def main():
    print("==== 环境检测 ====")
    print("Torch version:", torch.__version__)
    print("CUDA available:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("GPU:", torch.cuda.get_device_name(0))
        print("CUDA version:", torch.version.cuda)
    else:
        print("⚠️ 当前是 CPU 模式")

    print("\n==== 加载模型 ====")
    device = "cuda" if torch.cuda.is_available() else "cpu"

    model = SentenceTransformer(
        MODEL_PATH,
        device=device,
        model_kwargs={"torch_dtype": torch.float16} if device == "cuda" else {}
    )

    print("模型已加载到设备:", device)

    texts = [
        "Lifts a function to Option",
        "如果输入函数是恒等函数，lift 后的 Option 应保持不变",
        "public <A, B> Function<Option<A>, Option<B>> lift(Function<A, B> f) { ... }"
    ]

    print("\n==== 开始向量化 ====")
    t0 = time.time()
    embeddings = model.encode(
        texts,
        batch_size=8,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True
    )
    t1 = time.time()

    print("向量化完成 ✅")
    print("Embedding shape:", embeddings.shape)
    print("耗时:", round(t1 - t0, 3), "秒")

    print("\n==== 取第一条向量前 5 维 ====")
    print(embeddings[0][:5])


if __name__ == "__main__":
    main()