"""
Unit tests for SRS Parser (W2)
--------------------------------
Tests are grouped into 5 suites:

  Suite 1 — ParsedSRS dataclass
  Suite 2 — Keyword detection (no LLM)
  Suite 3 — JSON extraction from LLM responses
  Suite 4 — Fallback parser (no LLM)
  Suite 5 — LLM integration (skipped if no API key)

Run:
    python metagpt/elicitation/parser/test_srs_parser.py
    python -m pytest metagpt/elicitation/parser/test_srs_parser.py -v

RAMA Thesis — Devinder Shuthwal, LJMU 2026
"""

import importlib.util
import sys
import unittest
from pathlib import Path

# ------------------------------------------------------------------ #
#  Load parser module directly (avoid metagpt.__init__ import chain)  #
# ------------------------------------------------------------------ #

def _load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_BASE = Path(__file__).parent

parser_mod = _load(str(_BASE / "srs_parser.py"), "srs_parser")
ParsedSRS  = parser_mod.ParsedSRS
SRSParser  = parser_mod.SRSParser


# ------------------------------------------------------------------ #
#  Fixtures                                                            #
# ------------------------------------------------------------------ #

SRS_RICH = (
    "Build a B2C e-commerce platform where customers can register, "
    "login, browse a product catalog with search and filter, add items "
    "to their cart, and checkout using Stripe or PayPal. "
    "Admins can manage products, view orders, and issue refunds. "
    "The system should handle 5000 concurrent users with <2s response time. "
    "GDPR and PCI-DSS compliance are required. "
    "Inventory must be tracked in real-time across two warehouses."
)

SRS_VAGUE = (
    "Build a fast, modern, secure online shop for users to buy things."
)

SRS_B2B = (
    "Create a B2B wholesale portal where business buyers can place bulk orders, "
    "get invoice-based payment (net 30 terms), and track shipments. "
    "Admins manage vendor accounts and pricing tiers."
)

VALID_JSON_RESPONSE = """{
  "actors": ["Customer", "Admin"],
  "entities": ["Product", "Order", "Cart"],
  "functional_intents": ["user adds product to cart", "admin views orders"],
  "nfr_mentions": ["system handles 5000 concurrent users"],
  "ambiguities": []
}"""

FENCED_JSON_RESPONSE = """Sure, here is the extracted data:
```json
{
  "actors": ["Customer"],
  "entities": ["Product"],
  "functional_intents": ["user browses catalog"],
  "nfr_mentions": [],
  "ambiguities": ["'users' is vague"]
}
```
Let me know if you need more detail.
"""

MALFORMED_JSON = "The requirements mention customers and products. { bad json }"

MISSING_KEYS_JSON = '{"actors": ["Admin"], "entities": []}'


# ================================================================== #
#  Suite 1 — ParsedSRS Dataclass                                       #
# ================================================================== #

class TestParsedSRS(unittest.TestCase):

    def test_defaults_are_empty_lists(self):
        p = ParsedSRS(raw_text="test")
        self.assertEqual(p.actors, [])
        self.assertEqual(p.entities, [])
        self.assertEqual(p.functional_intents, [])
        self.assertEqual(p.nfr_mentions, [])
        self.assertEqual(p.ambiguities, [])
        self.assertEqual(p.detected_keywords, [])
        self.assertEqual(p.schema_hints, {})

    def test_default_parse_method_is_fallback(self):
        p = ParsedSRS(raw_text="test")
        self.assertEqual(p.parse_method, "fallback")

    def test_combined_text_includes_all_fields(self):
        p = ParsedSRS(
            raw_text="buy products",
            actors=["Customer"],
            entities=["Product"],
            functional_intents=["user adds to cart"],
            nfr_mentions=["fast response"],
        )
        combined = p.combined_text()
        self.assertIn("buy products", combined)
        self.assertIn("customer", combined)
        self.assertIn("product", combined)
        self.assertIn("user adds to cart", combined)
        self.assertIn("fast response", combined)

    def test_combined_text_is_lowercase(self):
        p = ParsedSRS(raw_text="Online STORE", actors=["ADMIN"])
        self.assertEqual(p.combined_text(), p.combined_text().lower())

    def test_summary_returns_string(self):
        p = ParsedSRS(raw_text="test", actors=["Customer"], parse_method="llm")
        summary = p.summary()
        self.assertIsInstance(summary, str)
        self.assertIn("llm", summary)
        self.assertIn("Customer", summary)


# ================================================================== #
#  Suite 2 — Keyword Detection                                         #
# ================================================================== #

