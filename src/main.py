# Personal Intelligence System V0.4.1
# Evidence-first: source detail extraction, evidence scoring, drill-down pages, and Daily Brief.

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import feedparser
from bs4 import BeautifulSoup
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = ROOT / "config" / "sources.json"
ITEMS_PATH = ROOT / "data" / "items.json"
PROCESSED_PATH = ROOT / "data" / "processed.json"
EVENTS_PATH = ROOT / "data" / "events.json"
THEMES_PATH = ROOT / "data" / "themes.json"
DAILY_BRIEF_PATH = ROOT / "data" / "daily_brief.md"
DETAILS_DIR = ROOT / "data" / "details"

ANALYSIS_VERSION = "v0.4.1"
MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
MAX_NEW_ITEMS = int(os.getenv("MAX_NEW_ITEMS", "3"))
CLUSTER_MAX_ITEMS = int(os.getenv("CLUSTER_MAX_ITEMS", "15"))
BRIEF_MAX_EVENTS = int(os.getenv("BRIEF_MAX_EVENTS", "5"))
ARTICLE_CHAR_LIMIT = int(os.getenv("ARTICLE_CHAR_LIMIT", "18000"))

# ---------------------------------------------------------------------
# Evidence-first single-item analysis
# ---------------------------------------------------------------------

