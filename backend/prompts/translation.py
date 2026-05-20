TRANSLATE_SYSTEM_PROMPT = """你是一个专业的翻译专家。你的任务是将以下句子翻译成{target_language}。

规则：
1. 翻译要准确、自然、符合{target_language}的表达习惯。
2. 保留原文的标点风格和语气。
3. 严格以 JSON 数组格式输出，不要包含 markdown 标记或任何其他文字。"""

TRANSLATE_USER_PROMPT = """以下是一些需要翻译的句子：

{sentences_json}

请将每个句子翻译成{target_language}，输出 JSON 数组。每个元素包含以下字段：
- index: 整数，与原句子的 index 对应
- translated_text: 字符串，翻译后的文本"""


def get_translate_system_prompt(target_language: str = "中文") -> str:
    return TRANSLATE_SYSTEM_PROMPT.format(target_language=target_language)


def get_translate_user_prompt(sentences_json: str, target_language: str = "中文") -> str:
    return TRANSLATE_USER_PROMPT.format(sentences_json=sentences_json, target_language=target_language)
