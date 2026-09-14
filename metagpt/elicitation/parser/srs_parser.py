"""
SRS Parser
-----------
Extracts structured information from a raw software requirements
specification (SRS) using two complementary passes:

  Pass 1 — Keyword Detection (no LLM, instant)
      Scans the raw text for ECOMMERCE_SCHEMA keywords.
      Produces: detected_keywords, schema_hints (which categories
      appear to be mentioned).

  Pass 2 — LLM Extraction (Gemini 2.5 Flash)
      Sends the SRS to Gemini and asks it to extract actors,
      entities, functional intents, NFR mentions, and ambiguities
      as structured JSON.

Both passes are combined into a single ParsedSRS object, which is
the input to the CompletenessAnalyser (W3).

RAMA Thesis — Devinder Shuthwal, LJMU 2026
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

# ------------------------------------------------------------------ #
#  Schema import — load directly to avoid metagpt.__init__ chain      #
# ------------------------------------------------------------------ #
_SCHEMA_PATH = Path(__file__).parent.parent / "schema" / "ecommerce_schema.py"
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location("ecommerce_schema", _SCHEMA_PATH)
_schema_mod = _ilu.module_from_spec(_spec)
sys.modules["ecommerce_schema"] = _schema_mod
_spec.loader.exec_module(_schema_mod)
ECOMMERCE_SCHEMA = _schema_mod.ECOMMERCE_SCHEMA

# ------------------------------------------------------------------ #
#  Config loader                                                       #
# ------------------------------------------------------------------ #

def _load_api_key() -> Optional[str]:
    """Read Gemini API key from config/config2.yaml."""
    candidates = [
        Path(__file__).parent.parent.parent.parent / "config" / "config2.yaml",
        Path.home() / ".metagpt" / "config2.yaml",
    ]
    for path in candidates:
        if path.exists():
            cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
            return cfg.get("llm", {}).get("api_key")
    return None


# ------------------------------------------------------------------ #
#  Data model                                                          #
# ------------------------------------------------------------------ #

@dataclass
class ParsedSRS:
    """
    Structured representation of a parsed SRS document.
    Produced by SRSParser and consumed by CompletenessAnalyser.
    """
    raw_text: str

    # LLM-extracted fields
    actors: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    functional_intents: List[str] = field(default_factory=list)
    nfr_mentions: List[str] = field(default_factory=list)
    ambiguities: List[str] = field(default_factory=list)

    # Keyword-detection fields
    detected_keywords: List[str] = field(default_factory=list)
    schema_hints: Dict[str, bool] = field(default_factory=dict)

    # Metadata
    parse_method: str = "fallback"   # "llm" | "fallback"

    def combined_text(self) -> str:
        """All text concatenated for downstream keyword analysis."""
        parts = [
            self.raw_text,
            *self.functional_intents,
            *self.nfr_mentions,
            *self.entities,
            *self.actors,
        ]
        return " ".join(parts).lower()

    def summary(self) -> str:
        lines = [
            f"Parse method : {self.parse_method}",
            f"Actors       : {self.actors}",
            f"Entities     : {self.entities}",
            f"Intents      : {len(self.functional_intents)} extracted",
            f"NFR mentions : {len(self.nfr_mentions)} extracted",
            f"Ambiguities  : {self.ambiguities}",
            f"Keywords     : {len(self.detected_keywords)} matched",
            f"Schema hints : {[k for k, v in self.schema_hints.items() if v]}",
        ]
        return "\n".join(lines)


# ------------------------------------------------------------------ #
#  LLM Prompt                                                          #
# ------------------------------------------------------------------ #

_EXTRACT_PROMPT = """\
You are a senior requirements engineer specialising in e-commerce software systems.

Analyse the following software requirement specification (SRS) and extract structured information.

Return ONLY a valid JSON object with exactly these keys — no markdown, no explanation:
{{
  "actors": ["list of user or system roles mentioned (e.g. Customer, Admin, Vendor, Guest)"],
  "entities": ["list of domain data objects (e.g. Product, Order, Cart, Category, Review)"],
  "functional_intents": ["short verb-noun phrases for each functional requirement (e.g. 'user adds product to cart')"],
  "nfr_mentions": ["any performance, security, scalability, compliance, or availability requirements mentioned"],
  "ambiguities": ["vague or underspecified terms that will need clarification (e.g. 'users', 'fast', 'secure', 'modern')"]
}}

Rules:
- If a field has no content, return an empty list [].
- Keep each item short (under 15 words).
- Do NOT add extra keys or wrap in markdown code fences.

