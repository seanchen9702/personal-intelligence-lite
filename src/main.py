# Personal Intelligence System V0.3
# Cross-source deduplication and event clustering

import hashlib
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
EVENTS_PATH = ROOT / "data" / "events.json"
THEMES_PATH = ROOT / "data" / "themes.json"

ANALYSIS_VERSION = "v0.3.1"
MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
MAX_NEW_ITEMS = int(os.getenv("MAX_NEW_ITEMS", "3"))
CLUSTER_MAX_ITEMS = int(os.getenv("CLUSTER_MAX_ITEMS", "15"))

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



THEME_SCHEMA = {
    "type": "object",
    "properties": {
        "themes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "theme_title": {"type": "string"},
                    "research_question": {"type": "string"},
                    "related_event_ids": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "synthesis": {"type": "string"},
                    "current_judgment": {"type": "string"},
                    "still_unknown": {"type": "string"},
                    "asset_direction": {"type": "string"},
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"]
                    }
                },
                "required": [
                    "theme_title",
                    "research_question",
                    "related_event_ids",
                    "synthesis",
                    "current_judgment",
                    "still_unknown",
                    "asset_direction",
                    "confidence"
                ],
                "additionalProperties": False
            }
        }
    },
    "required": ["themes"],
    "additionalProperties": False
}

THEME_INSTRUCTIONS = """
你负责把事件级信息提升为研究主题层。

输入不是文章，而是已经去重后的事件。

你的任务：
1. 找出多个事件背后的共同研究问题；
2. 不为了数量强行合并；
3. 一个主题至少应包含两个事件，或者代表一个持续值得追踪的核心问题。

好的主题：
- Agent如何获得权限，以及何时主动请求人类介入？
- 企业AI价值为什么从模型能力转向流程和组织能力？
- AI时代管理者需要保留哪些判断能力？

不好的主题：
- AI新闻
- Agent相关
- 今天的AI进展

输出重点：
theme_title：高信息密度中文标题
research_question：未来持续追踪的问题
synthesis：多个事件组合后新增的理解
current_judgment：当前阶段判断
still_unknown：仍未解决的问题
asset_direction：未来可以沉淀的方法论/产品资产
"""

CLUSTER_SCHEMA = {
    "type": "object",
    "properties": {
        "clusters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "member_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1
                    },
                    "event_title": {"type": "string"},
                    "event_type": {
                        "type": "string",
                        "enum": ["事件", "报告/研究", "产品/发布", "案例", "独立内容"]
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
                    "combined_summary": {"type": "string"},
                    "combined_judgment": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                    "contradictions": {"type": "string"},
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"]
                    },
                    "recommended_action": {
                        "type": "string",
                        "enum": ["IGNORE", "READ", "SAVE", "APPLY", "DISCUSS", "BUILD"]
                    },
                    "unique_contributions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "item_id": {"type": "string"},
                                "source_role": {
                                    "type": "string",
                                    "enum": [
                                        "一手事实",
                                        "技术机制",
                                        "组织解释",
                                        "企业实践",
                                        "宏观趋势",
                                        "人才/HR视角",
                                        "商业机会",
                                        "反方/校准",
                                        "其他"
                                    ]
                                },
                                "unique_contribution": {"type": "string"}
                            },
                            "required": ["item_id", "source_role", "unique_contribution"],
                            "additionalProperties": False
                        }
                    }
                },
                "required": [
                    "member_ids",
                    "event_title",
                    "event_type",
                    "knowledge_domain",
                    "combined_summary",
                    "combined_judgment",
                    "why_it_matters",
                    "contradictions",
                    "confidence",
                    "recommended_action",
                    "unique_contributions"
                ],
                "additionalProperties": False
            }
        }
    },
    "required": ["clusters"],
    "additionalProperties": False
}

