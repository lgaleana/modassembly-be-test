from functools import lru_cache

import tiktoken

encoding = None


@lru_cache(maxsize=1000)
def count_tokens(content: str, model: str = "gpt-4o") -> int:
    global encoding
    if encoding is None:
        encoding = tiktoken.encoding_for_model(model)
    count = len(encoding.encode(str(content)))
    return count