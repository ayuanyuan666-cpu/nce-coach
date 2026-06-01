#!/usr/bin/env python3
"""One-time scraper: parse protogenesis NCE HTML pages into structured JSON.

Usage:
    python scripts/scrape_protogenesis.py

Produces:
    data/book1/protogenesis_notes.json
    data/book2/protogenesis_notes.json
    data/book3/protogenesis_notes.json
"""

import json
import os
import re
import ssl
import urllib.request
from html.parser import HTMLParser
from collections import OrderedDict


BASE_URL = "https://protogenesis.github.io/New-Concept-English/NCE{}.html"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
PROXY = "http://127.0.0.1:10808"


def fetch_html(book_num):
    """Fetch HTML from URL via proxy."""
    url = BASE_URL.format(book_num)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    proxy_handler = urllib.request.ProxyHandler(
        {"http": PROXY, "https": PROXY}
    )
    opener = urllib.request.build_opener(proxy_handler)
    urllib.request.install_opener(opener)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    resp = urllib.request.urlopen(req, context=ctx)
    return resp.read().decode("utf-8")


def extract_lesson_numbers(h1_text, h1_id):
    """Extract all lesson numbers from h1 text and id.

    Handles:
    - "Lesson 1" (id="lesson-1") -> [1]
    - "Lesson 23&amp;24" (id="lesson-23lesson-24") -> [23, 24]
    - "Lesson 57-60" (id="lesson-57-60") -> [57, 58, 59, 60]
    - "Lesson 3" (id="lessoon-3") -> [3]
    """
    nums = []

    # From heading text first (most reliable)
    text_nums = re.findall(r"\d+", unescape_text(h1_text))
    text_nums = [int(n) for n in text_nums]

    # From ID - extract ALL numeric sequences
    id_nums = [int(n) for n in re.findall(r"\d+", h1_id)]

    # Detect range: if ID contains pattern like "57-60" (hyphen between numbers)
    # and text_nums only has [57, 60] -> expand range
    if re.search(r"\d+-\d+", h1_id) and len(text_nums) >= 2:
        first, last = text_nums[0], text_nums[-1]
        if last > first and last - first <= 60:
            return list(range(first, last + 1))

    # For combined IDs like "lesson-23lesson-24" or "lesson-333435"
    # text usually has the correct numbers
    if text_nums:
        return sorted(set(text_nums))

    # Fallback: use numbers from ID
    return sorted(set(id_nums))


def unescape_text(text):
    """Unescape HTML entities and clean whitespace."""
    from html import unescape
    text = unescape(text)
    text = text.replace("\xa0", " ")
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def inline_to_markdown(text):
    """Convert inline HTML markup to Markdown."""
    text = re.sub(r"<strong>(.*?)</strong>", r"**\1**", text)
    text = re.sub(r"<em>(.*?)</em>", r"*\1*", text)
    text = re.sub(r"<code>(.*?)</code>", r"`\1`", text)
    text = re.sub(r'<a\s+href="([^"]*)"[^>]*>(.*?)</a>', r"[\2](\1)", text)
    return unescape_text(text)


