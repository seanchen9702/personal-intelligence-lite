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

MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
MAX_NEW_ITEMS = int(os.getenv("MAX_NEW_ITEMS", "5"))

SCHEMA = {
    "type": "object",
    "properties": {
        "keep": {"type": "boolean"},
        "pis": {"type": "integer", "minimum": 0, "maximum": 100},
        "title_zh": {"type": "string"},
        "summary_zh": {"type": "string"},
        "why_it_matters": {"type": "string"},
        "topics": {
            "type": "array",
            "items": {"type": "string"}
        },
        "information_type": {
            "type": "string",
            "enum": ["事实", "研究发现", "案例", "作者推测", "价值判断", "混合"]
        },
        "recommended_action": {
            "type": "string",
            "enum": ["必看原文", "看中文摘要即可", "收藏备用", "进入Weekly分析", "丢弃"]
        },
        "drop_reason": {"type": ["string", "null"]}
    },
    "required": [
        "keep", "pis", "title_zh", "summary_zh", "why_it_matters",
        "topics", "information_type", "recommended_action", "drop_reason"
    ],
    "additionalProperties": False
}

INSTRUCTIONS = """你是我的个人信息情报筛选器。你的首要任务是保护注意力，而不是尽可能推荐内容。

我的优先主题：
A类：AI产品与实际应用；AI×未来社会/工作/教育；Leadership与管理者培养；HRD/HRBP/组织管理；AI工作方式与自动化；世界文明/城市/深度旅行。
B类：AI技术/模型/Agent；L&D；商业/创业；宏观经济/科技产业。
C类：哲学/历史/社会科学。

评分维度：相关性R 20%，新颖性N 20%，证据质量E 15%，实践价值A 20%，认知杠杆L 15%，信源质量S 10%。
最终给0-100分PIS。

硬过滤：常规产品宣传、无新增信息的新闻转述、标题党、泛泛而谈、重复的“AI会改变工作/Agent是未来”等无新增证据或机制的内容。

分层：
90-100 极高价值；
80-89 Daily候选；
65-79 Weekly候选；
<65 默认丢弃。

不要因为作者知名就提高评分。明确区分事实、研究发现、案例、作者推测和价值判断。
中文摘要要精炼，通常100-180字。
"""

def load_json(path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)

def clean_html(value):
    if not value:
        return ""
    text = BeautifulSoup(value, "html.parser").get_text("\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def entry_text(entry):
    parts = []
    if getattr(entry, "title", None):
        parts.append(f"标题：{entry.title}")
    if getattr(entry, "summary", None):
        parts.append(clean_html(entry.summary))
    for content in getattr(entry, "content", []):
        value = content.get("value", "")
        if value:
            parts.append(clean_html(value))
    # 防止把异常超长Feed整篇塞入筛选模型；初版只需要足够判断价值。
    text = "\n\n".join(x for x in parts if x)
    return text[:16000]

def analyze(client, source, entry):
    text = entry_text(entry)
    user_input = f"""请评估以下内容是否值得进入我的个人情报系统。

来源：{source['name']}
来源优先级：{source.get('priority', 'P1')}
预设主题：{', '.join(source.get('topics', []))}
原文链接：{entry.get('link', '')}

内容：
{text}
"""
    response = client.responses.create(
        model=MODEL,
        instructions=INSTRUCTIONS,
        input=user_input,
        reasoning={"effort": "none"},
        text={
            "verbosity": "low",
            "format": {
                "type": "json_schema",
                "name": "intelligence_screen",
                "strict": True,
                "schema": SCHEMA,
            },
        },
        store=False,
    )
    return json.loads(response.output_text)

def main():
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("缺少 OPENAI_API_KEY。请在 GitHub Actions Secrets 中添加。")

    sources = load_json(SOURCES_PATH, [])
    items = load_json(ITEMS_PATH, [])
    processed = set(load_json(PROCESSED_PATH, []))
    client = OpenAI()

    candidates = []
    for source in sources:
        feed = feedparser.parse(source["url"])
        if getattr(feed, "bozo", False):
            print(f"[WARN] Feed 解析可能有问题: {source['name']} - {feed.bozo_exception}")
        for entry in feed.entries:
            uid = entry.get("id") or entry.get("link") or entry.get("title")
            if not uid or uid in processed:
                continue
            candidates.append((source, entry, uid))

    # 初版只处理最新的少量未读内容，避免第一次运行就产生无意义成本。
    candidates = candidates[:MAX_NEW_ITEMS]
    print(f"本次发现 {len(candidates)} 条待处理内容。")

    run_time = datetime.now(timezone.utc).isoformat()

    for source, entry, uid in candidates:
        print(f"分析: {entry.get('title', '(无标题)')}")
        try:
            analysis = analyze(client, source, entry)
        except Exception as e:
            print(f"[ERROR] AI分析失败: {e}")
            continue

        record = {
            "id": uid,
            "source_id": source["id"],
            "source_name": source["name"],
            "title_original": entry.get("title", ""),
            "url": entry.get("link", ""),
            "published": entry.get("published", entry.get("updated", "")),
            "processed_at_utc": run_time,
            "model": MODEL,
            "analysis": analysis,
        }
        items.append(record)
        processed.add(uid)

        status = "KEEP" if analysis["keep"] else "DROP"
        print(f"  -> {status} | PIS {analysis['pis']} | {analysis['title_zh']}")

    save_json(ITEMS_PATH, items)
    save_json(PROCESSED_PATH, sorted(processed))

    kept = [x for x in items if x.get("analysis", {}).get("keep")]
    print(f"累计已处理 {len(items)} 条，其中保留 {len(kept)} 条。")

if __name__ == "__main__":
    main()
