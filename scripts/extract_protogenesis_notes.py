#!/usr/bin/env python3
"""
Extract per-lesson protogenesis notes from the JSON data file.

Usage:
    python scripts/extract_protogenesis_notes.py <book> <lesson>
Example:
    python scripts/extract_protogenesis_notes.py 2 4

Writes formatted Markdown to a temp file and prints the file path.
If the lesson has no content (consolidation lesson), prints a message and exits.
"""

import json
import os
import sys


DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def format_content_block(block):
    """Format a single content block to Markdown."""
    block_type = block.get("type", "paragraph")

    if block_type == "paragraph":
        return block["text"] + "\n"
    elif block_type == "list":
        lines = []
        for i, item in enumerate(block.get("items", []), 1):
            if block.get("ordered", False):
                lines.append(f"{i}. {item}")
            else:
                lines.append(f"- {item}")
        return "\n".join(lines) + "\n"
    elif block_type == "table":
        headers = block.get("headers", [])
        rows = block.get("rows", [])
        lines = []
        if headers:
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in rows:
            padded = list(row)
            while len(padded) < len(headers):
                padded.append("")
            lines.append("| " + " | ".join(padded) + " |")
        return "\n".join(lines) + "\n"
    elif block_type == "blockquote":
        lines = [f"> {line}" for line in block["text"].split("\n")]
        return "\n".join(lines) + "\n"
    elif block_type == "code":
        return f"```\n{block['text']}\n```\n"
    else:
        return block.get("text", "") + "\n"


def format_lesson(lesson_data, book, lesson):
    """Format a lesson's protogenesis notes as Markdown."""
    out = []
    out.append("=" * 60)
    out.append(f"protogenesis 笔记: Book {book} Lesson {lesson}")
    out.append(f"来源: https://protogenesis.github.io/New-Concept-English/NCE{book}.html")
    out.append("=" * 60)
    out.append("")

    main_knowledge = lesson_data.get("main_knowledge", [])
    if main_knowledge:
        out.append("## 主要知识点")
        out.append("")
        for item in main_knowledge:
            out.append(f"- {item}")
        out.append("")

    topics = lesson_data.get("topics", [])
    if topics:
        out.append("---")
        out.append("")
        for topic in topics:
            title = topic.get("title", "")
            if title:
                out.append(f"## {title}")
                out.append("")
            for block in topic.get("content", []):
                out.append(format_content_block(block))
            out.append("")

    return "\n".join(out)


def main():
    if len(sys.argv) != 3:
        print(f"用法: python {sys.argv[0]} <册号> <课次>")
        print(f"示例: python {sys.argv[0]} 2 4")
        sys.exit(1)

    book = sys.argv[1]
    lesson = sys.argv[2]
    lesson_key = f"{int(lesson):03d}"

    json_path = os.path.join(DATA_DIR, f"book{book}", "protogenesis_notes.json")

    if not os.path.exists(json_path):
        print(f"ERROR: 数据文件不存在: {json_path}")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if lesson_key not in data.get("lessons", {}):
        print(
            f"NOTE: Book {book} Lesson {lesson} 没有 protogenesis 补充笔记 "
            f"（该课为复习/练习课，无新增知识点）"
        )
        sys.exit(0)

    lesson_data = data["lessons"][lesson_key]
    output = format_lesson(lesson_data, book, lesson)

    out_path = os.path.join(
        os.environ.get("TEMP", "/tmp"), f"L{lesson}_protogenesis_notes.txt"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(output)

    main_knowledge = lesson_data.get("main_knowledge", [])
    topics = lesson_data.get("topics", [])
    knowledge_count = len(main_knowledge)
    topic_count = len(topics)

    print(f"Saved to: {out_path}")
    print(
        f"protogenesis Book {book} Lesson {lesson}: "
        f"{knowledge_count} 个知识点, {topic_count} 个主题"
    )


if __name__ == "__main__":
    main()
