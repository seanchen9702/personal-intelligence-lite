# Personal Intelligence System V0.5 Collector Alpha
# Multi-source collector: RSS / Atom / Index Page + Evidence-first analysis.

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import feedparser
from bs4 import BeautifulSoup
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = ROOT / "config" / "sources.json"
USER_PROFILE_PATH = ROOT / "config" / "user_profile.json"
ITEMS_PATH = ROOT / "data" / "items.json"
PROCESSED_PATH = ROOT / "data" / "processed.json"
EVENTS_PATH = ROOT / "data" / "events.json"
THEMES_PATH = ROOT / "data" / "themes.json"
DAILY_BRIEF_PATH = ROOT / "data" / "daily_brief.md"
DETAILS_DIR = ROOT / "data" / "details"

ANALYSIS_VERSION = "v0.6.1-personal"
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

MAX_NEW_ITEMS = int(os.getenv("MAX_NEW_ITEMS", "6"))
CLUSTER_MAX_ITEMS = int(os.getenv("CLUSTER_MAX_ITEMS", "15"))
BRIEF_MAX_EVENTS = int(os.getenv("BRIEF_MAX_EVENTS", "5"))
ARTICLE_CHAR_LIMIT = int(os.getenv("ARTICLE_CHAR_LIMIT", "18000"))
INDEX_MAX_LINKS = int(os.getenv("INDEX_MAX_LINKS", "30"))

USER_AGENT = "Mozilla/5.0 PersonalIntelligenceBot/0.5"

# ---------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------

ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "object",
            "properties": {
                "strategic_relevance": {"type": "integer", "minimum": 0, "maximum": 20},
                "practical_value": {"type": "integer", "minimum": 0, "maximum": 15},
                "cognitive_upgrade": {"type": "integer", "minimum": 0, "maximum": 15},
                "personal_asset_value": {"type": "integer", "minimum": 0, "maximum": 10},
                "information_quality": {"type": "integer", "minimum": 0, "maximum": 10},
                "specificity": {"type": "integer", "minimum": 0, "maximum": 15},
                "evidence_density": {"type": "integer", "minimum": 0, "maximum": 15}
            },
            "required": [
                "strategic_relevance",
                "practical_value",
                "cognitive_upgrade",
                "personal_asset_value",
                "information_quality",
                "specificity",
                "evidence_density"
            ],
            "additionalProperties": False
        },
        "knowledge_domain": {
            "type": "string",
            "enum": [
                "企业AI深度应用",
                "AI能力与技术演进",
                "组织与人才发展",
                "管理与领导力",
                "商业与创业机会",
                "未来社会与科技",
                "文明与旅行研究",
                "个人成长与工作系统",
                "其他高价值信息"
            ]
        },
        "title_zh": {"type": "string"},
        "summary_zh": {"type": "string"},
        "core_judgment": {"type": "string"},
        "why_it_matters": {"type": "string"},

        "evidence_types_detected": {
            "type": "array",
            "items": {"type": "string"}
        },

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

        "evidence_card": {
            "type": "object",
            "properties": {
                "basic": {
                    "type": "object",
                    "properties": {
                        "domain": {"type": "string"},
                        "topic": {"type": "string"},
                        "source_quality": {"type": "string", "enum": ["high", "medium", "low"]}
                    },
                    "required": ["domain", "topic", "source_quality"],
                    "additionalProperties": False
                },
                "facts": {"type": "array", "items": {"type": "string"}},
                "data_points": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "metric": {"type": "string"},
                            "value": {"type": "string"},
                            "context": {"type": "string"}
                        },
                        "required": ["metric", "value", "context"],
                        "additionalProperties": False
                    }
                },
                "cases": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "actor": {"type": "string"},
                            "context": {"type": "string"},
                            "action": {"type": "string"},
                            "result": {"type": "string"},
                            "limitation": {"type": "string"}
                        },
                        "required": ["actor", "context", "action", "result", "limitation"],
                        "additionalProperties": False
                    }
                },
                "interpretation": {
                    "type": "object",
                    "properties": {
                        "author_view": {"type": "string"},
                        "my_inference": {"type": "string"},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]}
                    },
                    "required": ["author_view", "my_inference", "confidence"],
                    "additionalProperties": False
                },
                "mechanism": {
                    "type": "object",
                    "properties": {
                        "trigger": {"type": "string"},
                        "how_it_works": {"type": "string"},
                        "behavior_or_work_change": {"type": "string"},
                        "organization_or_system_change": {"type": "string"}
                    },
                    "required": [
                        "trigger",
                        "how_it_works",
                        "behavior_or_work_change",
                        "organization_or_system_change"
                    ],
                    "additionalProperties": False
                },
                "uncertainties": {"type": "array", "items": {"type": "string"}},
                "research_questions": {"type": "array", "items": {"type": "string"}}
            },
            "required": [
                "basic",
                "facts",
                "data_points",
                "cases",
                "interpretation",
                "mechanism",
                "uncertainties",
                "research_questions"
            ],
            "additionalProperties": False
        },

        "personal_connection": {
            "type": "object",
            "properties": {
                "current_work": {"type": "string"},
                "career_growth": {"type": "string"},
                "future_opportunity": {"type": "string"},
                "personal_interest": {"type": "string"},
                "possible_asset": {"type": "string"}
            },
            "required": [
                "current_work",
                "career_growth",
                "future_opportunity",
                "personal_interest",
                "possible_asset"
            ],
            "additionalProperties": False
        },

        "asset_potential": {
            "type": "object",
            "properties": {
                "should_build": {"type": "boolean"},
                "asset_type": {
                    "type": "string",
                    "enum": [
                        "方法论",
                        "案例库",
                        "趋势判断",
                        "机会池",
                        "内容素材",
                        "旅行/文明知识",
                        "个人工作系统",
                        "暂不沉淀"
                    ]
                },
                "asset_name": {"type": "string"},
                "reason": {"type": "string"},
                "next_step": {"type": "string"}
            },
            "required": [
                "should_build",
                "asset_type",
                "asset_name",
                "reason",
                "next_step"
            ],
            "additionalProperties": False
        },

        "belief_status": {
            "type": "string",
            "enum": ["L0信息", "L1信号", "L2假设", "L3方法论候选", "L4资产候选"]
        },

        # Compatibility fields used by the existing downstream pipeline.
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
        "evidence_types_detected",
        "evidence",
        "claim_map",
        "evidence_card",
        "personal_connection",
        "asset_potential",
        "belief_status",
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


