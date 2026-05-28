"""
提取 Leo老师课堂笔记中指定课次的内容。

用法:
  python extract_neo_notes.py <book> <lesson> [--keywords K1 K2 ...]
  python extract_neo_notes.py 1 45
  python extract_neo_notes.py 1 45 --keywords "boss" "Pamela"

行为:
  1. 从 textbook.json 取该课词汇 + 课文中提取专有名词
  2. 过滤掉高频虚词（can/ask/do/be/have 等）
  3. 在 neo_notes.json 中搜索匹配项
  4. 找到关键词聚集的 item 区间（密集匹配段）
  5. 按 section 分组输出到临时文件
"""
import json, sys, os, re

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(SKILL_DIR, "data")

# 高频虚词——这些词出现在几十课里，没有定位价值
STOP_WORDS = {
    "can", "can't", "cannot", "ask", "do", "does", "don't", "doesn't",
    "be", "is", "am", "are", "was", "were", "been",
    "have", "has", "had", "haven't", "hasn't",
    "go", "goes", "went", "gone", "come", "comes", "came",
    "make", "makes", "made", "take", "takes", "took",
    "get", "gets", "got", "put", "puts",
    "like", "want", "wants", "see", "saw",
    "yes", "no", "not", "here", "there", "please",
    "what", "where", "when", "who", "why", "how",
    "me", "you", "him", "her", "us", "them",
    "i", "he", "she", "it", "we", "they",
    "my", "your", "his", "our", "their",
    "this", "that", "these", "those",
    "some", "any", "one", "two", "three",
    "a", "an", "the", "and", "but", "or", "of", "in", "on", "at", "to", "for", "with",
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_proper_nouns(text):
    """从课文中提取专有名词（首字母大写的人名/地名）"""
    words = re.findall(r'\b[A-Z][a-z]{2,}\b', text)
    # 排除常见的课文字符名（大写开头的普通词）
    fake_names = {"Here", "There", "Thank", "What's", "Where's", "Who's",
                  "Yes", "This", "That", "Look", "Can", "Are", "Is"}
    return list(set(w for w in words if w not in fake_names))


def get_lesson_keywords(book, lesson):
    """从 textbook 提取有意义的关键词（排除虚词 + 加入专有名词）"""
    lesson_key = str(lesson).zfill(3)
    textbook = load_json(os.path.join(DATA, f"book{book}", "textbook.json"))

    if lesson_key not in textbook:
        print(f"Warning: textbook.json 中没有 Lesson {lesson} ({lesson_key})")
        return []

    lesson_data = textbook[lesson_key]
    vocab = lesson_data.get("vocabulary", [])
    text = lesson_data.get("text", "")

    keywords = []

    # 从词汇表取实词
    if isinstance(vocab, list):
        for v in vocab:
            if isinstance(v, dict):
                word = v.get("word", "").strip()
            elif isinstance(v, str):
                word = v.strip()
            else:
                continue
            if word and len(word) > 2 and word.lower() not in STOP_WORDS:
                keywords.append(word)

    # 从课文中提取专有名词（人名/地名）
    proper_nouns = extract_proper_nouns(text)
    for pn in proper_nouns:
        if pn.lower() not in STOP_WORDS and pn not in keywords:
            keywords.append(pn)

    # 最多取 6 个关键词，优先保留词汇（排序在前的）
    return keywords[:6]


def search_notes(book, keywords):
    """在 neo_notes 中搜索关键词，返回 items 列表和匹配 item 索引集合"""
    notes = load_json(os.path.join(DATA, f"book{book}", "neo_notes.json"))
    items = notes["sections"]

    matched = set()
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        text = item.get("text", "")
        for kw in keywords:
            if kw.lower() in text.lower():
                matched.add(i)
                break
    return items, matched


def find_cluster(matched_indices, items, window=100, max_gap=60):
    """找到匹配最密集的区间（匹配数/跨度 最大），前后扩展 window"""
    if not matched_indices:
        return 0, 0

    sorted_idx = sorted(matched_indices)

    # 按 max_gap 切分成段落
    segments = []
    seg_start = sorted_idx[0]
    for i in range(1, len(sorted_idx)):
        if sorted_idx[i] - sorted_idx[i - 1] > max_gap:
            segments.append((seg_start, sorted_idx[i - 1]))
            seg_start = sorted_idx[i]
    segments.append((seg_start, sorted_idx[-1]))

    # 选最优段：评分 = 匹配数^2 / 跨度（偏好多匹配 + 紧凑）
    def score(seg):
        s, e = seg
        span = e - s + 1
        count = sum(1 for idx in sorted_idx if s <= idx <= e)
        return count * count / span if span > 0 else 0

    best = max(segments, key=score)

    start = max(0, best[0] - window)
    end = min(len(items), best[1] + window)
    return start, end


def format_output(items, start, end):
    """将指定区间的 items 格式化为可读文本"""
    lines = []
    prev_section = None

    labels = {
        "grammar": "【语法讲练】",
        "homework": "【课后作业】",
        "practices": "【课堂练习】",
    }

    for i in range(start, end):
        if i >= len(items):
            break
        item = items[i]
        if not isinstance(item, dict):
            continue

        text = item.get("text", "").strip()
        section = item.get("section", "")
        itype = item.get("type", "")

        if itype == "section_header" and not text:
            lines.append("")
            continue

        if section and section != prev_section and section in labels:
            lines.append(f"\n{labels[section]}")
        prev_section = section

        if text:
            lines.append(text)

    return "\n".join(lines)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    book = int(sys.argv[1])
    lesson = int(sys.argv[2])

    custom_kw = []
    for i in range(3, len(sys.argv)):
        if sys.argv[i] == "--keywords":
            custom_kw = sys.argv[i + 1:]
            break

    if custom_kw:
        keywords = custom_kw
    else:
        keywords = get_lesson_keywords(book, lesson)

    if not keywords:
        print("ERROR: 未能提取关键词，请用 --keywords 手动指定")
        sys.exit(1)

    print(f"Keywords: {keywords}")

    items, matched = search_notes(book, keywords)
    if not matched:
        print("ERROR: neo_notes 中未找到匹配内容")
        sys.exit(1)

    print(f"Matched items: {len(matched)}")

    start, end = find_cluster(matched, items)

    # 如果区间太大（>800），说明关键词不够精准，只用专有名词重试
    if end - start > 800:
        proper_only = [kw for kw in keywords if kw[0].isupper()]
        if proper_only and proper_only != keywords:
            print(f"Range too large ({end - start}), retry with proper nouns only: {proper_only}")
            items, matched = search_notes(book, proper_only)
            if matched:
                print(f"Matched items: {len(matched)}")
                start, end = find_cluster(matched, items)

    print(f"Range: items [{start}, {end}) ({end - start} items)")

    output = format_output(items, start, end)
    header = (
        f"{'=' * 60}\n"
        f"Leo老师 Book {book} Lesson {lesson} 课堂笔记\n"
        f"Keywords: {' / '.join(keywords)}\n"
        f"{'=' * 60}\n\n"
    )

    out_path = os.path.join(os.environ.get("TEMP", "/tmp"), f"L{lesson}_notes.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(header + output)

    print(f"Saved to: {out_path}")


if __name__ == "__main__":
    main()
