# Personal Intelligence System V0.2.1
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

ANALYSIS_VERSION = "v0.2.1"
MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
MAX_NEW_ITEMS = int(os.getenv("MAX_NEW_ITEMS", "5"))

SCHEMA = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "object",
            "properties": {
                "enterprise_ai_value": {"type": "integer", "minimum": 0, "maximum": 30},
                "practical_value": {"type": "integer", "minimum": 0, "maximum": 25},
                "cognitive_upgrade": {"type": "integer", "minimum": 0, "maximum": 20},
                "org_talent_value": {"type": "integer", "minimum": 0, "maximum": 15},
                "information_quality": {"type": "integer", "minimum": 0, "maximum": 10}
            },
            "required": [
                "enterprise_ai_value",
                "practical_value",
                "cognitive_upgrade",
                "org_talent_value",
                "information_quality"
            ],
            "additionalProperties": False
        },
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
                "expert_growth": {"type": "string"},
                "long_term_value": {"type": "string"}
            },
            "required": ["current_work", "expert_growth", "long_term_value"],
            "additionalProperties": False
        },
        "information_type": {
            "type": "string",
            "enum": ["事实", "研究发现", "案例", "作者观点", "推测", "混合"]
        },
        "action_type": {
            "type": "string",
            "enum": ["IGNORE", "READ", "SAVE", "APPLY", "DISCUSS", "BUILD"]
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"]
        },
        "counterpoint": {"type": "string"},
        "asset_type": {
            "type": "string",
            "enum": ["趋势观察", "案例库", "方法论", "工具实践", "创业机会", "长期观点"]
        },
        "drop_reason": {"type": ["string", "null"]}
    },
    "required": [
        "scores",
        "knowledge_domain",
        "title_zh",
        "summary_zh",
        "core_judgment",
        "why_it_matters",
        "relation_to_me",
        "information_type",
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

你的任务不是帮我获取更多AI资讯，而是帮助我持续建立成为
“AI时代企业转型实践专家”的认知、案例、方法论与机会判断。

【我的定位】
我希望连接：AI技术 × 企业业务 × 组织与人才。
我的优势路径不是成为算法研究者，而是从人力资源、组织发展和真实企业场景出发，
理解AI如何被深度嵌入工作、流程、岗位、管理和组织机制，并推动真正落地。

【我的核心目标】
1. 判断企业如何真正用AI创造价值，而非停留在工具使用；
2. 理解AI如何改变工作、流程、岗位、管理模式和组织结构；
3. 理解AI时代员工、管理者、HR和组织能力如何变化；
4. 建立可复用的企业AI落地方法论；
5. 建立自己的AI增强工作系统；
6. 持续发现AI创业、企业服务与咨询机会；
7. 保持对AI能力边界和未来社会变化的必要理解。

【七类知识域】
每条内容只能选择最主要的一类：
- AI能力演进
- 企业AI深度应用
- AI时代组织变革
- AI时代人才发展
- AI个人工作系统
- AI创业机会
- 未来社会观察

【固定评分规则】
不要直接给总分。只给以下五项分数，Python会自动相加。

1. enterprise_ai_value：0–30
问题：这是否帮助我更好理解“AI如何改变企业”？
高分：企业落地机制、工作重构、Agent进入真实流程、AI治理、AI战略与组织变化。
低分：单纯模型发布、参数、热点新闻。

2. practical_value：0–25
问题：这是否能转化为真实实践、实验、案例或方法？
高分：有明确场景、流程、做法、工具链、结果、失败经验。
低分：抽象观点、宏观口号、没有可执行信息。

3. cognitive_upgrade：0–20
问题：这是否带来新的机制解释、反例、框架或判断？
高分：改变我原有理解，或提供强解释力。
低分：重复“AI会提高效率”“Agent是未来”等常识。

4. org_talent_value：0–15
问题：是否帮助理解人、岗位、管理、组织、人才或变革？
注意：不是要求所有内容都与HR直接相关；纯技术但明显改变组织方式也可以得高分。

5. information_quality：0–10
问题：证据质量如何？
高分：一手实验、真实企业案例、研究数据、原始材料。
低分：二手转述、营销、无证据预测。

【总分分层由程序自动计算】
90–100：Immediate，极高价值
80–89：Daily，当日精选
65–79：Weekly，周报候选
50–64：Archive，存档观察
0–49：Drop，不值得占用注意力

【硬过滤】
显著降低评分：
- AI工具排行榜；
- “10个最好用AI工具”；
- 常规版本更新；
- 产品营销；
- 没有案例或机制的趋势预测；
- 单纯新闻转述；
- 重复已有常识；
- 标题党；
- 只有观点，没有证据或推理。

【分析要求】
1. title_zh：给出高信息密度中文标题。
2. summary_zh：只说明内容本身，避免擅自扩展；通常100–180字。
3. core_judgment：回答“这件事真正意味着什么”，不要只是复述。
4. why_it_matters：解释它为什么值得进入我的企业AI转型研究系统。
5. relation_to_me：
   - current_work：对我当前工作或实验有什么直接价值；
   - expert_growth：对我成长为企业AI深度应用落地专家有什么价值；
   - long_term_value：是否能形成方法论、知识资产、咨询能力或创业机会。
6. information_type：严格区分事实、研究发现、案例、作者观点、推测或混合。
7. counterpoint：指出最重要的反例、局限、替代解释或尚未验证之处。
8. action_type：
   - IGNORE：无需投入时间；
   - READ：值得打开原文；
   - SAVE：值得保存为知识资产；
   - APPLY：值得尽快试验或应用；
   - DISCUSS：值得与同事/专家讨论；
   - BUILD：值得形成长期研究主题、方法论或产品方向。
9. asset_type：判断更适合沉淀为哪类资产。
10. confidence：
   - high：事实与证据较充分；
   - medium：方向合理但仍有限制；
   - low：主要是推测或证据不足。
11. drop_reason：
   如果内容明显低价值，说明原因；否则填 null。

不要因为作者知名自动提高评分。
不要把作者判断当作事实。
如果信息不足以支持结论，必须降低 confidence 和相关评分。
"""


def load_json(path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clean_html(value):
    text = BeautifulSoup(value or "", "html.parser").get_text("\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def entry_text(entry):
    parts = []

    if entry.get("title"):
        parts.append(f"标题：{entry.get('title')}")

    if entry.get("summary"):
        parts.append(clean_html(entry.get("summary")))

    for content in entry.get("content", []):
        value = content.get("value", "")
        if value:
            parts.append(clean_html(value))

    return "\n\n".join(x for x in parts if x)[:16000]


def calculate_pis(scores):
    return (
        scores["enterprise_ai_value"]
        + scores["practical_value"]
        + scores["cognitive_upgrade"]
        + scores["org_talent_value"]
        + scores["information_quality"]
    )


def get_tier(pis):
    if pis >= 90:
        return "Immediate"
    if pis >= 80:
        return "Daily"
    if pis >= 65:
        return "Weekly"
    if pis >= 50:
        return "Archive"
    return "Drop"


def analyze(client, source, entry):
    prompt = f"""
请分析以下信息。

来源：{source.get('name', '')}
来源优先级：{source.get('priority', '')}
预设主题：{', '.join(source.get('topics', []))}
原文链接：{entry.get('link', '')}

原始内容：
{entry_text(entry)}
"""

    response = client.responses.create(
        model=MODEL,
        instructions=INSTRUCTIONS,
        input=prompt,
        text={
            "format": {
                "type": "json_schema",
                "name": "personal_intelligence_v021",
                "strict": True,
                "schema": SCHEMA
            }
        },
        store=False
    )

    raw = json.loads(response.output_text)

    pis = calculate_pis(raw["scores"])
    tier = get_tier(pis)
    keep = pis >= 50

    action_type = raw["action_type"]
    if not keep:
        action_type = "IGNORE"

    return {
        "analysis_version": ANALYSIS_VERSION,
        "keep": keep,
        "pis": pis,
        "tier": tier,
        "scores": raw["scores"],
        "knowledge_domain": raw["knowledge_domain"],
        "title_zh": raw["title_zh"],
        "summary_zh": raw["summary_zh"],
        "core_judgment": raw["core_judgment"],
        "why_it_matters": raw["why_it_matters"],
        "relation_to_me": raw["relation_to_me"],
        "information_type": raw["information_type"],
        "action_type": action_type,
        "confidence": raw["confidence"],
        "counterpoint": raw["counterpoint"],
        "asset_type": raw["asset_type"],
        "drop_reason": raw["drop_reason"]
    }


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
            print(f"[WARN] Feed 解析可能有问题: {source.get('name', '')} - {feed.bozo_exception}")

        for entry in feed.entries:
            uid = entry.get("id") or entry.get("link") or entry.get("title")

            if not uid or uid in processed:
                continue

            candidates.append((source, entry, uid))

    candidates = candidates[:MAX_NEW_ITEMS]
    print(f"本次发现 {len(candidates)} 条待处理内容。")

    run_time = datetime.now(timezone.utc).isoformat()

    for source, entry, uid in candidates:
        title = entry.get("title", "(无标题)")
        print(f"分析: {title}")

        try:
            analysis = analyze(client, source, entry)
        except Exception as exc:
            print(f"[ERROR] AI分析失败: {exc}")
            continue

        record = {
            "id": uid,
            "source_id": source.get("id", ""),
            "source_name": source.get("name", ""),
            "title_original": entry.get("title", ""),
            "url": entry.get("link", ""),
            "published": entry.get("published", entry.get("updated", "")),
            "processed_at_utc": run_time,
            "model": MODEL,
            "analysis_version": ANALYSIS_VERSION,
            "analysis": analysis
        }

        items.append(record)
        processed.add(uid)

        print(
            f"  -> {analysis['tier']} | "
            f"PIS {analysis['pis']} | "
            f"{analysis['knowledge_domain']} | "
            f"{analysis['title_zh']}"
        )

    save_json(ITEMS_PATH, items)
    save_json(PROCESSED_PATH, sorted(processed))

    print(f"累计已保存 {len(items)} 条记录。")


if __name__ == "__main__":
    main()
