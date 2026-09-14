"""Quick W1 verification — run with: python test_w1.py"""
import importlib.util
import sys

def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

print("=" * 55)
print("W1 Verification — Schema + RAG Seed")
print("=" * 55)

# ---- Schema ----
print("\n[1] Loading ecommerce_schema.py ...")
schema = load_module(
    "metagpt/elicitation/schema/ecommerce_schema.py",
    "ecommerce_schema",
)
print(f"    Total categories : {schema.total_categories()}")
print(f"    Total weight     : {schema.total_weight()}")
print(f"    Critical (w=3)   : {list(schema.get_critical_categories().keys())}")
print(f"    FUNCTIONAL       : {list(schema.get_by_group('FUNCTIONAL').keys())}")
print(f"    NON_FUNCTIONAL   : {list(schema.get_by_group('NON_FUNCTIONAL').keys())}")
print(f"    DOMAIN           : {list(schema.get_by_group('DOMAIN').keys())}")

# Check each category has required fields
for name, cat in schema.ECOMMERCE_SCHEMA.items():
    assert cat.weight in (1, 2, 3), f"Bad weight for {name}"
    assert cat.keywords, f"Empty keywords for {name}"
    assert cat.question, f"Empty question for {name}"
print("    All categories validated: OK")

# ---- Knowledge Base ----
print("\n[2] Loading knowledge_base.py ...")
kb_mod = load_module(
    "metagpt/elicitation/rag/knowledge_base.py",
    "knowledge_base",
)
kb = kb_mod.EcommerceKnowledgeBase()
print(f"    KB initialised. Current doc count: {kb.count()}")

# ---- Seed ----
print("\n[3] Loading seed_knowledge.py ...")
# Patch the import inside seed_knowledge to use our already-loaded kb_mod
sys.modules["metagpt.elicitation.rag.knowledge_base"] = kb_mod

seed_mod = load_module(
    "metagpt/elicitation/rag/seed_knowledge.py",
    "seed_knowledge",
)
print(f"    Knowledge entries defined: {len(seed_mod.ECOMMERCE_KNOWLEDGE)}")
unique_categories = set(d["category"] for d in seed_mod.ECOMMERCE_KNOWLEDGE)
print(f"    Categories covered in seed: {sorted(unique_categories)}")

# Run seed
seed_mod.seed(reset=True)
# Create fresh instance after reset to get updated collection ref
kb = kb_mod.EcommerceKnowledgeBase()
print(f"    KB doc count after seed: {kb.count()}")

# ---- Query test ----
print("\n[4] RAG Query test ...")
results = kb.query("payment gateway PCI compliance refund", n_results=2)
print(f"    Query: 'payment gateway PCI compliance refund'")
for i, r in enumerate(results, 1):
    print(f"    Result {i}: {r[:100]}...")

results2 = kb.query_with_metadata("GDPR user data deletion", n_results=2, category_filter="security_compliance")
print(f"\n    Filtered query: 'GDPR user data deletion' (category=security_compliance)")
for r in results2:
    print(f"    [{r['category']}] dist={r['distance']:.3f}: {r['text'][:90]}...")

print("\n" + "=" * 55)
print("W1 COMPLETE — All checks passed")
print("=" * 55)
