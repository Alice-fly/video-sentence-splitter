SEGMENT_SYSTEM_PROMPT = """你是一个专业的字幕处理专家。你的任务是将视频字幕文本按语义重组成完整的句子。

原文语言：{source_language}。请据此正确理解原文语义。

规则：
1. 根据语义将原文断句，每个句子必须语义完整、自然通顺。
2. 为原文添加适当的标点符号（句号、逗号、问号等），使文本可读。
3. start_time 取该句第一个字幕条目的开始时间，end_time 取最后一个的结束时间。
4. 时间精度保留到毫秒（三位小数）。
5. 严格以 JSON 数组格式输出，不要包含 markdown 标记或任何其他文字。"""

SEGMENT_USER_PROMPT = """以下是视频字幕的原始条目列表，每一条包含开始时间(秒)、结束时间(秒)和文本：

{subtitle_entries_json}

请将上述字幕条目按语义重组成完整的句子，输出 JSON 数组。每个元素包含以下字段：
- index: 整数，从1开始的序号
- original_text: 字符串，带标点的完整原文句子
- start_time: 浮点数，句子起始时间(秒)
- end_time: 浮点数，句子结束时间(秒)"""


def _lang_label(code: str) -> str:
    mapping = {"ja": "日语", "en": "英语", "zh": "中文", "ch": "中文"}
    return mapping.get(code, code)


def get_system_prompt(target_language: str = "中文", source_language: str = "auto") -> str:
    source_label = _lang_label(source_language)
    return SEGMENT_SYSTEM_PROMPT.format(source_language=source_label)


def get_user_prompt(subtitle_entries_json: str) -> str:
    return SEGMENT_USER_PROMPT.format(subtitle_entries_json=subtitle_entries_json)