ITEM_INSTRUCTIONS = """
你是我的 Personal Intelligence Advisor（个人认知资产助手）。

你的任务不是把所有材料都解释成“企业AI”，也不是做普通新闻摘要。
你的任务是帮助我持续建立可复用、可验证、能够支持职业发展与未来选择的长期认知资产。

【分析对象】
首先根据材料本身判断最合适的知识领域：
- 企业AI深度应用
- AI能力与技术演进
- 组织与人才发展
- 管理与领导力
- 商业与创业机会
- 未来社会与科技
- 文明与旅行研究
- 个人成长与工作系统
- 其他高价值信息

企业AI深度应用是当前最重要的战略研究方向，但不是唯一方向。
不要为了贴合主要方向，强行把其他有价值的信息解释成AI、HR或组织问题。

【使用个人画像】
输入中会提供 user_profile。
它用于判断“对我是否重要”，而不是限制“什么可以进入系统”。
如果材料对我的主要职业方向价值一般，但对长期兴趣、文明旅行、商业机会、个人成长或其他长期资产有明显价值，仍可保留并正确分类。

【分析顺序】
必须按以下顺序工作：
1. 识别领域与主题；
2. 提取证据；
3. 区分事实、作者观点、你的推断；
4. 解释作用机制；
5. 判断与个人目标的连接；
6. 判断是否值得沉淀为长期资产；
7. 最后才评分。

【Evidence-first原则】
先证据，后判断。

如果去掉名称、数字、具体动作、流程、机制、案例和限制后，只剩类似：
“AI会改变工作”
“企业要重视治理”
“管理者需要变化”
“未来充满机会”
这类正确但没有信息增量的话，必须显著降分。

【评分固定100分】
- strategic_relevance 0-20：
  对 user_profile 中主要研究方向、职业发展或长期兴趣的重要程度。
  企业AI通常权重最高，但高价值的组织、管理、商业、文明、未来社会或个人成长内容同样可以获得高分。

- practical_value 0-15：
  能否转化为实际行动、实验、设计、决策、项目或观察方法。

- cognitive_upgrade 0-15：
  是否真正改变、补充或校准现有判断，而不是重复常识。

- personal_asset_value 0-10：
  是否有潜力沉淀为方法论、案例库、趋势判断、机会池、内容素材、旅行/文明知识或个人工作系统。

- information_quality 0-10：
  来源可信度、证据质量和论证完整度。

- specificity 0-15：
  是否有明确人物/机构/对象/动作/过程/机制/结果。

- evidence_density 0-15：
  是否包含足够事实、数据、案例、机制和限制，而不是概念性评论。

【证据要求】
evidence 与 evidence_card 必须基于原材料：
- facts / concrete_facts：只写材料明确支持的事实；
- data_points / numbers_metrics：没有数字就返回空数组，禁止补造；
- cases：没有案例就返回空数组；
- mechanism：解释“为什么会产生这个结果”，不能只重复结论；
- claim_map：严格区分事实、作者解释、模型推断和未知；
- uncertainties：主动指出证据边界；
- research_questions：提出真正值得后续验证的问题，不要生成空泛问题。

对于非AI内容：
evidence.case_details 中 ai_intervention、workflow_change、human_role 如确实不适用，
请写“非AI主题，不适用”或依据材料填写对应的一般机制，不要强行AI化。

【个人连接】
personal_connection 五个维度分别判断：
- current_work：是否能帮助当前工作；
- career_growth：是否帮助未来职业竞争力；
- future_opportunity：是否指向新机会；
- personal_interest：是否满足重要的长期兴趣与认知建设；
- possible_asset：最可能沉淀成什么。

如果某维度无明显关系，直接写“无明显直接关系”，不要硬关联。

【资产判断】
asset_potential：
只有当材料提供足够独特证据、可复用机制或长期价值时，should_build 才为 true。
不要每篇文章都建议做框架。
asset_name 必须具体，例如：
“Agent人工升级触发条件案例库”
而不是：
“AI方法论”。

belief_status：
- L0信息：知道即可；
- L1信号：值得继续观察；
- L2假设：形成了待验证判断；
- L3方法论候选：已经能抽象出可复用机制；
- L4资产候选：值得持续积累并可能用于工作、输出、咨询或产品。

【兼容字段】
relation_to_me 与 personal_connection 保持语义一致；
asset_type 与 asset_potential 保持语义一致，供现有下游流程继续使用。

若材料只是摘要或列表页内容，必须降低 confidence，并明确材料不完整。
"""

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
                            "企业AI深度应用",
                            "AI能力与技术演进",
                            "组织与人才发展",
                            "管理与领导力",
                            "商业与创业机会",
                            "未来社会与科技",
                            "文明与旅行研究",
                            "个人成长与工作系统",
                            "其他高价值信息"
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
只有同一底层事件、报告、研究、案例、产品发布或实验才合并。
相似主题但底层事实不同，不合并。

不同领域都可以形成事件，不要强行AI化。

聚合时优先保留：
- 明确主体与对象
- 数字、事实和原始证据
- 具体动作与过程
- 技术、行为、管理或制度机制
- 失败、限制、反例和证据缺口

combined_judgment 不能超出成员材料。
"""

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
主题必须是未来值得持续验证的具体研究问题，而不是“Agent趋势”“AI治理”这种宽泛分类。
优先围绕多个事件共享的机制、矛盾或证据缺口形成主题。
"""

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
生成 Personal Intelligence Daily Brief。