class TestKeywordDetection(unittest.TestCase):

    def setUp(self):
        self.parser = SRSParser()

    def test_detects_payment_keywords(self):
        keywords, hints = self.parser.detect_keywords(
            "The system will use Stripe for payment processing"
        )
        self.assertIn("payment", keywords)
        self.assertTrue(hints["payment"])

    def test_detects_auth_keywords(self):
        keywords, hints = self.parser.detect_keywords(
            "Users can login and register using OAuth"
        )
        self.assertTrue(hints["authentication"])
        self.assertTrue(any(k in keywords for k in ["login", "register", "oauth"]))

    def test_detects_multiple_categories(self):
        keywords, hints = self.parser.detect_keywords(SRS_RICH)
        true_hints = [k for k, v in hints.items() if v]
        # Rich SRS should cover at least 8 categories
        self.assertGreaterEqual(len(true_hints), 8)

    def test_vague_srs_has_few_hints(self):
        keywords, hints = self.parser.detect_keywords(SRS_VAGUE)
        true_hints = [k for k, v in hints.items() if v]
        # Vague SRS should cover fewer than 5 categories
        self.assertLess(len(true_hints), 5)

    def test_hints_keys_match_schema_categories(self):
        _, hints = self.parser.detect_keywords("some requirement text")
        schema_keys = set(parser_mod.ECOMMERCE_SCHEMA.keys())
        hint_keys = set(hints.keys())
        self.assertEqual(schema_keys, hint_keys)

    def test_no_false_positives_on_empty_string(self):
        keywords, hints = self.parser.detect_keywords("")
        self.assertEqual(keywords, [])
        self.assertTrue(all(v is False for v in hints.values()))

    def test_keywords_are_deduplicated(self):
        # "payment payment payment" should still return keyword once
        keywords, _ = self.parser.detect_keywords("payment payment payment")
        self.assertEqual(keywords.count("payment"), 1)

    def test_keyword_detection_is_case_insensitive(self):
        _, hints_lower = self.parser.detect_keywords("stripe payment")
        _, hints_upper = self.parser.detect_keywords("STRIPE PAYMENT")
        self.assertEqual(hints_lower["payment"], hints_upper["payment"])

    def test_detects_seo_keywords(self):
        _, hints = self.parser.detect_keywords("The system needs SEO-friendly URLs and sitemap")
        self.assertTrue(hints["seo"])

    def test_detects_rental_keywords(self):
        _, hints = self.parser.detect_keywords("Customers can rent products for daily or weekly hire")
        self.assertTrue(hints["rental_service"])

    def test_detects_b2b_keyword(self):
        _, hints = self.parser.detect_keywords(SRS_B2B)
        self.assertTrue(hints["business_model"])

    def test_detects_order_frequency_keyword(self):
        _, hints = self.parser.detect_keywords(
            "The platform targets high-frequency grocery reorders and subscription replenishment"
        )
        self.assertTrue(hints["order_frequency"])


# ================================================================== #
#  Suite 3 — JSON Extraction from LLM Responses                        #
# ================================================================== #

class TestJsonExtraction(unittest.TestCase):

    def setUp(self):
        self.parser = SRSParser()

    def test_extracts_clean_json(self):
        result = self.parser._extract_json(VALID_JSON_RESPONSE)
        self.assertIsNotNone(result)
        self.assertEqual(result["actors"], ["Customer", "Admin"])
        self.assertEqual(result["entities"], ["Product", "Order", "Cart"])

    def test_extracts_fenced_json(self):
        result = self.parser._extract_json(FENCED_JSON_RESPONSE)
        self.assertIsNotNone(result)
        self.assertEqual(result["actors"], ["Customer"])

    def test_returns_none_on_malformed_json(self):
        result = self.parser._extract_json(MALFORMED_JSON)
        self.assertIsNone(result)

    def test_returns_none_on_empty_string(self):
        result = self.parser._extract_json("")
        self.assertIsNone(result)

    def test_fills_missing_keys_with_empty_lists(self):
        result = self.parser._extract_json(MISSING_KEYS_JSON)
        self.assertIsNotNone(result)
        # Missing keys should be filled in
        self.assertIn("functional_intents", result)
        self.assertIn("nfr_mentions", result)
        self.assertIn("ambiguities", result)
        self.assertEqual(result["functional_intents"], [])

    def test_all_expected_keys_present(self):
        result = self.parser._extract_json(VALID_JSON_RESPONSE)
        for key in ["actors", "entities", "functional_intents", "nfr_mentions", "ambiguities"]:
            self.assertIn(key, result)

    def test_all_values_are_lists(self):
        result = self.parser._extract_json(VALID_JSON_RESPONSE)
        for value in result.values():
            self.assertIsInstance(value, list)


# ================================================================== #
#  Suite 4 — Fallback Parser (no LLM)                                  #
# ================================================================== #

