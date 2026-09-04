# Personal Intelligence System V0.2
# Full replacement file for src/main.py

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import feedparser
from bs4 import BeautifulSoup
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = ROOT / "config" / "sources.json"
ITEMS_PATH = ROOT / "data" / "items.json"
PROCESSED_PATH = ROOT / "data" / "processed.json"

MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
MAX_NEW_ITEMS = int(os.getenv("MAX_NEW_ITEMS", "5"))

SCHEMA = {
    "type": "object",
    "properties": {
        "keep": {"type": "boolean"},
        "pis": {"type": "integer", "minimum": 0, "maximum": 100},
        "knowledge_domain": {
            "type": "string",
            "enum": [
                "AI能力演进",
                "企业AI深度应用",
                "AI时代组织变革",
                "AI时代人才发展",
                "AI个人工作系统",
                "AI创业机会",
                "未来社会观察"
            ]
        },
        "title_zh": {"type": "string"},
        "summary_zh": {"type": "string"},
        "core_judgment": {"type": "string"},
        "why_it_matters": {"type": "string"},
        "relation_to_me": {
            "type": "object",
            "properties": {
                "current_work": {"type": "string"},
                "career_growth": {"type": "string"},
                "long_term_value": {"type": "string"}
            },
            "required": [
                "current_work",
                "career_growth",
                "long_term_value"
            ],
            "additionalProperties": False
        },
        "action_type": {
            "type": "string",
            "enum": [
                "IGNORE",
                "READ",
                "SAVE",
                "APPLY",
                "DISCUSS",
                "BUILD"
            ]
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"]
        },
        "counterpoint": {"type": "string"},
        "asset_type": {
            "type": "string",
            "enum": [
                "趋势观察",
                "案例库",
                "方法论",
                "工具实践",
                "创业机会",
                "长期观点"
            ]
        },
        "drop_reason": {"type": ["string", "null"]}
    },
    "required": [
        "keep",
        "pis",
        "knowledge_domain",
        "title_zh",
        "summary_zh",
        "core_judgment",
        "why_it_matters",
        "relation_to_me",
        "action_type",
        "confidence",
        "counterpoint",
        "asset_type",
        "drop_reason"
    ],
    "additionalProperties": False
}

INSTRUCTIONS = """
你是我的 Personal Intelligence Advisor（个人AI情报顾问）。

目标：
帮助我成为AI时代企业转型实践专家。

我的定位：
我希望连接AI技术、企业业务和组织人才发展。
我的优势路径是从人力资源和组织发展的角度，推动企业AI深度应用。

重点关注：
1. 企业AI深度应用
2. AI时代组织变革
3. AI时代人才发展
4. AI个人工作系统
5. AI创业机会
6. AI能力演进
7. 未来社会变化

判断标准：
不要判断内容是否热门。
判断它是否帮助我理解：
“AI如何改变企业，以及我应该如何参与这种变化”。

优先保留：
- 企业AI落地案例
- AI改变工作方式的研究
- 组织和人才变化
- 可形成方法论的信息
- 潜在创业机会

降低价值：
- 工具列表
- 泛泛AI趋势
- 无案例预测
- 单纯新闻
- 重复观点

必须区分：
事实、研究、案例、观点、推测。

输出要求：
说明内容价值；
说明与我的当前工作、职业成长、长期发展的关系；
指出可能的反方观点；
判断下一步行动。
"""

def load_json(path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def clean_html(value):
    text = BeautifulSoup(value or "", "html.parser").get_text("\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()

def analyze(client, source, entry):
    text = clean_html(entry.get("summary", ""))

    prompt = f"""
来源：{source['name']}
链接：{entry.get('link', '')}

内容：
{entry.get('title', '')}

{text[:12000]}
"""

    response = client.responses.create(
        model=MODEL,
        instructions=INSTRUCTIONS,
        input=prompt,
        text={
            "format": {
                "type": "json_schema",
                "name": "personal_intelligence",
                "strict": True,
                "schema": SCHEMA
            }
        },
        store=False
    )

    return json.loads(response.output_text)

def main():
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("缺少 OPENAI_API_KEY")

    client = OpenAI()

    sources = load_json(SOURCES_PATH, [])
    items = load_json(ITEMS_PATH, [])
    processed = set(load_json(PROCESSED_PATH, []))

    candidates = []

    for source in sources:
        feed = feedparser.parse(source["url"])
        for entry in feed.entries:
            uid = entry.get("id") or entry.get("link")
            if uid and uid not in processed:
                candidates.append((source, entry, uid))

    for source, entry, uid in candidates[:MAX_NEW_ITEMS]:
        analysis = analyze(client, source, entry)

        items.append({
            "id": uid,
            "source": source["name"],
            "title_original": entry.get("title", ""),
            "url": entry.get("link", ""),
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "analysis": analysis
        })

        processed.add(uid)

    save_json(ITEMS_PATH, items)
    save_json(PROCESSED_PATH, list(processed))

if __name__ == "__main__":
    main()