CLUSTER_INSTRUCTIONS = """
你负责把多来源信息从“文章级”提升到“事件级”。

你的首要任务是识别真正的跨来源重复，而不是把相似主题强行合并。

【什么可以合并】
只有以下情况才可以放进同一事件：
1. 描述同一个真实世界事件、事故、发布、研究、报告或企业案例；
2. 不同作者围绕同一个底层事件提供不同层次解释；
3. 一篇主要提供技术事实，另一篇以同一事件为核心提供组织、人才、商业或治理解释。

例如：
- Simon解释某个Agent事故的技术机制；
- Ethan以同一个Agent事故为核心讨论企业应该何时让AI主动寻求人类介入；
这两篇可以属于同一个事件，但必须保留各自独特贡献。

【什么不能合并】
不要仅仅因为两篇文章都谈：
Agent、AI治理、未来工作、模型成本、组织变化
就放到一起。
如果底层事实、报告或案例不同，应保持为不同事件。

【每个事件必须完成】
1. event_title：用中文写一个高信息密度的事件标题；
2. combined_summary：合并已确认事实，不把推测写成事实；
3. combined_judgment：解释不同来源拼在一起后，我们多知道了什么；
4. contradictions：说明来源之间的差异、证据缺口或冲突；
5. unique_contributions：逐条说明每个来源的角色和独特贡献。

目标：
未来Daily Brief不应该告诉我“今天有5篇文章”，
而应该告诉我“今天真正有3个值得知道的事件，以及不同来源各自补充了什么”。
"""

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



def make_event_id(member_ids):
    raw = "|".join(sorted(member_ids)).encode("utf-8")
    return "evt_" + hashlib.sha1(raw).hexdigest()[:12]


def cluster_candidate_items(items):
    candidates = []
    for item in items:
        analysis = item.get("analysis", {})
        if not analysis.get("keep"):
            continue
        if analysis.get("pis", 0) < 50:
            continue
        if not analysis.get("core_judgment"):
            continue
        candidates.append(item)

    # 最近写入的数据在列表尾部。
    return candidates[-CLUSTER_MAX_ITEMS:]


def build_cluster_payload(items):
    payload = []
    for item in items:
        analysis = item.get("analysis", {})
        payload.append({
            "id": item.get("id", ""),
            "source_name": item.get("source_name") or item.get("source", ""),
            "title_original": item.get("title_original", ""),
            "url": item.get("url", ""),
            "pis": analysis.get("pis", 0),
            "tier": analysis.get("tier", ""),
            "knowledge_domain": analysis.get("knowledge_domain", ""),
            "summary_zh": analysis.get("summary_zh", ""),
            "core_judgment": analysis.get("core_judgment", ""),
            "why_it_matters": analysis.get("why_it_matters", ""),
            "information_type": analysis.get("information_type", "")
        })
    return payload


def singleton_event(item):
    analysis = item.get("analysis", {})
    item_id = item.get("id", "")
    source_name = item.get("source_name") or item.get("source", "")

    return {
        "event_id": make_event_id([item_id]),
        "event_title": analysis.get("title_zh") or item.get("title_original", ""),
        "event_type": "独立内容",
        "knowledge_domain": analysis.get("knowledge_domain", ""),
        "member_ids": [item_id],
        "member_count": 1,
        "source_names": [source_name] if source_name else [],
        "source_count": 1 if source_name else 0,
        "is_cross_source": False,
        "event_pis": analysis.get("pis", 0),
        "event_tier": analysis.get("tier", "Archive"),
        "combined_summary": analysis.get("summary_zh", ""),
        "combined_judgment": analysis.get("core_judgment", ""),
        "why_it_matters": analysis.get("why_it_matters", ""),
        "contradictions": analysis.get("counterpoint", ""),
        "confidence": analysis.get("confidence", "medium"),
        "recommended_action": analysis.get("action_type", "SAVE"),
        "unique_contributions": [{
            "item_id": item_id,
            "source_name": source_name,
            "source_role": "其他",
            "unique_contribution": analysis.get("core_judgment", "")
        }]
    }