class TestFallbackParser(unittest.TestCase):

    def setUp(self):
        self.parser = SRSParser()

    def test_returns_parsed_srs(self):
        result = self.parser.parse_fallback(SRS_RICH)
        self.assertIsInstance(result, ParsedSRS)

    def test_parse_method_is_fallback(self):
        result = self.parser.parse_fallback(SRS_RICH)
        self.assertEqual(result.parse_method, "fallback")

    def test_raw_text_preserved(self):
        result = self.parser.parse_fallback(SRS_RICH)
        self.assertEqual(result.raw_text, SRS_RICH)

    def test_detects_customer_actor(self):
        result = self.parser.parse_fallback("Customers can login and register")
        self.assertIn("Customer", result.actors)

    def test_detects_admin_actor(self):
        result = self.parser.parse_fallback("Admins manage products and orders")
        self.assertIn("Admin", result.actors)

    def test_detects_vendor_actor(self):
        result = self.parser.parse_fallback("Vendors can list their products on the marketplace")
        self.assertIn("Vendor", result.actors)

    def test_detects_product_entity(self):
        result = self.parser.parse_fallback("Users can browse products in categories")
        self.assertIn("Product", result.entities)

    def test_detects_order_entity(self):
        result = self.parser.parse_fallback("Customers can view their orders")
        self.assertIn("Order", result.entities)

    def test_flags_vague_fast(self):
        result = self.parser.parse_fallback(SRS_VAGUE)
        ambs = " ".join(result.ambiguities).lower()
        self.assertIn("performance", ambs)

    def test_flags_vague_secure(self):
        result = self.parser.parse_fallback(SRS_VAGUE)
        ambs = " ".join(result.ambiguities).lower()
        self.assertIn("security", ambs)

    def test_flags_vague_users(self):
        result = self.parser.parse_fallback(SRS_VAGUE)
        ambs = " ".join(result.ambiguities).lower()
        self.assertIn("b2c", ambs)

    def test_schema_hints_populated(self):
        result = self.parser.parse_fallback(SRS_RICH)
        self.assertIsInstance(result.schema_hints, dict)
        self.assertTrue(result.schema_hints.get("payment"))
        self.assertTrue(result.schema_hints.get("authentication"))

    def test_combined_text_covers_raw(self):
        result = self.parser.parse_fallback("Build a store with products")
        self.assertIn("build a store", result.combined_text())

    def test_rich_srs_has_many_hints(self):
        result = self.parser.parse_fallback(SRS_RICH)
        covered = [k for k, v in result.schema_hints.items() if v]
        self.assertGreaterEqual(len(covered), 8)


# ================================================================== #
#  Suite 5 — LLM Integration (skipped without API key)                 #
# ================================================================== #

class TestLLMParser(unittest.TestCase):

    def setUp(self):
        self.parser = SRSParser()
        if not self.parser._api_key:
            self.skipTest("No API key found in config2.yaml — skipping LLM tests")

    def test_llm_parse_returns_parsed_srs(self):
        result = self.parser.parse_sync(
            "Build an e-commerce store with product catalog, cart, and Stripe payment."
        )
        self.assertIsInstance(result, ParsedSRS)

    def test_llm_parse_method_is_llm(self):
        result = self.parser.parse_sync(
            "Build an e-commerce store with product catalog, cart, and Stripe payment."
        )
        self.assertEqual(result.parse_method, "llm")

    def test_llm_extracts_actors(self):
        result = self.parser.parse_sync(
            "Customers can shop online. Admins manage the product catalog."
        )
        actors_lower = [a.lower() for a in result.actors]
        self.assertTrue(
            any("customer" in a for a in actors_lower) or
            any("admin" in a for a in actors_lower)
        )

    def test_llm_extracts_entities(self):
        result = self.parser.parse_sync(
            "The platform has products, orders, and shopping carts."
        )
        entities_lower = [e.lower() for e in result.entities]
        self.assertTrue(any("product" in e for e in entities_lower))

    def test_llm_flags_ambiguities(self):
        result = self.parser.parse_sync(SRS_VAGUE)
        # Vague SRS should trigger at least one ambiguity flag
        self.assertGreater(len(result.ambiguities), 0)

    def test_llm_extracts_nfr(self):
        result = self.parser.parse_sync(
            "The system must handle 10,000 concurrent users with <500ms response time."
        )
        nfr_text = " ".join(result.nfr_mentions).lower()
        self.assertTrue(
            "concurrent" in nfr_text or "response" in nfr_text or "10,000" in nfr_text
        )

    def test_llm_parses_rich_srs(self):
        result = self.parser.parse_sync(SRS_RICH)
        self.assertGreater(len(result.functional_intents), 2)
        covered = [k for k, v in result.schema_hints.items() if v]
        self.assertGreaterEqual(len(covered), 8)


# ================================================================== #
#  Runner                                                              #
# ================================================================== #

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestParsedSRS))
    suite.addTests(loader.loadTestsFromTestCase(TestKeywordDetection))
    suite.addTests(loader.loadTestsFromTestCase(TestJsonExtraction))
    suite.addTests(loader.loadTestsFromTestCase(TestFallbackParser))
    suite.addTests(loader.loadTestsFromTestCase(TestLLMParser))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