SCHEMA = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "object",
            "properties": {
                "enterprise_ai_value": {"type": "integer", "minimum": 0, "maximum": 20},
                "practical_value": {"type": "integer", "minimum": 0, "maximum": 15},
                "cognitive_upgrade": {"type": "integer", "minimum": 0, "maximum": 15},
                "org_talent_value": {"type": "integer", "minimum": 0, "maximum": 10},
                "information_quality": {"type": "integer", "minimum": 0, "maximum": 10},
                "specificity": {"type": "integer", "minimum": 0, "maximum": 15},
                "evidence_density": {"type": "integer", "minimum": 0, "maximum": 15}
            },
            "required": [
                "enterprise_ai_value",
                "practical_value",
                "cognitive_upgrade",
                "org_talent_value",
                "information_quality",
                "specificity",
                "evidence_density"
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
        "evidence": {
            "type": "object",
            "properties": {
                "concrete_facts": {"type": "array", "items": {"type": "string"}},
                "numbers_metrics": {"type": "array", "items": {"type": "string"}},
                "mechanism_steps": {"type": "array", "items": {"type": "string"}},
                "named_entities": {"type": "array", "items": {"type": "string"}},
                "case_details": {
                    "type": "object",
                    "properties": {
                        "actor": {"type": "string"},
                        "context": {"type": "string"},
                        "problem": {"type": "string"},
                        "ai_intervention": {"type": "string"},
                        "workflow_change": {"type": "string"},
                        "human_role": {"type": "string"},
                        "outcome": {"type": "string"},
                        "failure_limits": {"type": "string"}
                    },
                    "required": [
                        "actor",
                        "context",
                        "problem",
                        "ai_intervention",
                        "workflow_change",
                        "human_role",
                        "outcome",
                        "failure_limits"
                    ],
                    "additionalProperties": False
                }
            },
            "required": [
                "concrete_facts",
                "numbers_metrics",
                "mechanism_steps",
                "named_entities",
                "case_details"
            ],
            "additionalProperties": False
        },
        "claim_map": {
            "type": "object",
            "properties": {
                "confirmed_or_reported_facts": {"type": "array", "items": {"type": "string"}},
                "author_interpretations": {"type": "array", "items": {"type": "string"}},
                "model_inferences": {"type": "array", "items": {"type": "string"}},
                "unknowns": {"type": "array", "items": {"type": "string"}}
            },
            "required": [
                "confirmed_or_reported_facts",
                "author_interpretations",
                "model_inferences",
                "unknowns"
            ],
            "additionalProperties": False
        },
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
        "why_read_original": {"type": "string"},
        "original_reading_focus": {"type": "array", "items": {"type": "string"}},
        "information_type": {
            "type": "string",
            "enum": ["事实", "研究发现", "案例", "作者观点", "推测", "混合"]
        },
        "action_type": {
            "type": "string",
            "enum": ["IGNORE", "READ", "SAVE", "APPLY", "DISCUSS", "BUILD"]
        },
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
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
        "evidence",
        "claim_map",
        "relation_to_me",
        "why_read_original",
        "original_reading_focus",
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
你是 Evidence-first Personal Intelligence Advisor。

我的方向：
从人力资源与组织视角出发，成长为企业AI深度应用落地专家。
我不需要更多“正确的AI观点”，我需要可以支撑判断的具体事实、企业案例、机制、数据、失败过程和工作流细节。

【最重要的原则】
先抽取证据，再做判断。不要先想一个漂亮结论，再从原文中寻找支持。

如果删掉企业名、人物、数字、流程、机制、失败细节后，内容只剩：
“AI会改变工作”“企业要重视治理”“人机协同很重要”“Agent是未来”
则这是正确的废话，应显著降分。

【固定评分，共100分】
enterprise_ai_value 0-20：
是否帮助理解AI如何进入真实企业和业务。

practical_value 0-15：
是否可以转化成实验、模板、方法或具体动作。

cognitive_upgrade 0-15：
是否提供新机制、新反例或真正改变判断的证据。

org_talent_value 0-10：
是否帮助理解岗位、管理、组织、人才与变革。

information_quality 0-10：
证据来源和可信度。

specificity 0-15：
有没有明确主体、任务、流程、工具、权限、动作、结果和失败细节。

evidence_density 0-15：
每单位内容中有多少可验证事实、数字、案例和机制，而不是评论和概念。

【硬性上限】
- specificity < 6 且 evidence_density < 6：总分应视为不超过49。
- specificity < 8 或 evidence_density < 8：除非是重大一手研究，否则不应进入Daily。
- 没有任何具体事实、数字、机制或案例：默认Drop。
- 作者知名度不能加分。

【证据输出】
concrete_facts：
只写原文明确报告/描述的事实，尽量包含主体、动作、对象、条件。

numbers_metrics：
把所有有解释价值的数字、比例、时间、成本、次数、规模、结果指标列出来。没有就返回空数组，禁止编造。

mechanism_steps：
如果原文描述了“怎么发生/怎么做”的过程，按步骤提炼。没有则返回空数组。

case_details：
尽可能还原“谁—什么背景—原问题—AI如何介入—流程怎么变—人做什么—结果—失败或限制”。
原文没有的信息明确写“原文未提供”，不要补全。

claim_map：
必须区分：
1. 原文明示的事实/报告；
2. 作者解释；
3. 你基于材料做的推断；
4. 尚未知。

【判断输出】
core_judgment必须由证据推出。
如果证据不足，不要用宏大结论包装。

why_read_original：
告诉我为什么值得点开原文；如果不值得，明确说“不需要阅读全文”。

original_reading_focus：
告诉我打开原文后重点找什么细节，而不是让我从头通读。

目标：
让我能够从日报快速扫读，并在真正重要的内容上继续下钻到细节和原始材料。
"""

# ---------------------------------------------------------------------
# Event clustering
# ---------------------------------------------------------------------

CLUSTER_SCHEMA = {
    "type": "object",
    "properties": {
        "clusters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "member_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
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
                    "key_evidence": {"type": "array", "items": {"type": "string"}},
                    "contradictions": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
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
                    "key_evidence",
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
把文章级信息聚合为事件级信息。
只有描述同一底层事件、报告、企业案例、产品发布或实验时才合并。
相似主题但底层事实不同，不要合并。

聚合时优先保留：
- 企业/机构/产品名称
- 真实工作任务
- 具体数字和指标
- 实际流程
- 技术或管理机制
- 失败、反例和限制

combined_judgment不能比成员材料更宏大。
key_evidence必须是成员材料中已存在的具体证据。
"""

# ---------------------------------------------------------------------
# Weekly themes
# ---------------------------------------------------------------------

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
                    "related_event_ids": {"type": "array", "items": {"type": "string"}},
                    "synthesis": {"type": "string"},
                    "current_judgment": {"type": "string"},
                    "still_unknown": {"type": "string"},
                    "asset_direction": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]}
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
把事件提升为研究主题。
不要输出“AI治理”“Agent趋势”这类宽泛主题。
主题必须是一个值得长期验证的具体问题，例如：
“企业如何确定Agent必须暂停并请求人工授权的阈值？”
优先围绕多个事件共享的机制、矛盾或证据缺口形成主题。
"""

# ---------------------------------------------------------------------
# Daily Brief
# ---------------------------------------------------------------------

BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "overview": {"type": "string"},
        "top_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string"},
                    "title": {"type": "string"},
                    "why_top": {"type": "string"},
                    "judgment_update": {"type": "string"},
                    "for_me": {"type": "string"},
                    "still_uncertain": {"type": "string"}
                },
                "required": [
                    "event_id",
                    "title",
                    "why_top",
                    "judgment_update",
                    "for_me",
                    "still_uncertain"
                ],
                "additionalProperties": False
            }
        },
        "method_asset": {
            "type": "object",
            "properties": {
                "asset_name": {"type": "string"},
                "why_now": {"type": "string"},
                "next_step": {"type": "string"}
            },
            "required": ["asset_name", "why_now", "next_step"],
            "additionalProperties": False
        },
        "actions": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["headline", "overview", "top_items", "method_asset", "actions"],
    "additionalProperties": False
}

BRIEF_INSTRUCTIONS = """
生成 Evidence-first Daily Intelligence。