class LessonParser(HTMLParser):
    """Parse a single lesson's HTML content into structured JSON."""

    def __init__(self):
        super().__init__()
        self.topics = []  # [{title, content: [{type, ...}]}]
        self.main_knowledge = []  # ["知识点1", "知识点2"]
        self.classic_phrases = []  # ["phrase1", "phrase2"]
        self._current_topic = None
        self._in_main_knowledge = False
        self._in_h4 = False
        self._in_h5 = False
        self._in_li = False
        self._in_p = False
        self._in_table = False
        self._in_th = False
        self._in_td = False
        self._in_blockquote = False
        self._in_strong = False
        self._in_list = False
        self._in_code = False
        self._list_ordered = False
        self._list_items = []
        self._table_headers = []
        self._table_rows = []
        self._table_current_row = []
        self._table_current_cell = ""
        self._text_buffer = ""
        self._blockquote_lines = []
        self._code_text = ""
        self._tag_stack = []
        self._h4_texts = []  # Track h4 texts to identify sections

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        self._tag_stack.append(tag)

        if tag == "h4":
            self._in_h4 = True
            self._text_buffer = ""
        elif tag == "h5":
            self._in_h5 = True
            self._text_buffer = ""
        elif tag == "h6":
            self._in_h5 = True
            self._text_buffer = ""
        elif tag == "p":
            self._in_p = True
            self._text_buffer = ""
        elif tag == "li":
            self._in_li = True
            self._text_buffer = ""
        elif tag == "strong":
            self._in_strong = True
        elif tag == "table":
            self._in_table = True
            self._table_headers = []
            self._table_rows = []
            self._table_current_row = []
        elif tag == "th":
            self._in_th = True
            self._table_current_cell = ""
        elif tag == "td":
            self._in_td = True
            self._table_current_cell = ""
        elif tag == "tr":
            self._table_current_row = []
        elif tag == "ul":
            self._in_list = True
            self._list_ordered = False
            self._list_items = []
        elif tag == "ol":
            self._in_list = True
            self._list_ordered = True
            self._list_items = []
        elif tag == "blockquote":
            self._in_blockquote = True
            self._blockquote_lines = []
        elif tag == "code":
            self._in_code = True
            self._code_text = ""

    def handle_endtag(self, tag):
        if self._tag_stack:
            self._tag_stack.pop()

        if tag == "h4":
            self._in_h4 = False
            h4_text = unescape_text(self._text_buffer)
            self._h4_texts.append(h4_text)
            if "主要知识点" in h4_text or "main knowledge" in h4_text.lower():
                self._in_main_knowledge = True
        elif tag == "h5" or tag == "h6":
            self._in_h5 = False
            title = unescape_text(self._text_buffer)
            if title and len(title) > 1:
                # Check for special section types
                if any(kw in title for kw in ["经典", "短语", "结构", "语句"]):
                    pass  # Will be handled when content follows
                self._in_main_knowledge = False
                self._current_topic = {"title": title, "content": []}
                self.topics.append(self._current_topic)
        elif tag == "p":
            self._in_p = False
            text = inline_to_markdown(self._text_buffer)
            if not text:
                return
            if self._in_blockquote:
                self._blockquote_lines.append(text)
            elif self._current_topic is not None:
                self._current_topic["content"].append(
                    {"type": "paragraph", "text": text}
                )
            elif self._in_main_knowledge:
                pass  # Main knowledge is from <ul>
            else:
                # Orphan paragraph - create a topic for it
                self._current_topic = {"title": text[:50], "content": []}
                self.topics.append(self._current_topic)
                self._current_topic["content"].append(
                    {"type": "paragraph", "text": text}
                )
        elif tag == "li":
            self._in_li = False
            text = inline_to_markdown(self._text_buffer)
            if not text:
                return
            if self._in_main_knowledge and not self._in_list:
                self.main_knowledge.append(text)
            elif self._in_list:
                self._list_items.append(text)
        elif tag == "ul" or tag == "ol":
            if self._list_items:
                if self._in_main_knowledge:
                    # This list belongs to the "Main knowledge" section
                    self.main_knowledge.extend(self._list_items)
                else:
                    content_item = {
                        "type": "list",
                        "ordered": self._list_ordered,
                        "items": list(self._list_items),
                    }
                    if self._current_topic is not None:
                        self._current_topic["content"].append(content_item)
                    else:
                        # Orphan list - create a topic for it
                        self._current_topic = {
                            "title": self._list_items[0][:50] if self._list_items else "",
                            "content": [content_item],
                        }
                        self.topics.append(self._current_topic)
            self._in_list = False
            self._list_items = []
        elif tag == "table":
            self._in_table = False
            if self._table_headers or self._table_rows:
                content_item = {
                    "type": "table",
                    "headers": self._table_headers,
                    "rows": self._table_rows,
                }
                if self._current_topic is not None:
                    self._current_topic["content"].append(content_item)
        elif tag == "th":
            self._in_th = False
            cell_text = unescape_text(self._table_current_cell)
            self._table_headers.append(cell_text)
        elif tag == "td":
            self._in_td = False
            cell_text = unescape_text(self._table_current_cell)
            self._table_current_row.append(cell_text)
        elif tag == "tr":
            if self._table_current_row:
                self._table_rows.append(list(self._table_current_row))
            self._table_current_row = []
        elif tag == "blockquote":
            self._in_blockquote = False
            text = "\n".join(self._blockquote_lines)
            if text:
                if self._current_topic is not None:
                    self._current_topic["content"].append(
                        {"type": "blockquote", "text": text}
                    )
        elif tag == "code":
            self._in_code = False
            if self._code_text.strip():
                content_item = {"type": "code", "text": self._code_text.strip()}
                if self._current_topic is not None:
                    self._current_topic["content"].append(content_item)

    def handle_data(self, data):
        if self._in_h4 or self._in_h5 or self._in_p or self._in_li:
            self._text_buffer += data
        elif self._in_td or self._in_th:
            self._table_current_cell += data
        elif self._in_code:
            self._code_text += data
        elif self._in_blockquote:
            stripped = data.strip()
            if stripped:
                self._blockquote_lines.append(stripped)

    def get_result(self):
        return {
            "main_knowledge": list(self.main_knowledge),
            "topics": self.topics,
        }


