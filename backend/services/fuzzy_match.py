"""字符串模糊匹配 — 处理语音识别偏差、错别字、标点差异。"""

import re


def normalize(text: str) -> str:
    """标准化：去标点、去多余空格、转小写。

    把 "xx-x" 和 "xxx" 归一化到同一形式。
    """
    # 去掉所有标点符号（保留中文字、英文字母、数字、空格）
    text = re.sub(r"[^\w\s]", "", text)
    # 合并连续空格
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def levenshtein_ratio(s1: str, s2: str) -> float:
    """Levenshtein 相似度，返回值 0.0（完全不同）到 1.0（完全相同）。

    使用 O(n*m) 动态规划，对短标题（≤50 字）性能足够。
    """
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    n1, n2 = len(s1), len(s2)
    # 复用较短字符串做行以节省内存
    if n1 > n2:
        s1, s2 = s2, s1
        n1, n2 = n2, n1

    prev = list(range(n1 + 1))
    curr = [0] * (n1 + 1)

    for j in range(1, n2 + 1):
        curr[0] = j
        for i in range(1, n1 + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            curr[i] = min(prev[i] + 1, curr[i - 1] + 1, prev[i - 1] + cost)
        prev, curr = curr, prev

    distance = prev[n1]
    max_len = max(n1, n2)
    return 1.0 - (distance / max_len)


def fuzzy_match(new_title: str, existing_titles: list[str], threshold: float = 0.6) -> tuple[str | None, float]:
    """在已有标题列表中找最相似的一项。

    返回 (最佳匹配标题, 相似度) 或 (None, 0.0)。
    """
    new_norm = normalize(new_title)
    best_title = None
    best_score = 0.0

    for title in existing_titles:
        score = levenshtein_ratio(new_norm, normalize(title))
        if score > best_score:
            best_score = score
            best_title = title

    if best_score >= threshold:
        return best_title, best_score
    return None, 0.0


def classify_match(score: float) -> str:
    """按相似度分数分类。

    - auto_merge (≥0.85)：几乎肯定同一件事，自动合并
    - ask_user (0.5-0.85)：可能相同，需要问用户
    - new_item (<0.5)：不同的事情
    """
    if score >= 0.85:
        return "auto_merge"
    elif score >= 0.5:
        return "ask_user"
    return "new_item"