不要再写长篇抽象判断。最多3条。

每条内容必须：
1. 明确为什么能进入Top 3：因为有了什么新证据，而不是观点听起来正确；
2. 判断更新必须由具体证据支持；
3. 不确定性必须真实存在；
4. 如果事件证据密度低，就不要选。

日报只负责快速扫读。
更完整的事实、数字、机制、案例过程和原文入口，会放在对应detail页面。
"""

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

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
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def feed_text(entry):
    parts = []
    if entry.get("title"):
        parts.append(entry.get("title"))
    if entry.get("summary"):
        parts.append(clean_html(entry.get("summary")))
    for content in entry.get("content", []):
        value = content.get("value", "")
        if value:
            parts.append(clean_html(value))
    return "\n\n".join(x for x in parts if x).strip()


def fetch_article_text(url):
    if not url:
        return ""
    try:
        req = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 PersonalIntelligenceBot/0.4.1"
            }
        )
        with urlopen(req, timeout=12) as response:
            raw = response.read(800000).decode("utf-8", errors="ignore")
        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.decompose()

        article = soup.find("article") or soup.find("main") or soup.body
        text = clean_html(str(article)) if article else ""
        return text[:ARTICLE_CHAR_LIMIT]
    except Exception as exc:
        print(f"[WARN] 无法读取原网页，回退到RSS内容: {url} | {exc}")
        return ""


def get_source_material(entry):
    rss = feed_text(entry)
    page = ""

    # RSS/Atom内容太短时尝试读取原网页；足够长也可补充网页，但只保留限定长度。
    if len(rss) < 6000:
        page = fetch_article_text(entry.get("link", ""))

    best = page if len(page) > len(rss) else rss
    return {
        "rss_text": rss[:ARTICLE_CHAR_LIMIT],
        "page_text": page[:ARTICLE_CHAR_LIMIT],
        "analysis_text": best[:ARTICLE_CHAR_LIMIT],
        "source_depth": (
            "full_page_or_long_feed" if len(best) >= 5000
            else "partial_feed_or_excerpt"
        )
    }


def calculate_pis(scores):
    total = sum(scores.values())

    # 具体性/证据密度硬性约束，防止“正确废话”拿高分。
    specificity = scores["specificity"]
    evidence_density = scores["evidence_density"]

    if specificity < 6 and evidence_density < 6:
        return min(total, 49)
    if specificity < 8 or evidence_density < 8:
        return min(total, 64)

    return total


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


def safe_slug(value):
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def analyze(client, source, entry, material):
    prompt = f"""
