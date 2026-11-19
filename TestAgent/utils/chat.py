import datetime
import os

from openai import OpenAI


def _chat_client_settings(model):
    # Default: DASHSCOPE_API_KEY, base https://dashscope.aliyuncs.com/compatible-mode/v1.
    # Override: AIGC_API_KEY. AIGC_BASE_URL defaults to https://api2.aigcbest.top
    # (a bare host is sent as {host}/v1). AIGC_MODEL replaces the model argument.
    aigc_key = os.environ.get("AIGC_API_KEY", "").strip()
    if aigc_key:
        base_url = os.environ.get("AIGC_BASE_URL", "").strip() or "https://api2.aigcbest.top"
        base_url = base_url.rstrip("/")
        if base_url.count("/") == 2:
            base_url = base_url + "/v1"
        override = os.environ.get("AIGC_MODEL", "").strip()
        if override:
            model = override
        return aigc_key, base_url, model
    return os.environ["DASHSCOPE_API_KEY"], "https://dashscope.aliyuncs.com/compatible-mode/v1", model


def get_ai_response(prompt, model="qwen3-coder-next", temperature=0):
    """
    调用 OpenAI API 获取回复的通用函数
    """
    api_key, base_url, model = _chat_client_settings(model)
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        )

    try:
        # 2. 发起请求
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一个乐于助人的 AI 助手。"},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=4096,
        )

        try:
            from utils.token_ledger import write_row
            u = response.usage
            write_row(os.environ.get("CMATG_AUX_STAGE", "aux_direct_call"),
                      getattr(u, "prompt_tokens", None), getattr(u, "completion_tokens", None), requests=1)
        except Exception:
            pass
        # 3. 解析并返回文本内容
        return response.choices[0].message.content

    except Exception as e:
        return f"发生错误: {e}"



if __name__ == '__main__':

    res=get_ai_response("你是谁")
    print(res)
