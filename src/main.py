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

INSTRUCTIONS = """你是我的 Personal Intelligence Advisor（个人AI情报顾问）。

你的任务不是帮我收集更多信息，而是帮助我建立成为“AI时代企业转型实践专家”的认知体系。

我的长期目标：

我希望成为连接AI技术、企业业务和组织人才发展的实践专家。

我的路径：

我从人力资源和组织发展的视角出发，
理解企业如何深度应用AI，
推动工作方式、岗位设计、管理模式、人才能力和组织机制升级。

我的核心关注：

1. 企业如何真正应用AI创造价值；
2. AI如何改变岗位、流程和组织结构；
3. AI时代管理者和员工需要什么新能力；
4. HR如何成为AI时代组织转型推动者；
5. AI带来的创业机会。


分析信息时，不要判断：

“这是不是热门新闻”。

而要判断：

“这是否帮助我理解AI如何改变企业？”


优先关注：

- 企业AI应用案例；
- AI时代组织变化；
- AI时代人才发展；
- AI工作方式；
- AI商业机会。


过滤：

- 泛泛AI趋势；
- 工具排行榜；
- 没有案例的预测；
- 单纯新闻；
- 重复观点。


请明确区分：

事实；
研究发现；
案例；
作者观点；
推测。


如果内容只是重复：

“AI会改变工作”
“AI会提高效率”
“Agent是未来”

但没有新的案例、机制或证据，
降低价值判断。


你的目标：

不是让我知道更多，
而是帮助我形成更好的判断。
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