来源：{source.get('name', '')}
原始链接：{entry.get('link', '')}
发布时间：{entry.get('published', entry.get('updated', ''))}
内容深度：{material['source_depth']}

以下是系统当前能获取到的原始材料。
如果只是RSS摘要，请明确证据有限，不要假装读到了全文。

--- 原始材料开始 ---
{material['analysis_text']}
--- 原始材料结束 ---
"""

    response = client.responses.create(
        model=MODEL,
        instructions=INSTRUCTIONS,
        input=prompt,
        text={
            "format": {
                "type": "json_schema",
                "name": "evidence_first_item_v041",
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

    action = raw["action_type"] if keep else "IGNORE"

    # 没有任何证据的文章直接Drop。
    evidence = raw["evidence"]
    evidence_count = (
        len(evidence["concrete_facts"])
        + len(evidence["numbers_metrics"])
        + len(evidence["mechanism_steps"])
    )
    if evidence_count == 0:
        keep = False
        pis = min(pis, 49)
        tier = "Drop"
        action = "IGNORE"

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
        "evidence": raw["evidence"],
        "claim_map": raw["claim_map"],
        "relation_to_me": raw["relation_to_me"],
        "why_read_original": raw["why_read_original"],
        "original_reading_focus": raw["original_reading_focus"],
        "information_type": raw["information_type"],
        "action_type": action,
        "confidence": raw["confidence"],
        "counterpoint": raw["counterpoint"],
        "asset_type": raw["asset_type"],
        "drop_reason": raw["drop_reason"],
        "source_depth": material["source_depth"]
    }

# ---------------------------------------------------------------------
# Detail pages
# ---------------------------------------------------------------------

def render_detail_page(item):
    a = item["analysis"]
    ev = a["evidence"]
    cm = a["claim_map"]
    case = ev["case_details"]

    lines = [
        f"# {a['title_zh']}",
        "",
        f"> **PIS {a['pis']}｜{a['tier']}｜{a['knowledge_domain']}｜{a['confidence']}**",
        "",
        f"原文：[{item.get('title_original','打开原文')}]({item.get('url','')})",
        "",
        f"来源：{item.get('source_name','')}  ",
        f"发布时间：{item.get('published','')}  ",
        f"材料完整度：{a.get('source_depth','')}",
        "",
        "## 1｜这篇内容真正提供了什么",
        "",
        a["summary_zh"],
        "",
        f"**判断：** {a['core_judgment']}",
        "",
        "## 2｜关键证据",
        ""
    ]

    if ev["concrete_facts"]:
        lines += ["### 具体事实", ""]
        lines += [f"- {x}" for x in ev["concrete_facts"]]
        lines.append("")

    if ev["numbers_metrics"]:
        lines += ["### 数字与指标", ""]
        lines += [f"- **{x}**" for x in ev["numbers_metrics"]]
        lines.append("")

    if ev["mechanism_steps"]:
        lines += ["### 机制 / 过程", ""]
        lines += [f"{i}. {x}" for i, x in enumerate(ev["mechanism_steps"], 1)]
        lines.append("")

    lines += [
        "## 3｜案例过程",
        "",
        f"**主体：** {case['actor']}",
        "",
        f"**背景：** {case['context']}",
        "",
        f"**原问题：** {case['problem']}",
        "",
        f"**AI如何介入：** {case['ai_intervention']}",
        "",
        f"**流程发生了什么变化：** {case['workflow_change']}",
        "",
        f"**人的角色：** {case['human_role']}",
        "",
        f"**结果：** {case['outcome']}",
        "",
        f"**失败 / 限制：** {case['failure_limits']}",
        "",
        "## 4｜事实、解释与推断分开看",
        "",
        "### 原文明示/报告的事实"
    ]

    lines += [f"- {x}" for x in cm["confirmed_or_reported_facts"]] or ["- 原文未提供足够事实。"]
    lines += ["", "### 作者的解释"]
    lines += [f"- {x}" for x in cm["author_interpretations"]] or ["- 无明确作者解释。"]
    lines += ["", "### 系统基于材料做的推断"]
    lines += [f"- {x}" for x in cm["model_inferences"]] or ["- 无额外推断。"]
    lines += ["", "### 仍然不知道什么"]
    lines += [f"- {x}" for x in cm["unknowns"]] or ["- 暂无。"]

    lines += [
        "",
        "## 5｜为什么与你有关",
        "",
        f"**当前工作：** {a['relation_to_me']['current_work']}",
        "",
        f"**专家成长：** {a['relation_to_me']['expert_growth']}",
        "",
        f"**长期价值：** {a['relation_to_me']['long_term_value']}",
        "",
        "## 6｜要不要看原文",
        "",
        a["why_read_original"],
        ""
    ]

    if a["original_reading_focus"]:
        lines += ["### 打开原文后重点找这些", ""]
        lines += [f"- {x}" for x in a["original_reading_focus"]]
        lines.append("")

    lines += [
        f"**[→ 打开原始材料]({item.get('url','')})**",
        "",
        "## 7｜反方与限制",
        "",
        a["counterpoint"]
    ]

    return "\n".join(lines)


def write_detail_page(item):
    DETAILS_DIR.mkdir(parents=True, exist_ok=True)
    filename = safe_slug(item["id"]) + ".md"
    path = DETAILS_DIR / filename
    path.write_text(render_detail_page(item), encoding="utf-8")
    return f"details/{filename}"

# ---------------------------------------------------------------------
# Event clustering helpers
# ---------------------------------------------------------------------

def make_event_id(member_ids):
    raw = "|".join(sorted(member_ids)).encode("utf-8")
    return "evt_" + hashlib.sha1(raw).hexdigest()[:12]


def cluster_candidate_items(items):
    candidates = []
    for item in items:
        a = item.get("analysis", {})
        if a.get("keep") and a.get("pis", 0) >= 50:
            candidates.append(item)
    return candidates[-CLUSTER_MAX_ITEMS:]


def singleton_event(item):
    a = item["analysis"]
    facts = a["evidence"]["concrete_facts"][:4]
    nums = a["evidence"]["numbers_metrics"][:3]

    return {
        "event_id": make_event_id([item["id"]]),
        "event_title": a["title_zh"],
        "event_type": "独立内容",
        "knowledge_domain": a["knowledge_domain"],
        "member_ids": [item["id"]],
        "member_count": 1,
        "source_names": [item.get("source_name", "")],
        "source_count": 1,
        "is_cross_source": False,
        "event_pis": a["pis"],
        "event_tier": a["tier"],
        "combined_summary": a["summary_zh"],
        "combined_judgment": a["core_judgment"],
        "why_it_matters": a["why_it_matters"],
        "key_evidence": facts + nums,
        "contradictions": a["counterpoint"],
        "confidence": a["confidence"],
        "recommended_action": a["action_type"],
        "unique_contributions": [{
            "item_id": item["id"],
            "source_name": item.get("source_name", ""),
            "source_role": "其他",
            "unique_contribution": a["core_judgment"]
        }]
    }


def build_cluster_payload(items):
    payload = []
    for item in items:
        a = item["analysis"]
        payload.append({
            "id": item["id"],
            "source_name": item.get("source_name", ""),
            "title_zh": a["title_zh"],
            "pis": a["pis"],
            "knowledge_domain": a["knowledge_domain"],
            "summary": a["summary_zh"],
            "judgment": a["core_judgment"],
            "concrete_facts": a["evidence"]["concrete_facts"][:5],
            "numbers_metrics": a["evidence"]["numbers_metrics"][:5],
            "mechanism_steps": a["evidence"]["mechanism_steps"][:5]
        })
    return payload


def cluster_items(client, items):
    candidates = cluster_candidate_items(items)
    if not candidates:
        return []
    if len(candidates) == 1:
        return [singleton_event(candidates[0])]

    payload = build_cluster_payload(candidates)
    valid_ids = {x["id"] for x in payload}
    item_map = {x["id"]: x for x in candidates}

    response = client.responses.create(
        model=MODEL,
        instructions=CLUSTER_INSTRUCTIONS,
        input=json.dumps(payload, ensure_ascii=False),
        text={
            "format": {
                "type": "json_schema",
                "name": "evidence_event_clusters_v041",
                "strict": True,
                "schema": CLUSTER_SCHEMA
            }
        },
        store=False
    )
    raw = json.loads(response.output_text)

    events = []
    assigned = set()

    for c in raw["clusters"]:
        member_ids = [x for x in c["member_ids"] if x in valid_ids and x not in assigned]
        if not member_ids:
            continue
        assigned.update(member_ids)

        member_items = [item_map[x] for x in member_ids]
        sources = []
        scores = []
        for item in member_items:
            source = item.get("source_name", "")
            if source and source not in sources:
                sources.append(source)
            scores.append(item["analysis"]["pis"])

        contributions = []
        for uc in c["unique_contributions"]:
            iid = uc["item_id"]
            if iid in member_ids:
                contributions.append({
                    "item_id": iid,
                    "source_name": item_map[iid].get("source_name", ""),
                    "source_role": uc["source_role"],
                    "unique_contribution": uc["unique_contribution"]
                })

        event_pis = max(scores) if scores else 0
        events.append({
            "event_id": make_event_id(member_ids),
            "event_title": c["event_title"],
            "event_type": c["event_type"],
            "knowledge_domain": c["knowledge_domain"],
            "member_ids": member_ids,
            "member_count": len(member_ids),
            "source_names": sources,
            "source_count": len(sources),
            "is_cross_source": len(sources) >= 2,
            "event_pis": event_pis,
            "event_tier": get_tier(event_pis),
            "combined_summary": c["combined_summary"],
            "combined_judgment": c["combined_judgment"],
            "why_it_matters": c["why_it_matters"],
            "key_evidence": c["key_evidence"],
            "contradictions": c["contradictions"],
            "confidence": c["confidence"],
            "recommended_action": c["recommended_action"],
            "unique_contributions": contributions
        })

    for item in candidates:
        if item["id"] not in assigned:
            events.append(singleton_event(item))

    events.sort(key=lambda x: x["event_pis"], reverse=True)
    return events


def attach_event_metadata(items, events):
    lookup = {}
    for event in events:
        for iid in event["member_ids"]:
            lookup[iid] = {
                "event_id": event["event_id"],
                "event_title": event["event_title"],
                "event_type": event["event_type"],
                "cluster_size": event["member_count"],
                "is_cross_source": event["is_cross_source"]
            }
    for item in items:
        if item["id"] in lookup:
            item["event"] = lookup[item["id"]]

# ---------------------------------------------------------------------
# Themes
# ---------------------------------------------------------------------

def build_themes(client, events):
    if len(events) < 2:
        return []

    payload = [{
        "event_id": e["event_id"],
        "event_title": e["event_title"],
        "knowledge_domain": e["knowledge_domain"],
        "combined_judgment": e["combined_judgment"],
        "key_evidence": e.get("key_evidence", [])[:5],
        "event_pis": e["event_pis"]
    } for e in events[-30:]]

    response = client.responses.create(
        model=MODEL,
        instructions=THEME_INSTRUCTIONS,
        input=json.dumps(payload, ensure_ascii=False),
        text={
            "format": {
                "type": "json_schema",
                "name": "research_themes_v041",
                "strict": True,
                "schema": THEME_SCHEMA
            }
        },
        store=False
    )
    result = json.loads(response.output_text)
    valid_ids = {e["event_id"] for e in events}

    themes = []
    for t in result["themes"]:
        related = [x for x in t["related_event_ids"] if x in valid_ids]
        if len(related) < 2:
            continue
        t["theme_id"] = "theme_" + hashlib.sha1("|".join(sorted(related)).encode()).hexdigest()[:12]
        t["related_event_ids"] = related
        t["related_event_count"] = len(related)
        themes.append(t)
    return themes

# ---------------------------------------------------------------------
# Daily Brief
# ---------------------------------------------------------------------

def select_brief_events(events):
    eligible = [e for e in events if e["event_tier"] in ("Immediate", "Daily", "Weekly")]
    eligible.sort(key=lambda x: x["event_pis"], reverse=True)
    return eligible[:BRIEF_MAX_EVENTS]


def build_brief_payload(events):
    return [{
        "event_id": e["event_id"],
        "event_title": e["event_title"],
        "event_pis": e["event_pis"],
        "event_tier": e["event_tier"],
        "knowledge_domain": e["knowledge_domain"],
        "key_evidence": e.get("key_evidence", [])[:6],
        "combined_judgment": e["combined_judgment"],
        "contradictions": e["contradictions"],
        "source_names": e["source_names"]
    } for e in select_brief_events(events)]


def render_brief(brief, events, items):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    event_map = {e["event_id"]: e for e in events}
    item_map = {i["id"]: i for i in items}

    lines = [
        f"# Evidence-first Daily Intelligence｜{today}",
        "",
        f"> **{brief['headline']}**",
        "",
        brief["overview"],
        "",
        "## 01｜今天最多看这3条",
        ""
    ]

    for idx, top in enumerate(brief["top_items"][:3], 1):
        e = event_map.get(top["event_id"])
        if not e:
            continue

        lines += [
            f"### {idx}. {top['title']}",
            "",
            f"**为什么进入Top 3**  \n{top['why_top']}",
            "",
            "**最关键的证据**"
        ]
        for evidence in e.get("key_evidence", [])[:5]:
            lines.append(f"- {evidence}")

        lines += [
            "",
            f"**我该更新什么判断**  \n{top['judgment_update']}",
            "",
            f"**对我有什么实际价值**  \n{top['for_me']}",
            "",
            f"**还不能确认什么**  \n{top['still_uncertain']}",
            ""
        ]

        member_items = [item_map[iid] for iid in e["member_ids"] if iid in item_map]
        for item in member_items:
            detail_path = item.get("detail_path")
            title = item.get("title_original", "原始材料")
            url = item.get("url", "")
            if detail_path:
                lines.append(f"- [展开证据卡：{item.get('source_name','')}](./{detail_path})")
            if url:
                lines.append(f"- [打开原文：{title}]({url})")
        lines.append("")

    asset = brief["method_asset"]
    lines += [
        "## 02｜今天最值得沉淀的一个方法",
        "",
        f"### {asset['asset_name']}",
        "",
        f"**为什么现在值得做：** {asset['why_now']}",
        "",
        f"**最小下一步：** {asset['next_step']}",
        "",
        "## 03｜我今天可以做什么",
        ""
    ]
    for action in brief["actions"][:3]:
        lines.append(f"- {action}")

    lines += [
        "",
        "---",
        "",
        "> 使用方式：先扫Top 3；只有当关键证据真正与你相关时，再点“展开证据卡”或原文。"
    ]
    return "\n".join(lines)


def fallback_brief(events, items):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    item_map = {i["id"]: i for i in items}
    lines = [f"# Evidence-first Daily Intelligence｜{today}", "", "## 今天最高价值事件", ""]
    for e in select_brief_events(events)[:3]:
        lines += [f"### {e['event_title']}", ""]
        for x in e.get("key_evidence", [])[:5]:
            lines.append(f"- {x}")
        lines += ["", f"**判断：** {e['combined_judgment']}", ""]
        for iid in e["member_ids"]:
            item = item_map.get(iid)
            if item:
                if item.get("detail_path"):
                    lines.append(f"- [展开证据卡](./{item['detail_path']})")
                lines.append(f"- [原文]({item.get('url','')})")
        lines.append("")
    return "\n".join(lines)


def generate_daily_brief(client, events, items):
    payload = build_brief_payload(events)
    if not payload:
        return fallback_brief(events, items)

    try:
        response = client.responses.create(
            model=MODEL,
            instructions=BRIEF_INSTRUCTIONS,
            input=json.dumps(payload, ensure_ascii=False),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "evidence_daily_brief_v041",
                    "strict": True,
                    "schema": BRIEF_SCHEMA
                }
            },
            store=False
        )
        brief = json.loads(response.output_text)
        return render_brief(brief, events, items)
    except Exception as exc:
        print(f"[WARN] Brief生成失败，使用降级版: {exc}")
        return fallback_brief(events, items)

# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def collect_candidates(sources, processed):
    queues = []

    for source in sources:
        feed = feedparser.parse(source["url"])
        if getattr(feed, "bozo", False):
            print(f"[WARN] Feed解析异常: {source.get('name','')} | {feed.bozo_exception}")

        queue = []
        for entry in feed.entries:
            uid = entry.get("id") or entry.get("link") or entry.get("title")
            if uid and uid not in processed:
                queue.append((source, entry, uid))
        if queue:
            queues.append(queue)

    candidates = []
    round_index = 0
    while len(candidates) < MAX_NEW_ITEMS:
        added = False
        for queue in queues:
            if round_index < len(queue):
                candidates.append(queue[round_index])
                added = True
                if len(candidates) >= MAX_NEW_ITEMS:
                    break
        if not added:
            break
        round_index += 1

    return candidates


def main(mode="daily"):
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("缺少 OPENAI_API_KEY")

    client = OpenAI()

    if mode == "weekly":
        events = load_json(EVENTS_PATH, [])
        old_themes = load_json(THEMES_PATH, [])
        try:
            themes = build_themes(client, events)
            save_json(THEMES_PATH, themes)
            print(f"Weekly themes: {len(themes)}")
        except Exception as exc:
            print(f"[WARN] Weekly主题聚类失败，保留旧结果: {exc}")
            save_json(THEMES_PATH, old_themes)
        return

    sources = load_json(SOURCES_PATH, [])
    items = load_json(ITEMS_PATH, [])
    processed = set(load_json(PROCESSED_PATH, []))

    candidates = collect_candidates(sources, processed)
    print(f"本次处理 {len(candidates)} 条新内容。")

    run_time = datetime.now(timezone.utc).isoformat()

    for source, entry, uid in candidates:
        print(f"读取: {entry.get('title','(无标题)')}")
        material = get_source_material(entry)

        try:
            analysis = analyze(client, source, entry, material)
        except Exception as exc:
            print(f"[ERROR] 分析失败，跳过: {exc}")
            continue

        item = {
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

        item["detail_path"] = write_detail_page(item)
        items.append(item)
        processed.add(uid)

        print(
            f"  -> PIS {analysis['pis']} / {analysis['tier']} | "
            f"具体性 {analysis['scores']['specificity']} | "
            f"证据密度 {analysis['scores']['evidence_density']}"
        )

    old_events = load_json(EVENTS_PATH, [])
    try:
        events = cluster_items(client, items)
        attach_event_metadata(items, events)
    except Exception as exc:
        print(f"[WARN] 事件聚类失败，保留旧结果: {exc}")
        events = old_events

    # 为已有V0.4.1项目补写detail页。
    for item in items:
        if item.get("analysis", {}).get("analysis_version") == ANALYSIS_VERSION and not item.get("detail_path"):
            item["detail_path"] = write_detail_page(item)

    brief = generate_daily_brief(client, events, items)

    save_json(ITEMS_PATH, items)
    save_json(PROCESSED_PATH, sorted(processed))
    save_json(EVENTS_PATH, events)
    DAILY_BRIEF_PATH.write_text(brief, encoding="utf-8")

    print(
        f"完成：{len(items)}条内容，{len(events)}个事件，"
        f"Brief与证据卡已更新。"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["daily", "weekly"], default="daily")
    args = parser.parse_args()
    main(args.mode)