def cluster_items(client, items):
    candidates = cluster_candidate_items(items)

    if not candidates:
        return []

    if len(candidates) == 1:
        return [singleton_event(candidates[0])]

    payload = build_cluster_payload(candidates)
    valid_ids = {x["id"] for x in payload}
    item_map = {item.get("id", ""): item for item in candidates}

    response = client.responses.create(
        model=MODEL,
        instructions=CLUSTER_INSTRUCTIONS,
        input=json.dumps(payload, ensure_ascii=False),
        text={
            "format": {
                "type": "json_schema",
                "name": "cross_source_event_clusters_v03",
                "strict": True,
                "schema": CLUSTER_SCHEMA
            }
        },
        store=False
    )

    raw = json.loads(response.output_text)

    events = []
    assigned = set()

    for cluster in raw.get("clusters", []):
        member_ids = []
        for item_id in cluster.get("member_ids", []):
            if item_id in valid_ids and item_id not in assigned:
                member_ids.append(item_id)

        if not member_ids:
            continue

        assigned.update(member_ids)

        member_items = [item_map[item_id] for item_id in member_ids]
        member_sources = []
        member_scores = []

        for item in member_items:
            source_name = item.get("source_name") or item.get("source", "")
            if source_name and source_name not in member_sources:
                member_sources.append(source_name)
            member_scores.append(item.get("analysis", {}).get("pis", 0))

        contributions = []
        seen_contribution_ids = set()

        for contribution in cluster.get("unique_contributions", []):
            item_id = contribution.get("item_id", "")
            if item_id not in member_ids or item_id in seen_contribution_ids:
                continue

            source_name = (
                item_map[item_id].get("source_name")
                or item_map[item_id].get("source", "")
            )

            contributions.append({
                "item_id": item_id,
                "source_name": source_name,
                "source_role": contribution.get("source_role", "其他"),
                "unique_contribution": contribution.get("unique_contribution", "")
            })
            seen_contribution_ids.add(item_id)

        # 如果模型遗漏了某个成员的贡献，自动补齐。
        for item_id in member_ids:
            if item_id in seen_contribution_ids:
                continue

            item = item_map[item_id]
            contributions.append({
                "item_id": item_id,
                "source_name": item.get("source_name") or item.get("source", ""),
                "source_role": "其他",
                "unique_contribution": item.get("analysis", {}).get("core_judgment", "")
            })

        event_pis = max(member_scores) if member_scores else 0

        events.append({
            "event_id": make_event_id(member_ids),
            "event_title": cluster.get("event_title", ""),
            "event_type": cluster.get("event_type", "独立内容"),
            "knowledge_domain": cluster.get("knowledge_domain", ""),
            "member_ids": member_ids,
            "member_count": len(member_ids),
            "source_names": member_sources,
            "source_count": len(member_sources),
            "is_cross_source": len(member_sources) >= 2,
            "event_pis": event_pis,
            "event_tier": get_tier(event_pis),
            "combined_summary": cluster.get("combined_summary", ""),
            "combined_judgment": cluster.get("combined_judgment", ""),
            "why_it_matters": cluster.get("why_it_matters", ""),
            "contradictions": cluster.get("contradictions", ""),
            "confidence": cluster.get("confidence", "medium"),
            "recommended_action": cluster.get("recommended_action", "SAVE"),
            "unique_contributions": contributions
        })

    # 没有被模型分组的内容自动成为单例事件，避免丢信息。
    for item in candidates:
        item_id = item.get("id", "")
        if item_id not in assigned:
            events.append(singleton_event(item))

    # 高价值事件排前面。
    events.sort(
        key=lambda x: (
            x.get("is_cross_source", False),
            x.get("event_pis", 0),
            x.get("member_count", 0)
        ),
        reverse=True
    )

    return events


def attach_event_metadata(items, events):
    lookup = {}

    for event in events:
        contribution_lookup = {
            x.get("item_id"): x
            for x in event.get("unique_contributions", [])
        }

        for item_id in event.get("member_ids", []):
            contribution = contribution_lookup.get(item_id, {})
            lookup[item_id] = {
                "event_id": event.get("event_id"),
                "event_title": event.get("event_title"),
                "event_type": event.get("event_type"),
                "cluster_size": event.get("member_count", 1),
                "is_cross_source": event.get("is_cross_source", False),
                "source_role": contribution.get("source_role", "其他"),
                "unique_contribution": contribution.get("unique_contribution", "")
            }

    for item in items:
        item_id = item.get("id", "")
        if item_id in lookup:
            item["event"] = lookup[item_id]