目标不是“今天AI发生了什么”，而是：
今天有哪些高质量证据值得更新我的判断、支持我的工作，或进入长期认知资产。

企业AI深度应用是当前首要方向，但不是唯一方向。
组织与人才、管理、商业机会、未来社会、文明旅行、个人成长等高价值内容也可以进入Top 3。

最多3条。
每条必须说明：
- 为什么它有资格进入Top 3；
- 最关键的新证据；
- 它真正改变或补充了什么判断；
- 对我的工作、职业、未来机会、长期兴趣或资产建设有什么实际价值；
- 还有什么不能确认。

优先证据密度高、具体、可验证、有机制或有反例的内容。
不要用宏观口号填满日报。
"""

# ---------------------------------------------------------------------
# Generic helpers
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


def normalize_sources(raw):
    # V0.5 format: {"version": "...", "strategy": {...}, "sources": [...]}
    if isinstance(raw, dict) and isinstance(raw.get("sources"), list):
        return raw.get("strategy", {}), raw["sources"]

    # Backward compatibility with V0.4 list format
    if isinstance(raw, list):
        legacy = []
        for s in raw:
            legacy.append({
                **s,
                "status": "active",
                "source_role": "secondary_interpreter",
                "evidence_class": "interpretation",
                "platform": "rss",
                "language": "EN",
                "knowledge_domains": s.get("topics", []),
                "why_follow": "",
                "expected_evidence": [],
                "crawl": {
                    "method": "rss",
                    "url": s.get("url", ""),
                    "detail_page": True
                },
                "filters": {"include": [], "exclude": []},
                "quality_rules": {
                    "minimum_specificity": 8,
                    "minimum_evidence_density": 8,
                    "prefer_primary_source": False,
                    "require_one_of": []
                },
                "max_items_per_run": 1
            })
        return {}, legacy

    raise ValueError("config/sources.json 格式无法识别")


def http_get(url, timeout=25, max_bytes=1600000, retries=3):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.7",
        "Cache-Control": "no-cache",
    }
    last_exc = None
    for attempt in range(retries):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=timeout) as resp:
                data = resp.read(max_bytes)
                charset = resp.headers.get_content_charset() or "utf-8"
                return data.decode(charset, errors="ignore")
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                print(f"[RETRY] {url} | {attempt + 1}/{retries} | {exc}")
    raise last_exc


def extract_jsonld_article_body(soup):
    bodies = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            raw = tag.string or tag.get_text()
            data = json.loads(raw)
        except Exception:
            continue

        stack = data if isinstance(data, list) else [data]
        while stack:
            obj = stack.pop()
            if isinstance(obj, dict):
                body = obj.get("articleBody")
                if isinstance(body, str) and len(body.strip()) > 200:
                    bodies.append(body.strip())
                graph = obj.get("@graph")
                if isinstance(graph, list):
                    stack.extend(graph)
            elif isinstance(obj, list):
                stack.extend(obj)
    return max(bodies, key=len) if bodies else ""


def fetch_article_text(url):
    if not url:
        return ""
    try:
        raw = http_get(url)
        soup = BeautifulSoup(raw, "html.parser")

        jsonld_body = extract_jsonld_article_body(soup)
        if len(jsonld_body) >= 800:
            return jsonld_body[:ARTICLE_CHAR_LIMIT]

        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
            tag.decompose()

        candidates = [
            soup.find("article"),
            soup.find("main"),
            soup.find(attrs={"role": "main"}),
            soup.body,
        ]
        texts = []
        for node in candidates:
            if node:
                value = clean_html(str(node))
                if value:
                    texts.append(value)

        result = max(texts, key=len) if texts else ""
        return result[:ARTICLE_CHAR_LIMIT]
    except Exception as exc:
        print(f"[WARN] 详情页读取失败: {url} | {exc}")
        return ""


def canonical_url(url):
    try:
        parsed = urlparse(url)
        clean = parsed._replace(fragment="", query="").geturl()
        return clean.rstrip("/")
    except Exception:
        return url


def make_item_id(source_id, url, title):
    raw = f"{source_id}|{canonical_url(url)}|{title}".encode("utf-8")
    return "itm_" + hashlib.sha1(raw).hexdigest()[:16]


def safe_slug(value):
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def text_matches_any(text, terms):
    if not terms:
        return False
    low = (text or "").lower()
    return any((term or "").lower() in low for term in terms if term)


def prefilter_candidate(source, title, url):
    filters = source.get("filters", {})
    includes = filters.get("include", [])
    excludes = filters.get("exclude", [])

    haystack = f"{title} {url}"

    if excludes and text_matches_any(haystack, excludes):
        return False

    # Include规则作为软过滤：
    # 若标题/URL命中则优先；若完全不命中也不直接丢掉，
    # 避免页面标题没有显式关键词导致漏掉好内容。
    return True


# ---------------------------------------------------------------------
# Collectors
# ---------------------------------------------------------------------

def collect_feed_source(source, processed):
    crawl = source.get("crawl", {})
    url = crawl.get("url", "")
    feed = feedparser.parse(url)

    if getattr(feed, "bozo", False):
        print(f"[WARN] Feed解析异常: {source.get('name')} | {feed.bozo_exception}")

    candidates = []
    limit = max(source.get("max_items_per_run", 1) * 5, 5)

    for entry in feed.entries[:limit]:
        link = canonical_url(entry.get("link", ""))
        title = clean_html(entry.get("title", "")).strip()
        published = entry.get("published", entry.get("updated", ""))
        uid = entry.get("id") or make_item_id(source.get("id", ""), link, title)

        if uid in processed:
            continue

        rss_parts = []
        if entry.get("summary"):
            rss_parts.append(clean_html(entry.get("summary")))
        for content in entry.get("content", []):
            value = content.get("value", "")
            if value:
                rss_parts.append(clean_html(value))

        rss_text = "\n\n".join(x for x in rss_parts if x).strip()

        if not prefilter_candidate(source, title, link):
            continue

        candidates.append({
            "id": uid,
            "source": source,
            "title": title,
            "url": link,
            "published": published,
            "discovery_text": rss_text[:ARTICLE_CHAR_LIMIT],
            "discovery_method": crawl.get("method", "rss")
        })

    return candidates


def is_probable_article_link(source, href, text):
    if not href:
        return False

    href = canonical_url(href)
    if href.startswith("mailto:") or href.startswith("javascript:"):
        return False

    crawl = source.get("crawl", {})
    base = crawl.get("url", "")
    scope = crawl.get("link_scope")

    abs_url = urljoin(base, href)
    parsed_base = urlparse(base)
    parsed_link = urlparse(abs_url)

    allowed_hosts = {parsed_base.netloc}
    if source.get("id") == "langchain_blog":
        allowed_hosts.update({"blog.langchain.com", "www.langchain.com", "langchain.com"})
    if parsed_base.netloc and parsed_link.netloc not in allowed_hosts:
        return False

    if scope and source.get("id") != "langchain_blog" and scope not in parsed_link.path:
        return False

    bad_suffixes = (
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg",
        ".pdf", ".zip", ".xml", ".json", ".rss", ".atom"
    )
    if parsed_link.path.lower().endswith(bad_suffixes):
        return False

    if abs_url.rstrip("/") == base.rstrip("/"):
        return False

    visible = (text or "").strip()
    if len(visible) < 4:
        return False

    generic = {"view story", "read more", "learn more", "view more", "read"}
    if visible.lower() in generic:
        # 允许后续从卡片容器恢复标题
        return True

    return True


def recover_card_title(anchor):
    direct = clean_html(anchor.get_text(" ", strip=True)).strip()
    generic = {"view story", "read more", "learn more", "view more", "read"}
    if direct and direct.lower() not in generic and len(direct) >= 8:
        return direct[:300]

    node = anchor
    for _ in range(4):
        node = node.parent
        if not node:
            break
        text = clean_html(node.get_text(" ", strip=True)).strip()
        text = re.sub(r"\s+", " ", text)
        if len(text) >= 20:
            for suffix in ["View story", "Read more", "Learn more"]:
                text = text.replace(suffix, "").strip()
            if len(text) >= 12:
                return text[:300]

    return direct or "Untitled article"


def discover_from_sitemap(source, processed):
    sid = source.get("id")
    sitemap_urls = []
    if sid == "openai_enterprise_customer_stories":
        sitemap_urls = ["https://openai.com/sitemap.xml"]
    elif sid == "mckinsey_quantumblack_ai":
        sitemap_urls = ["https://www.mckinsey.com/sitemap.xml"]

    candidates = []
    for sitemap_url in sitemap_urls:
        try:
            raw = http_get(sitemap_url, timeout=35)
        except Exception as exc:
            print(f"[WARN] Sitemap读取失败: {source.get('name')} | {exc}")
            continue

        # Avoid requiring lxml/xml parser in GitHub Actions.
        # Sitemap XML is simple enough to parse <loc> values directly.
        urls = re.findall(r"<loc>(.*?)</loc>", raw, flags=re.I | re.S)
        urls = [
            BeautifulSoup(x, "html.parser").get_text(strip=True)
            for x in urls
            if x.strip()
        ]

        if not urls:
            print(f"[WARN] Sitemap未解析到URL: {source.get('name')} | {sitemap_url}")
            continue

        for link in urls:
            low = link.lower()
            if sid == "openai_enterprise_customer_stories":
                if "/business/" not in low:
                    continue
                if not any(k in low for k in ["customer", "stories", "customers", "enterprise"]):
                    continue
            elif sid == "mckinsey_quantumblack_ai":
                if "/capabilities/quantumblack/" not in low:
                    continue
                if not any(k in low for k in ["ai", "agent", "gen-ai", "artificial-intelligence"]):
                    continue

            title = link.rstrip("/").split("/")[-1].replace("-", " ").strip().title()
            uid = make_item_id(source.get("id", ""), link, title)
            if uid in processed:
                continue
            candidates.append({
                "id": uid,
                "source": source,
                "title": title,
                "url": canonical_url(link),
                "published": "",
                "discovery_text": "",
                "discovery_method": "sitemap_fallback"
            })
            if len(candidates) >= INDEX_MAX_LINKS:
                return candidates

    return candidates


def collect_index_source(source, processed):
    crawl = source.get("crawl", {})
    index_url = crawl.get("url", "")
    raw = ""

    try:
        raw = http_get(index_url, timeout=35)
    except Exception as exc:
        print(f"[WARN] 列表页读取失败: {source.get('name')} | {exc}")

    if not raw:
        fallback = discover_from_sitemap(source, processed)
        if fallback:
            print(f"[FALLBACK] {source.get('name')}: sitemap发现 {len(fallback)} 条")
        return fallback

    soup = BeautifulSoup(raw, "html.parser")
    seen_urls = set()
    candidates = []

    for a in soup.find_all("a", href=True):
        title = recover_card_title(a)
        href = a.get("href", "")

        if not is_probable_article_link(source, href, title):
            continue

        link = canonical_url(urljoin(index_url, href))
        if link in seen_urls:
            continue
        seen_urls.add(link)

        if not prefilter_candidate(source, title, link):
            continue

        uid = make_item_id(source.get("id", ""), link, title)
        if uid in processed:
            continue

        candidates.append({
            "id": uid,
            "source": source,
            "title": title,
            "url": link,
            "published": "",
            "discovery_text": "",
            "discovery_method": "index_page"
        })

        if len(candidates) >= INDEX_MAX_LINKS:
            break

    # 对“报告中心页”做保底：页面本身就是持续更新的研究资源。
    if not candidates and source.get("id") == "anthropic_economic_index":
        fingerprint = hashlib.sha1(raw[:50000].encode("utf-8", errors="ignore")).hexdigest()[:12]
        uid = f"itm_{source.get('id')}_{fingerprint}"
        if uid not in processed:
            candidates.append({
                "id": uid,
                "source": source,
                "title": "Anthropic Economic Index - latest update",
                "url": index_url,
                "published": "",
                "discovery_text": clean_html(raw)[:ARTICLE_CHAR_LIMIT],
                "discovery_method": "self_page_fallback"
            })

    if not candidates:
        fallback = discover_from_sitemap(source, processed)
        candidates.extend(fallback)

    return candidates


def collect_source(source, processed):
    if source.get("status", "active") != "active":
        return []

    method = source.get("crawl", {}).get("method", "rss")

    if method in ("rss", "atom"):
        return collect_feed_source(source, processed)

    if method == "index_page":
        return collect_index_source(source, processed)

    print(f"[WARN] 尚未支持 crawl.method={method}: {source.get('name')}")
    return []


def choose_candidates(strategy, sources, processed):
    source_queues = []

    for source in sources:
        queue = collect_source(source, processed)
        if queue:
            source_queues.append({
                "source": source,
                "queue": queue,
                "cursor": 0
            })
            print(f"[DISCOVER] {source.get('name')}: {len(queue)} 条候选")
        else:
            print(f"[DISCOVER] {source.get('name')}: 0 条新候选")

    max_total = min(
        MAX_NEW_ITEMS,
        int(strategy.get("max_items_per_day", MAX_NEW_ITEMS))
    )

    if not source_queues or max_total <= 0:
        return []

    target_mix = strategy.get("target_mix", {})
    selected = []
    selected_per_source = {}

    # 第一轮：优先按 evidence_class 的目标配比选
    classes = ["primary_evidence", "builder_operator", "interpretation", "venture"]
    class_targets = {}
    remaining = max_total

    for i, cls in enumerate(classes):
        if i == len(classes) - 1:
            class_targets[cls] = remaining
        else:
            n = round(max_total * float(target_mix.get(cls, 0)))
            n = max(0, min(n, remaining))
            class_targets[cls] = n
            remaining -= n

    def take_from_class(cls, needed):
        nonlocal selected
        if needed <= 0:
            return

        made_progress = True
        while needed > 0 and made_progress and len(selected) < max_total:
            made_progress = False
            for sq in source_queues:
                source = sq["source"]
                if source.get("evidence_class") != cls:
                    continue

                sid = source.get("id", source.get("name", ""))
                source_limit = min(
                    int(strategy.get("max_items_per_source", 1)),
                    int(source.get("max_items_per_run", 1))
                )
                if selected_per_source.get(sid, 0) >= source_limit:
                    continue

                if sq["cursor"] >= len(sq["queue"]):
                    continue

                selected.append(sq["queue"][sq["cursor"]])
                sq["cursor"] += 1
                selected_per_source[sid] = selected_per_source.get(sid, 0) + 1
                needed -= 1
                made_progress = True

                if needed <= 0 or len(selected) >= max_total:
                    break

    for cls in classes:
        take_from_class(cls, class_targets.get(cls, 0))

    # 第二轮：如果目标配比某类缺货，按来源轮转补齐
    made_progress = True
    while len(selected) < max_total and made_progress:
        made_progress = False
        for sq in source_queues:
            source = sq["source"]
            sid = source.get("id", source.get("name", ""))
            source_limit = min(
                int(strategy.get("max_items_per_source", 1)),
                int(source.get("max_items_per_run", 1))
            )
            if selected_per_source.get(sid, 0) >= source_limit:
                continue
            if sq["cursor"] >= len(sq["queue"]):
                continue

            selected.append(sq["queue"][sq["cursor"]])
            sq["cursor"] += 1
            selected_per_source[sid] = selected_per_source.get(sid, 0) + 1
            made_progress = True

            if len(selected) >= max_total:
                break

    return selected


# ---------------------------------------------------------------------
# Evidence analysis
# ---------------------------------------------------------------------

def build_source_material(candidate):
    source = candidate["source"]
    crawl = source.get("crawl", {})
    discovery_text = candidate.get("discovery_text", "")

    page_text = ""
    if crawl.get("detail_page", True):
        page_text = fetch_article_text(candidate.get("url", ""))

    best = page_text if len(page_text) > len(discovery_text) else discovery_text

    # 页面卡片能发现链接但详情页抓取失败时，不再完全静默。
    if not best.strip():
        print(
            f"[WARN] 正文为空: {source.get('name')} | "
            f"{candidate.get('title')} | {candidate.get('url')}"
        )

    return {
        "analysis_text": best[:ARTICLE_CHAR_LIMIT],
        "page_text": page_text[:ARTICLE_CHAR_LIMIT],
        "discovery_text": discovery_text[:ARTICLE_CHAR_LIMIT],
        "source_depth": (
            "full_page_or_long_feed" if len(best) >= 5000
            else "partial_feed_or_excerpt"
        )
    }


def base_pis(scores):
    return sum(scores.values())


def apply_quality_rules(raw, source):
    pis = base_pis(raw["scores"])
    specificity = raw["scores"]["specificity"]
    density = raw["scores"]["evidence_density"]

    # 全局硬约束
    if specificity < 6 and density < 6:
        pis = min(pis, 49)
    elif specificity < 8 or density < 8:
        pis = min(pis, 64)

    # 来源级阈值
    rules = source.get("quality_rules", {})
    min_spec = int(rules.get("minimum_specificity", 0))
    min_density = int(rules.get("minimum_evidence_density", 0))

    if specificity < min_spec or density < min_density:
        pis = min(pis, 64)

    # 来源期望证据校验
    required_types = set(rules.get("require_one_of", []))
    detected = set(raw.get("evidence_types_detected", []))

    if required_types and not (required_types & detected):
        pis = min(pis, 49)

    evidence = raw["evidence"]
    evidence_count = (
        len(evidence["concrete_facts"])
        + len(evidence["numbers_metrics"])
        + len(evidence["mechanism_steps"])
    )
    if evidence_count == 0:
        pis = min(pis, 49)

    return pis


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


def analyze_item(client, candidate, material):
    source = candidate["source"]
    user_profile = load_json(USER_PROFILE_PATH, {})

    source_context = {
        "name": source.get("name"),
        "source_role": source.get("source_role"),
        "evidence_class": source.get("evidence_class"),
        "why_follow": source.get("why_follow"),
        "knowledge_domains": source.get("knowledge_domains", []),
        "expected_evidence": source.get("expected_evidence", []),
        "quality_rules": source.get("quality_rules", {})
    }

    prompt = f"""
