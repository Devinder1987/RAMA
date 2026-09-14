"""
ACQS — Architecture Coverage Quality Score (W10a)
--------------------------------------------------
Deterministic Layer-1 scorer: measures how well a MetaGPT system-design
document covers six software quality attributes, on a 0–1 scale.

Each attribute is defined by indicator groups; a group counts as covered
when any of its regex patterns matches the document text.

    a_i  = covered_groups / total_groups          (per attribute)
    ACQS = mean(a_i)                              (unweighted)

Layer 2 (LLM-as-judge, anchored 0–1 rubric) lives in the W10 MAAD rubric;
this module is fully offline and reproducible.

Usage:
    python acqs_scorer.py <design.json> [more docs...]
    python acqs_scorer.py workspace/own_shop/docs/system_design/*.json

RAMA Thesis — Devinder Shuthwal, LJMU 2026
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# ------------------------------------------------------------------ #
#  Indicator lexicon                                                   #
#  attribute -> group -> list of case-insensitive regex patterns       #
# ------------------------------------------------------------------ #

ATTRIBUTE_INDICATORS: Dict[str, Dict[str, List[str]]] = {
    "security": {
        "auth_mechanism":    [r"\bJWT\b", r"JSON Web Token", r"OAuth", r"bearer\s*auth", r"session-based auth"],
        "password_hashing":  [r"bcrypt", r"argon2", r"scrypt", r"password[\s_]?hash", r"salt(ed|ing)?\b"],
        "encryption":        [r"\bTLS\b", r"\bSSL\b", r"HTTPS", r"encrypt(ion|ed)?", r"at[- ]rest"],
        "input_validation":  [r"input validation", r"saniti[sz]", r"SQL injection", r"\bXSS\b", r"\bCSRF\b", r"helmet"],
        "compliance":        [r"GDPR", r"PCI[- ]?DSS", r"HIPAA", r"data protection", r"consent", r"data minimi[sz]ation"],
        "secrets_management":[r"environment variable", r"\benv var", r"dotenv", r"\.env\b", r"secrets? manage", r"vault"],
    },
    "scalability": {
        "horizontal_scaling":[r"horizontal(ly)? scal", r"stateless", r"scale[- ]out"],
        "load_balancer":     [r"load balanc"],
        "caching":           [r"\bcach(e|ing)\b", r"\bRedis\b", r"\bCDN\b", r"memcached"],
        "db_scaling":        [r"replica(tion)?", r"shard", r"partition"],
        "auto_scaling":      [r"auto[- ]?scal"],
        "async_queue":       [r"message queue", r"RabbitMQ", r"\bSQS\b", r"Kafka", r"message broker", r"async(hronous)? (task|process)"],
    },
    "cost": {
        "managed_services":  [r"managed service", r"\bRDS\b", r"ElastiCache", r"managed database"],
        "open_source_rationale": [r"open[- ]source"],
        "sizing":            [r"infra(structure)? siz", r"cost estimate", r"instance type"],
        "serverless_payg":   [r"serverless", r"pay[- ]as[- ]you[- ]go", r"\bLambda\b"],
        "cost_tradeoff":     [r"cost", r"budget", r"cheap(er)?", r"pricing"],
    },
    "performance": {
        "quantified_target": [r"\d[\d,]*\s*[-–]\s*\d[\d,]*\s*concurrent", r"\d+\s*concurrent users",
                              r"\d+\s*ms\b", r"p9[59]", r"response time", r"latency", r"\bRPS\b"],
        "caching_strategy":  [r"\bcach(e|ing)\b", r"\bRedis\b", r"\bCDN\b"],
        "indexing":          [r"index(ing|es)?\b"],
        "connection_pooling":[r"connection pool", r"\bPool\b"],
        "pagination":        [r"pagination", r"lazy load", r"infinite scroll"],
        "async_processing":  [r"async(hronous)?", r"non[- ]blocking", r"background (job|task)"],
    },
    "availability": {
        "redundancy":        [r"failover", r"redundan", r"multi[- ]AZ", r"hot standby"],
        "health_checks":     [r"health check"],
        "backup_recovery":   [r"backup", r"disaster recovery", r"restore"],
        "monitoring":        [r"monitor(ing)?", r"alert(ing)?", r"CloudWatch", r"Prometheus", r"Grafana"],
        "uptime_target":     [r"high availability", r"\buptime\b", r"\bSLA\b", r"99\.\d"],
        "graceful_degradation": [r"graceful", r"circuit breaker", r"rate limit"],
    },
    "modifiability": {
        "layered_architecture": [r"controller", r"service layer", r"layered", r"\bMVC\b"],
        "separation_of_concerns": [r"separation of concerns", r"loose(ly)? coupl", r"modular", r"encapsulat"],
        "api_versioning":    [r"/api/v\d", r"API version", r"\bv1\b"],
        "config_externalisation": [r"config(uration)? file", r"environment variable", r"centrali[sz]ed config", r"config\.js"],
        "evolution_path":    [r"if (the )?requirements? evolve", r"migrat(e|ion) to", r"initially .{0,60}later", r"future", r"swap"],
        "reusable_components": [r"reusable", r"shared (component|utilit)", r"components?/common"],
    },
}


# ------------------------------------------------------------------ #
#  Report                                                              #
# ------------------------------------------------------------------ #

@dataclass
class AttributeScore:
    attribute: str
    score: float                          # covered / total, 0–1
    covered: Dict[str, str]               # group -> first matched evidence
    missing: List[str]                    # groups with no match


@dataclass
class ACQSReport:
    acqs: float                           # mean of attribute scores
    attributes: Dict[str, AttributeScore]
    sources: List[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "=" * 66,
            " ACQS — Architecture Coverage Quality Score  (Layer 1, keyword)",
            "=" * 66,
            f" Sources: {', '.join(Path(s).name for s in self.sources)}",
            "",
        ]
        for name, a in self.attributes.items():
            bar = "█" * round(a.score * 20) + "░" * (20 - round(a.score * 20))
            lines.append(f"  {name:<14} [{bar}] {a.score:.2f}")
            for grp, ev in a.covered.items():
                lines.append(f"      + {grp:<24} “{ev}”")
            for grp in a.missing:
                lines.append(f"      - {grp:<24} (not addressed)")
            lines.append("")
        lines.append("-" * 66)
        lines.append(f"  ACQS (unweighted mean)  : {self.acqs:.3f}")
        lines.append("=" * 66)
        return "\n".join(lines)


# ------------------------------------------------------------------ #
#  Scorer                                                              #
# ------------------------------------------------------------------ #

class ACQSScorer:
    """Scores design/documentation text against ATTRIBUTE_INDICATORS."""

    def score_text(self, text: str, sources: Optional[List[str]] = None) -> ACQSReport:
        attributes: Dict[str, AttributeScore] = {}
        for attr, groups in ATTRIBUTE_INDICATORS.items():
            covered: Dict[str, str] = {}
            missing: List[str] = []
            for group, patterns in groups.items():
                evidence = None
                for pat in patterns:
                    m = re.search(pat, text, flags=re.IGNORECASE)
                    if m:
                        evidence = m.group(0)
                        break
                if evidence:
                    covered[group] = evidence
                else:
                    missing.append(group)
            attributes[attr] = AttributeScore(
                attribute=attr,
                score=round(len(covered) / len(groups), 4),
                covered=covered,
                missing=missing,
            )
        acqs = round(sum(a.score for a in attributes.values()) / len(attributes), 4)
        return ACQSReport(acqs=acqs, attributes=attributes, sources=sources or [])

    def score_files(self, paths: List[Path]) -> ACQSReport:
        """Score the union of one or more JSON / text documents."""
        chunks = []
        for p in paths:
            raw = Path(p).read_text(encoding="utf-8", errors="replace")
            if p.suffix == ".json":
                try:
                    raw = json.dumps(json.loads(raw), ensure_ascii=False)
                except json.JSONDecodeError:
                    pass
            chunks.append(raw)
        return self.score_text("\n".join(chunks), sources=[str(p) for p in paths])


# ------------------------------------------------------------------ #
#  CLI entry point                                                     #
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if len(sys.argv) < 2:
        print("Usage: python acqs_scorer.py <design.json|doc.txt> [more docs...]")
        sys.exit(1)

    files = [Path(a) for a in sys.argv[1:]]
    for f in files:
        if not f.exists():
            print(f"Not found: {f}")
            sys.exit(1)

    report = ACQSScorer().score_files(files)
    print(report.summary())