def theme_items_payload(events):
    payload = []
    for event in events:
        if event.get("member_count", 0) < 1:
            continue
        payload.append({
            "event_id": event.get("event_id"),
            "event_title": event.get("event_title"),
            "event_type": event.get("event_type"),
            "knowledge_domain": event.get("knowledge_domain"),
            "combined_summary": event.get("combined_summary"),
            "combined_judgment": event.get("combined_judgment"),
            "why_it_matters": event.get("why_it_matters"),
            "event_pis": event.get("event_pis"),
        })
    return payload[-40:]


def build_themes(client, events):
    if len(events) < 2:
        return []

    payload = theme_items_payload(events)

    response = client.responses.create(
        model=MODEL,
        instructions=THEME_INSTRUCTIONS,
        input=json.dumps(payload, ensure_ascii=False),
        text={
            "format": {
                "type": "json_schema",
                "name": "research_themes_v031",
                "strict": True,
                "schema": THEME_SCHEMA
            }
        },
        store=False
    )

    result = json.loads(response.output_text)
    valid_ids = {e.get("event_id") for e in events}

    themes=[]
    for theme in result.get("themes", []):
        related=[
            x for x in theme.get("related_event_ids", [])
            if x in valid_ids
        ]
        if len(related) < 2:
            continue

        theme["theme_id"]="theme_"+hashlib.sha1(
            "|".join(sorted(related)).encode("utf-8")
        ).hexdigest()[:12]
        theme["related_event_count"]=len(related)
        themes.append(theme)

    return themes

def main():
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("缺少 OPENAI_API_KEY。请在 GitHub Actions Secrets 中添加。")

    sources = load_json(SOURCES_PATH, [])
    items = load_json(ITEMS_PATH, [])
    processed = set(load_json(PROCESSED_PATH, []))
    client = OpenAI()

    # 多源均衡采样：
    # 先从每个来源各取 1 条，再进入下一轮，避免单一来源占满本次处理名额。
    source_queues = []

    for source in sources:
        feed = feedparser.parse(source["url"])

        if getattr(feed, "bozo", False):
            print(f"[WARN] Feed 解析可能有问题: {source.get('name', '')} - {feed.bozo_exception}")

        queue = []
        for entry in feed.entries:
            uid = entry.get("id") or entry.get("link") or entry.get("title")

            if not uid or uid in processed:
                continue

            queue.append((source, entry, uid))

        if queue:
            source_queues.append(queue)

    candidates = []
    round_index = 0

    while len(candidates) < MAX_NEW_ITEMS:
        added_this_round = False

        for queue in source_queues:
            if round_index < len(queue):
                candidates.append(queue[round_index])
                added_this_round = True

                if len(candidates) >= MAX_NEW_ITEMS:
                    break

        if not added_this_round:
            break

        round_index += 1

    print(f"本次发现 {len(candidates)} 条待处理内容，来自 {len(source_queues)} 个有新内容的来源。")

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

    # 无论本轮有没有新内容，都重新检查最近高价值内容的跨来源事件关系。
    events = cluster_items(client, items)
attach_event_metadata(items, events)

themes = load_json(THEMES_PATH, [])

    save_json(ITEMS_PATH, items)
    save_json(PROCESSED_PATH, sorted(processed))
    save_json(EVENTS_PATH, events)
    save_json(THEMES_PATH, themes)

    cross_source_count = sum(1 for event in events if event.get("is_cross_source"))
    print(
        f"累计已保存 {len(items)} 条记录；"
        f"当前形成 {len(events)} 个事件，其中 {cross_source_count} 个跨来源事件；形成 {len(themes)} 个研究主题。"
    )


if __name__ == "__main__":
    main()