【个人画像 user_profile】
{json.dumps(user_profile, ensure_ascii=False, indent=2)}

【来源配置】
{json.dumps(source_context, ensure_ascii=False, indent=2)}

【文章元信息】
标题：{candidate.get('title','')}
原始链接：{candidate.get('url','')}
发布时间：{candidate.get('published','')}
发现方式：{candidate.get('discovery_method','')}
材料完整度：{material.get('source_depth','')}

【当前可获得的原始材料】
--- START ---
{material.get('analysis_text','')}
--- END ---
"""

    response = client.responses.create(
        model=MODEL,
        instructions=ITEM_INSTRUCTIONS,
        input=prompt,
        text={
            "format": {
                "type": "json_schema",
                "name": "personal_intelligence_item_v061",
                "strict": True,
                "schema": ITEM_SCHEMA
            }
        },
        store=False
    )

    raw = json.loads(response.output_text)
    pis = apply_quality_rules(raw, source)
    tier = get_tier(pis)
    keep = pis >= 50

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
        "evidence_types_detected": raw["evidence_types_detected"],
        "evidence": raw["evidence"],
        "claim_map": raw["claim_map"],
        "evidence_card": raw["evidence_card"],
        "personal_connection": raw["personal_connection"],
        "asset_potential": raw["asset_potential"],
        "belief_status": raw["belief_status"],
        "relation_to_me": raw["relation_to_me"],
        "why_read_original": raw["why_read_original"],
        "original_reading_focus": raw["original_reading_focus"],
        "information_type": raw["information_type"],
        "action_type": raw["action_type"] if keep else "IGNORE",
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
    ev = a.get("evidence", {})
    cm = a.get("claim_map", {})
    case = ev.get("case_details", {})
    ec = a.get("evidence_card", {})
    pc = a.get("personal_connection", {})
    ap = a.get("asset_potential", {})

    lines = [
        f"# {a.get('title_zh', item.get('title_original', '未命名内容'))}",
        "",
        f"> **PIS {a.get('pis', 0)}｜{a.get('tier', '')}｜{a.get('knowledge_domain', '')}｜{a.get('confidence', '')}｜{a.get('belief_status', '')}**",
        "",
        f"原文：[{item.get('title_original','打开原文')}]({item.get('url','')})",
        "",
        f"来源：{item.get('source_name','')}  ",
        f"来源角色：{item.get('source_role','')}  ",
        f"证据类别：{item.get('evidence_class','')}  ",
        f"材料完整度：{a.get('source_depth','')}  ",
        "",
        "## 1｜这篇内容真正提供了什么",
        "",
        a.get("summary_zh", ""),
        "",
        f"**核心判断：** {a.get('core_judgment', '')}",
        "",
        "## 2｜认知证据卡",
        ""
    ]

    facts = ec.get("facts", [])
    if facts:
        lines += ["### 事实", ""]
        lines += [f"- {x}" for x in facts]
        lines.append("")

    data_points = ec.get("data_points", [])
    if data_points:
        lines += ["### 数据", ""]
        for x in data_points:
            lines.append(
                f"- **{x.get('metric','')}：{x.get('value','')}**｜{x.get('context','')}"
            )
        lines.append("")

    cases = ec.get("cases", [])
    if cases:
        lines += ["### 案例", ""]
        for x in cases:
            lines += [
                f"- **{x.get('actor','')}**｜{x.get('context','')}",
                f"  - 动作：{x.get('action','')}",
                f"  - 结果：{x.get('result','')}",
                f"  - 限制：{x.get('limitation','')}"
            ]
        lines.append("")

    mechanism = ec.get("mechanism", {})
    lines += [
        "### 作用机制",
        "",
        f"- **触发变化：** {mechanism.get('trigger','')}",
        f"- **如何发生：** {mechanism.get('how_it_works','')}",
        f"- **行为/工作变化：** {mechanism.get('behavior_or_work_change','')}",
        f"- **组织/系统变化：** {mechanism.get('organization_or_system_change','')}",
        "",
        "### 作者观点 vs 我的推断",
        "",
        f"- **作者观点：** {ec.get('interpretation', {}).get('author_view','')}",
        f"- **系统推断：** {ec.get('interpretation', {}).get('my_inference','')}",
        "",
        "### 仍不确定",
        ""
    ]

    uncertainties = ec.get("uncertainties", [])
    lines += [f"- {x}" for x in uncertainties] or ["- 暂无额外不确定性记录。"]

    lines += ["", "### 值得继续追的问题", ""]
    questions = ec.get("research_questions", [])
    lines += [f"- {x}" for x in questions] or ["- 暂无。"]

    lines += [
        "",
        "## 3｜与你的关系",
        "",
        f"**当前工作：** {pc.get('current_work','')}",
        "",
        f"**职业成长：** {pc.get('career_growth','')}",
        "",
        f"**未来机会：** {pc.get('future_opportunity','')}",
        "",
        f"**长期兴趣：** {pc.get('personal_interest','')}",
        "",
        f"**可能沉淀：** {pc.get('possible_asset','')}",
        "",
        "## 4｜资产潜力",
        "",
        f"**是否值得沉淀：** {'是' if ap.get('should_build') else '否'}",
        "",
        f"**资产类型：** {ap.get('asset_type','')}",
        "",
        f"**资产名称：** {ap.get('asset_name','')}",
        "",
        f"**原因：** {ap.get('reason','')}",
        "",
        f"**下一步：** {ap.get('next_step','')}",
        "",
        "## 5｜底层原始证据",
        ""
    ]

    concrete = ev.get("concrete_facts", [])
    if concrete:
        lines += ["### 具体事实", ""]
        lines += [f"- {x}" for x in concrete]
        lines.append("")

    numbers = ev.get("numbers_metrics", [])
    if numbers:
        lines += ["### 数字与指标", ""]
        lines += [f"- **{x}**" for x in numbers]
        lines.append("")

    steps = ev.get("mechanism_steps", [])
    if steps:
        lines += ["### 原文过程 / 机制", ""]
        lines += [f"{i}. {x}" for i, x in enumerate(steps, 1)]
        lines.append("")

    lines += [
        "## 6｜事实、作者解释与模型推断分开看",
        "",
        "### 原文明示/报告的事实"
    ]
    lines += [f"- {x}" for x in cm.get("confirmed_or_reported_facts", [])] or ["- 原文未提供足够事实。"]
    lines += ["", "### 作者的解释"]
    lines += [f"- {x}" for x in cm.get("author_interpretations", [])] or ["- 无明确作者解释。"]
    lines += ["", "### 模型基于材料的推断"]
    lines += [f"- {x}" for x in cm.get("model_inferences", [])] or ["- 无额外推断。"]
    lines += ["", "### 尚未知"]
    lines += [f"- {x}" for x in cm.get("unknowns", [])] or ["- 暂无。"]

    lines += [
        "",
        "## 7｜要不要看原文",
        "",
        a.get("why_read_original", ""),
        ""
    ]

    if a.get("original_reading_focus"):
        lines += ["### 打开原文后重点找这些", ""]
        lines += [f"- {x}" for x in a["original_reading_focus"]]
        lines.append("")

    lines += [
        f"**[→ 打开原始材料]({item.get('url','')})**",
        "",
        "## 8｜反方与限制",
        "",
        a.get("counterpoint", "")
    ]

    return "\n".join(lines)

def write_detail_page(item):
    DETAILS_DIR.mkdir(parents=True, exist_ok=True)
    filename = safe_slug(item["id"]) + ".md"
    path = DETAILS_DIR / filename
    path.write_text(render_detail_page(item), encoding="utf-8")
    return f"details/{filename}"


# ---------------------------------------------------------------------
# Event clustering
# ---------------------------------------------------------------------

def make_event_id(member_ids):
    raw = "|".join(sorted(member_ids)).encode("utf-8")
    return "evt_" + hashlib.sha1(raw).hexdigest()[:12]


def cluster_analysis_view(item):
    a = item.get("analysis", {}) or {}
    evidence = a.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {}

    return {
        "title_zh": a.get("title_zh") or item.get("title_original") or "未命名内容",
        "pis": int(a.get("pis", 0) or 0),
        "tier": a.get("tier") or get_tier(int(a.get("pis", 0) or 0)),
        "knowledge_domain": a.get("knowledge_domain", "企业AI深度应用"),
        "summary_zh": a.get("summary_zh", ""),
        "core_judgment": a.get("core_judgment", ""),
        "why_it_matters": a.get("why_it_matters", ""),
        "counterpoint": a.get("counterpoint", ""),
        "confidence": a.get("confidence", "medium"),
        "action_type": a.get("action_type", "READ"),
        "evidence_types_detected": a.get("evidence_types_detected", []),
        "concrete_facts": evidence.get("concrete_facts", []),
        "numbers_metrics": evidence.get("numbers_metrics", []),
        "mechanism_steps": evidence.get("mechanism_steps", []),
    }


def singleton_event(item):
    a = cluster_analysis_view(item)
    facts = a["concrete_facts"][:4]
    nums = a["numbers_metrics"][:3]

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


def cluster_items(client, items):
    candidates = [
        x for x in items
        if x.get("analysis", {}).get("keep")
        and x.get("analysis", {}).get("pis", 0) >= 50
    ][-CLUSTER_MAX_ITEMS:]

    if not candidates:
        return []
    if len(candidates) == 1:
        return [singleton_event(candidates[0])]

    payload = []
    for item in candidates:
        a = cluster_analysis_view(item)
        payload.append({
            "id": item["id"],
            "source_name": item.get("source_name", ""),
            "title_zh": a["title_zh"],
            "pis": a["pis"],
            "knowledge_domain": a["knowledge_domain"],
            "summary": a["summary_zh"],
            "judgment": a["core_judgment"],
            "evidence_types": a["evidence_types_detected"],
            "concrete_facts": a["concrete_facts"][:5],
            "numbers_metrics": a["numbers_metrics"][:5],
            "mechanism_steps": a["mechanism_steps"][:5]
        })

    response = client.responses.create(
        model=MODEL,
        instructions=CLUSTER_INSTRUCTIONS,
        input=json.dumps(payload, ensure_ascii=False),
        text={
            "format": {
                "type": "json_schema",
                "name": "event_clusters_v05",
                "strict": True,
                "schema": CLUSTER_SCHEMA
            }
        },
        store=False
    )

    raw = json.loads(response.output_text)
    valid_ids = {x["id"] for x in payload}
    item_map = {x["id"]: x for x in candidates}
    assigned = set()
    events = []

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

    user_profile = load_json(USER_PROFILE_PATH, {})

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
                "name": "themes_v05",
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
        t["theme_id"] = "theme_" + hashlib.sha1(
            "|".join(sorted(related)).encode()
        ).hexdigest()[:12]
        t["related_event_ids"] = related
        t["related_event_count"] = len(related)
        themes.append(t)

    return themes


# ---------------------------------------------------------------------
# Daily Brief
# ---------------------------------------------------------------------

def select_brief_events(events):
    eligible = [
        e for e in events
        if e["event_tier"] in ("Immediate", "Daily", "Weekly")
    ]
    eligible.sort(key=lambda x: x["event_pis"], reverse=True)
    return eligible[:BRIEF_MAX_EVENTS]


def generate_daily_brief(client, events, items):
    selected = select_brief_events(events)
    item_map = {i["id"]: i for i in items}
    event_map = {e["event_id"]: e for e in events}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if not selected:
        return (
            f"# Evidence-first Daily Intelligence｜{today}\n\n"
            "今天没有发现达到 Weekly 以上门槛的新事件。\n"
        )

    payload = [{
        "event_id": e["event_id"],
        "event_title": e["event_title"],
        "event_pis": e["event_pis"],
        "event_tier": e["event_tier"],
        "knowledge_domain": e["knowledge_domain"],
        "key_evidence": e.get("key_evidence", [])[:6],
        "combined_judgment": e["combined_judgment"],
        "contradictions": e["contradictions"],
        "source_names": e["source_names"]
    } for e in selected]

    try:
        response = client.responses.create(
            model=MODEL,
            instructions=BRIEF_INSTRUCTIONS,
            input=json.dumps(
                {"user_profile": user_profile, "events": payload},
                ensure_ascii=False
            ),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "daily_brief_v061",
                    "strict": True,
                    "schema": BRIEF_SCHEMA
                }
            },
            store=False
        )
        brief = json.loads(response.output_text)

        lines = [
            f"# Personal Intelligence Brief｜{today}",
            "",
            f"> **{brief['headline']}**",
            "",
            brief["overview"],
            "",
            "## 01｜今天最多看这3条",
            ""
        ]

        for idx, top in enumerate(brief["top_items"][:3], 1):
            event = event_map.get(top["event_id"])
            if not event:
                continue

            lines += [
                f"### {idx}. {top['title']}",
                "",
                f"**为什么进入Top 3**  \n{top['why_top']}",
                "",
                "**最关键的证据**"
            ]

            for evidence in event.get("key_evidence", [])[:5]:
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

            for iid in event["member_ids"]:
                item = item_map.get(iid)
                if not item:
                    continue
                if item.get("detail_path"):
                    lines.append(
                        f"- [展开证据卡：{item.get('source_name','')}]"
                        f"(./{item['detail_path']})"
                    )
                if item.get("url"):
                    lines.append(
                        f"- [打开原文：{item.get('title_original','原始材料')}]"
                        f"({item['url']})"
                    )
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
            "> 使用方式：先看真正改变判断的证据，再决定是否下钻证据卡、原文或沉淀为长期资产。"
        ]

        return "\n".join(lines)

    except Exception as exc:
        print(f"[WARN] Brief生成失败，使用降级版: {exc}")

        lines = [f"# Personal Intelligence Brief｜{today}", ""]
        for event in selected[:3]:
            lines += [f"## {event['event_title']}", ""]
            for x in event.get("key_evidence", [])[:5]:
                lines.append(f"- {x}")
            lines += ["", f"**判断：** {event['combined_judgment']}", ""]
        return "\n".join(lines)


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

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

    raw_sources = load_json(SOURCES_PATH, [])
    strategy, sources = normalize_sources(raw_sources)

    items = load_json(ITEMS_PATH, [])
    processed = set(load_json(PROCESSED_PATH, []))

    candidates = choose_candidates(strategy, sources, processed)

    print("")
    print(f"本次将分析 {len(candidates)} 条内容：")
    for c in candidates:
        print(
            f"- [{c['source'].get('evidence_class')}] "
            f"{c['source'].get('name')} | {c.get('title')} | {c.get('url')}"
        )
    print("")

    run_time = datetime.now(timezone.utc).isoformat()

    for candidate in candidates:
        source = candidate["source"]
        print(f"[READ] {source.get('name')} | {candidate.get('title')}")

        material = build_source_material(candidate)

        if not material["analysis_text"].strip():
            print("[WARN] 无可分析正文，跳过")
            continue

        try:
            analysis = analyze_item(client, candidate, material)
        except Exception as exc:
            print(f"[ERROR] 分析失败，跳过: {exc}")
            continue

        item = {
            "id": candidate["id"],
            "source_id": source.get("id", ""),
            "source_name": source.get("name", ""),
            "source_role": source.get("source_role", ""),
            "evidence_class": source.get("evidence_class", ""),
            "platform": source.get("platform", ""),
            "title_original": candidate.get("title", ""),
            "url": candidate.get("url", ""),
            "published": candidate.get("published", ""),
            "discovery_method": candidate.get("discovery_method", ""),
            "processed_at_utc": run_time,
            "model": MODEL,
            "analysis_version": ANALYSIS_VERSION,
            "analysis": analysis
        }

        item["detail_path"] = write_detail_page(item)
        items.append(item)
        processed.add(candidate["id"])

        print(
            f"  -> PIS {analysis['pis']} / {analysis['tier']} | "
            f"具体性 {analysis['scores']['specificity']} | "
            f"证据密度 {analysis['scores']['evidence_density']} | "
            f"证据类型 {analysis['evidence_types_detected']}"
        )

    old_events = load_json(EVENTS_PATH, [])

    try:
        events = cluster_items(client, items)
        attach_event_metadata(items, events)
    except Exception as exc:
        print(f"[WARN] 事件聚类失败，保留旧结果: {exc}")
        events = old_events

    brief = generate_daily_brief(client, events, items)

    save_json(ITEMS_PATH, items)
    save_json(PROCESSED_PATH, sorted(processed))
    save_json(EVENTS_PATH, events)
    DAILY_BRIEF_PATH.write_text(brief, encoding="utf-8")

    print("")
    print(
        f"完成：累计 {len(items)} 条内容，"
        f"{len(events)} 个事件，Daily Brief 已更新。"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["daily", "weekly"], default="daily")
    args = parser.parse_args()
    main(args.mode)