def split_lesson_blocks(html):
    """Split HTML into per-lesson blocks using h1 headings with lesson IDs."""
    # Find all lesson h1 positions
    lesson_pattern = re.compile(
        r'<h1\s+id="(less[oO]{1,2}n-[^"]+)"[^>]*>'
        r"(.*?)</h1>"
    )
    matches = list(lesson_pattern.finditer(html))

    blocks = []
    for i, match in enumerate(matches):
        h1_id = match.group(1)
        h1_text = re.sub(r"<[^>]+>", "", match.group(2))
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(html)
        lesson_html = html[start:end]
        lesson_nums = extract_lesson_numbers(h1_text, h1_id)

        blocks.append(
            {
                "lesson_nums": lesson_nums,
                "html": lesson_html,
                "heading_text": unescape_text(h1_text),
            }
        )

    return blocks


def parse_lesson_html(lesson_html):
    """Parse a single lesson's HTML content."""
    parser = LessonParser()
    try:
        parser.feed(lesson_html)
    except Exception as e:
        print(f"  WARNING: parse error: {e}")
    return parser.get_result()


def scrape_book(book_num):
    """Scrape one book's HTML and produce structured JSON."""
    print(f"Fetching Book {book_num}...")
    html = fetch_html(book_num)

    print(f"  Splitting lesson blocks...")
    blocks = split_lesson_blocks(html)
    print(f"  Found {len(blocks)} lesson blocks")

    lessons = OrderedDict()
    for block in blocks:
        result = parse_lesson_html(block["html"])
        # Skip empty entries
        if not result["main_knowledge"] and not result["topics"]:
            continue

        entry = {}
        if result["main_knowledge"]:
            entry["main_knowledge"] = result["main_knowledge"]
        if result["topics"]:
            entry["topics"] = result["topics"]

        if not entry:
            continue

        for num in block["lesson_nums"]:
            key = f"{num:03d}"
            lessons[key] = entry

    # Build lesson content list for index
    lesson_list = list(lessons.keys())

    output = OrderedDict()
    output["source"] = BASE_URL.format(book_num)
    output["source_label"] = "protogenesis 新概念英语笔记"
    output["book"] = book_num
    output["description"] = (
        f"新概念英语第{book_num}册手动整理语法笔记，仅包含引入新知识点的课次"
    )
    output["total_lessons_with_content"] = len(lesson_list)
    output["lesson_content_map"] = {"lessons": lesson_list}
    output["lessons"] = lessons

    return output


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    for book_num in [1, 2, 3]:
        output = scrape_book(book_num)

        book_dir = os.path.join(DATA_DIR, f"book{book_num}")
        os.makedirs(book_dir, exist_ok=True)
        out_path = os.path.join(book_dir, "protogenesis_notes.json")

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        lesson_count = len(output["lesson_content_map"]["lessons"])
        file_size_kb = os.path.getsize(out_path) / 1024
        print(f"  Saved: {out_path} ({lesson_count} lessons, {file_size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