SRS Input:
{requirement}
"""


# ------------------------------------------------------------------ #
#  Parser                                                              #
# ------------------------------------------------------------------ #

class SRSParser:
    """
    Two-pass SRS parser.

    Usage (async):
        parser = SRSParser()
        parsed = await parser.parse("Build an online store with payments")

    Usage (sync):
        parsed = parser.parse_sync("Build an online store with payments")
    """

    def __init__(self):
        self._api_key: Optional[str] = _load_api_key()
        self._client = None   # lazy-initialised on first LLM call
        # Token accounting (Gemini usage_metadata), read by ElicitationRunner
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.llm_calls = 0

    def _record_usage(self, response) -> None:
        """Accumulate Gemini token usage from a response (best-effort)."""
        um = getattr(response, "usage_metadata", None)
        if um is None:
            return
        self.prompt_tokens     += getattr(um, "prompt_token_count", 0) or 0
        self.completion_tokens += getattr(um, "candidates_token_count", 0) or 0
        self.llm_calls         += 1

    # ---------------------------------------------------------------- #
    #  Public API                                                        #
    # ---------------------------------------------------------------- #

    async def parse(self, requirement: str) -> ParsedSRS:
        """
        Full two-pass parse: keyword detection + LLM extraction.
        Falls back to keyword-only if LLM is unavailable or fails.
        """
        keywords, hints = self.detect_keywords(requirement)

        llm_data = await self._call_llm(requirement)
        if llm_data:
            return ParsedSRS(
                raw_text=requirement,
                actors=llm_data.get("actors", []),
                entities=llm_data.get("entities", []),
                functional_intents=llm_data.get("functional_intents", []),
                nfr_mentions=llm_data.get("nfr_mentions", []),
                ambiguities=llm_data.get("ambiguities", []),
                detected_keywords=keywords,
                schema_hints=hints,
                parse_method="llm",
            )

        # LLM unavailable — fall back to keyword-only
        return self.parse_fallback(requirement)

    def parse_sync(self, requirement: str) -> ParsedSRS:
        """Synchronous wrapper around parse()."""
        return asyncio.run(self.parse(requirement))

    def parse_fallback(self, requirement: str) -> ParsedSRS:
        """
        Keyword-only parse — no LLM required.
        Used when the API key is absent or the LLM call fails.
        Produces a ParsedSRS with schema_hints populated from keywords.
        """
        keywords, hints = self.detect_keywords(requirement)
        actors = self._extract_actors_heuristic(requirement)
        entities = self._extract_entities_heuristic(requirement)

        return ParsedSRS(
            raw_text=requirement,
            actors=actors,
            entities=entities,
            functional_intents=[],
            nfr_mentions=[],
            ambiguities=self._detect_ambiguities(requirement),
            detected_keywords=keywords,
            schema_hints=hints,
            parse_method="fallback",
        )

    def detect_keywords(self, text: str) -> tuple[List[str], Dict[str, bool]]:
        """
        Scan text for ECOMMERCE_SCHEMA keywords.

        Returns:
            keywords : all matched keyword strings
            hints    : {category_name: True if any keyword matched}
        """
        text_lower = text.lower()
        matched_keywords: List[str] = []
        hints: Dict[str, bool] = {}

        for category_name, category in ECOMMERCE_SCHEMA.items():
            found = [kw for kw in category.keywords if kw.lower() in text_lower]
            hints[category_name] = len(found) > 0
            matched_keywords.extend(found)

        # Deduplicate while preserving order
        seen = set()
        unique_keywords = []
        for kw in matched_keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)

        return unique_keywords, hints

    # ---------------------------------------------------------------- #
    #  LLM call                                                          #
    # ---------------------------------------------------------------- #

    async def _call_llm(self, requirement: str) -> Optional[dict]:
        """
        Call Gemini 2.5 Flash and return parsed JSON dict.
        Returns None if the API key is missing or the call fails.
        """
        if not self._api_key:
            print("  [SRSParser] No API key found — using fallback parser.")
            return None

        try:
            from google import genai

            if self._client is None:
                self._client = genai.Client(api_key=self._api_key)

            prompt = _EXTRACT_PROMPT.format(requirement=requirement)

            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model="gemini-2.5-flash",
                contents=prompt,
            )
            self._record_usage(response)
            raw_text = response.text
            return self._extract_json(raw_text)

        except Exception as exc:
            print(f"  [SRSParser] LLM call failed ({exc}) — using fallback parser.")
            return None

    # ---------------------------------------------------------------- #
    #  JSON extraction from LLM response                                 #
    # ---------------------------------------------------------------- #

    def _extract_json(self, text: str) -> Optional[dict]:
        """
        Extract a JSON object from LLM output.
        Handles:
          - Clean JSON
          - JSON wrapped in ```json ... ``` markdown fences
          - JSON embedded in surrounding prose
        """
        # Strip markdown fences if present
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1)

        # Find the first { ... } block
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if not brace_match:
            return None

        try:
            data = json.loads(brace_match.group())
            return self._validate_llm_response(data)
        except json.JSONDecodeError:
            return None

    def _validate_llm_response(self, data: dict) -> dict:
        """Ensure all expected keys are present and are lists."""
        expected = ["actors", "entities", "functional_intents", "nfr_mentions", "ambiguities"]
        for key in expected:
            if key not in data or not isinstance(data[key], list):
                data[key] = []
        return data

    # ---------------------------------------------------------------- #
    #  Heuristic helpers (used by fallback)                              #
    # ---------------------------------------------------------------- #

    # (regex, canonical_name) tuples — regex handles singular/plural,
    # canonical_name avoids relying on match.group().capitalize() which
    # would otherwise produce "Admins" instead of "Admin" for plural input.
    _ACTOR_PATTERNS = [
        (r"\bcustomers?\b", "Customer"),
        (r"\busers?\b", "User"),
        (r"\bbuyers?\b", "Buyer"),
        (r"\bshoppers?\b", "Shopper"),
        (r"\bguests?\b", "Guest"),
        (r"\bvisitors?\b", "Visitor"),
        (r"\badministrators?\b", "Administrator"),
        (r"\badmins?\b", "Admin"),
        (r"\bmanagers?\b", "Manager"),
        (r"\bstaff\b", "Staff"),
        (r"\boperators?\b", "Operator"),
        (r"\bvendors?\b", "Vendor"),
        (r"\bsellers?\b", "Seller"),
        (r"\bmerchants?\b", "Merchant"),
        (r"\bsuppliers?\b", "Supplier"),
        (r"\bsystems?\b", "System"),
        (r"\bapis?\b", "API"),
        (r"\bservices?\b", "Service"),
        (r"\bbots?\b", "Bot"),
        (r"\bagents?\b", "Agent"),
        (r"\bowners?\b", "Owner"),
        (r"\bsuperadmins?\b", "Superadmin"),
        (r"\bsuper.admins?\b", "Superadmin"),
    ]

    _ENTITY_PATTERNS = [
        (r"\bproducts?\b", "Product"),
        (r"\bitems?\b", "Item"),
        (r"\bgoods\b", "Goods"),
        (r"\bmerchandise\b", "Merchandise"),
        (r"\borders?\b", "Order"),
        (r"\bpurchases?\b", "Purchase"),
        (r"\btransactions?\b", "Transaction"),
        (r"\bcarts?\b", "Cart"),
        (r"\bbaskets?\b", "Basket"),
        (r"\bbags?\b", "Bag"),
        (r"\bcategor(?:y|ies)\b", "Category"),
        (r"\bcollections?\b", "Collection"),
        (r"\bdepartments?\b", "Department"),
        (r"\bpayments?\b", "Payment"),
        (r"\binvoices?\b", "Invoice"),
        (r"\breceipts?\b", "Receipt"),
        (r"\breviews?\b", "Review"),
        (r"\bratings?\b", "Rating"),
        (r"\bfeedback\b", "Feedback"),
        (r"\bshipments?\b", "Shipment"),
        (r"\bdeliver(?:y|ies)\b", "Delivery"),
        (r"\bshipping\b", "Shipping"),
        (r"\bcoupons?\b", "Coupon"),
        (r"\bvouchers?\b", "Voucher"),
        (r"\bdiscounts?\b", "Discount"),
        (r"\bpromos?\b", "Promo"),
        (r"\bwarehouses?\b", "Warehouse"),
        (r"\binventory\b", "Inventory"),
        (r"\bstocks?\b", "Stock"),
        (r"\bsubscriptions?\b", "Subscription"),
        (r"\bmemberships?\b", "Membership"),
        (r"\bplans?\b", "Plan"),
    ]

    _AMBIGUITY_PATTERNS = [
        (r"\bfast\b",   "performance target is vague — specify response time"),
        (r"\bsecure\b", "security requirement is vague — specify standard (GDPR, PCI-DSS, OWASP)"),
        (r"\bmodern\b", "'modern' is subjective — specify tech stack or UI framework"),
        (r"\bsimple\b", "'simple' is subjective — specify feature scope"),
        (r"\busers\b",  "'users' is ambiguous — are these B2C customers, B2B buyers, or admins?"),
        (r"\bscalable\b", "scalability target is vague — specify expected load (users/orders per day)"),
        (r"\breal.?time\b", "'real-time' is vague — specify acceptable latency"),
        (r"\bai\b",     "AI feature is underspecified — describe the expected behaviour"),
    ]

    def _extract_actors_heuristic(self, text: str) -> List[str]:
        found = set()
        text_lower = text.lower()
        for pattern, canonical in self._ACTOR_PATTERNS:
            if re.search(pattern, text_lower):
                found.add(canonical)
        return sorted(found)

    def _extract_entities_heuristic(self, text: str) -> List[str]:
        found = set()
        text_lower = text.lower()
        for pattern, canonical in self._ENTITY_PATTERNS:
            if re.search(pattern, text_lower):
                found.add(canonical)
        return sorted(found)

    def _detect_ambiguities(self, text: str) -> List[str]:
        found = []
        text_lower = text.lower()
        for pattern, message in self._AMBIGUITY_PATTERNS:
            if re.search(pattern, text_lower):
                found.append(message)
        return found


# ------------------------------------------------------------------ #
#  CLI entry point — quick test                                        #
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sample = (
        "Build an online store where customers can browse products, "
        "add items to cart, and checkout with PayPal or credit card. "
        "Admins can manage products and view orders. "
        "The system should be fast and secure."
    )
    parser = SRSParser()
    result = parser.parse_sync(sample)
    print("\n=== ParsedSRS ===")
    print(result.summary())
