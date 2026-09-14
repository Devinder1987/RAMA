"""
E-commerce Domain Knowledge Seeder
-------------------------------------
Populates the RAG knowledge base with e-commerce architecture patterns,
best practices, regulatory constraints, and reference SRS fragments.

Sources drawn from:
  - Standard e-commerce architecture guides
  - GDPR / PCI-DSS compliance requirements
  - PURE corpus domain patterns (Ferrari et al., 2017)
  - MAAD architecture evaluation rubric (Li et al., 2025)

Run once before first elicitation:
    python -m metagpt.elicitation.rag.seed_knowledge

RAMA Thesis — Devinder Shuthwal, LJMU 2026
"""

from metagpt.elicitation.rag.knowledge_base import EcommerceKnowledgeBase, DEFAULT_PERSIST_DIR

# ------------------------------------------------------------------ #
#  Knowledge Documents                                                 #
#  Each entry: id, category (matches ecommerce_schema keys), text     #
# ------------------------------------------------------------------ #

ECOMMERCE_KNOWLEDGE: list[dict] = [

    # ---------------------------------------------------------------- #
    #  AUTHENTICATION                                                   #
    # ---------------------------------------------------------------- #
    {
        "id": "auth-001",
        "category": "authentication",
        "text": (
            "JWT (JSON Web Tokens) combined with OAuth 2.0 is the industry standard for "
            "e-commerce authentication. Access tokens expire in 15–60 minutes; refresh tokens "
            "last 30 days. Social login (Google, Facebook, Apple) reduces signup friction by ~40%. "
            "Role-based access control (RBAC) is required to separate customer, admin, and vendor scopes."
        ),
    },
    {
        "id": "auth-002",
        "category": "authentication",
        "text": (
            "Two-factor authentication (2FA) via TOTP (Google Authenticator) or SMS OTP is "
            "recommended for admin accounts and optional for customers. Password hashing must use "
            "bcrypt or argon2 — never MD5 or SHA-1. Account lockout after 5 failed attempts prevents "
            "brute-force attacks."
        ),
    },
    {
        "id": "auth-003",
        "category": "authentication",
        "text": (
            "Guest checkout requires a temporary session token (not a full account). On registration "
            "during checkout, the guest cart and order history must merge into the new account. "
            "SSO (Single Sign-On) via SAML 2.0 or OIDC is required in B2B e-commerce contexts."
        ),
    },

    # ---------------------------------------------------------------- #
    #  PRODUCT CATALOG                                                  #
    # ---------------------------------------------------------------- #
    {
        "id": "catalog-001",
        "category": "product_catalog",
        "text": (
            "Core product catalog schema: product_id (UUID), name, slug, description (rich text), "
            "base_price, sale_price, currency, stock_quantity, SKU, category_id[], images[], "
            "variants[] (size/colour/material), tags[], is_active, created_at, updated_at. "
            "Variants should have their own SKU and stock count."
        ),
    },
    {
        "id": "catalog-002",
        "category": "product_catalog",
        "text": (
            "For catalogs with >10,000 products, Elasticsearch or Algolia is recommended over "
            "SQL LIKE queries. Category trees should support unlimited depth (nested set model or "
            "closure table). Product images should be stored in object storage (S3/GCS) and served "
            "via CDN. Lazy-loading and WebP format reduce page load by 30-50%."
        ),
    },
    {
        "id": "catalog-003",
        "category": "product_catalog",
        "text": (
            "Product import/export via CSV or API is a standard admin requirement. "
            "Bulk price updates should be transactional. Product reviews and ratings (1-5 stars) "
            "are commonly required and affect search ranking. Digital products need download link "
            "management separate from physical product inventory."
        ),
    },

    # ---------------------------------------------------------------- #
    #  SEARCH AND FILTER                                                #
    # ---------------------------------------------------------------- #
    {
        "id": "search-001",
        "category": "search_and_filter",
        "text": (
            "Product search architecture: Elasticsearch or Algolia for full-text search with faceted "
            "filtering (price range, category, brand, rating, availability). Typesense is a "
            "cost-effective open-source alternative. Autocomplete via edge n-grams. "
            "Search queries should be logged for analytics and personalisation."
        ),
    },
    {
        "id": "search-002",
        "category": "search_and_filter",
        "text": (
            "Search filters typically needed in e-commerce: price range (slider), category (tree), "
            "brand (multi-select), rating (>=N stars), availability (in stock only), size, colour. "
            "Sorting options: relevance, price (asc/desc), newest, best-selling, highest-rated. "
            "Facet counts should update dynamically as filters are applied."
        ),
    },

    # ---------------------------------------------------------------- #
    #  SHOPPING CART                                                    #
    # ---------------------------------------------------------------- #
    {
        "id": "cart-001",
        "category": "shopping_cart",
        "text": (
            "Shopping cart persistence: use Redis for ephemeral guest carts (TTL 7 days) and "
            "database for authenticated user carts (TTL 30 days). On login, merge guest cart into "
            "user cart with conflict resolution (keep higher quantity or user-preference rule). "
            "Cart must validate stock availability on each add and at checkout."
        ),
    },
    {
        "id": "cart-002",
        "category": "shopping_cart",
        "text": (
            "Cart line item schema: cart_id, product_id, variant_id, quantity, unit_price, "
            "total_price, added_at. Price should be locked at time of add to avoid surprise "
            "changes during session, but validated against current price at checkout. "
            "Wishlist is a separate entity from cart — items are not quantity-constrained."
        ),
    },

    # ---------------------------------------------------------------- #
    #  CHECKOUT                                                         #
    # ---------------------------------------------------------------- #
    {
        "id": "checkout-001",
        "category": "checkout",
        "text": (
            "Standard checkout flow: (1) Cart review → (2) Shipping address → (3) Delivery method "
            "selection → (4) Payment → (5) Order confirmation. Guest checkout skips account creation "
            "until post-confirmation. One-page checkout (all steps on one page) reduces abandonment "
            "by ~20% vs multi-step. Address validation via Google Places API or postal service API."
        ),
    },
    {
        "id": "checkout-002",
        "category": "checkout",
        "text": (
            "Coupon and promo code system: discount types include percentage off, fixed amount off, "
            "free shipping, buy-X-get-Y. Codes should have: usage limit per code, usage limit per "
            "user, expiry date, minimum order value, applicable product/category scope. "
            "Stacking of multiple coupons should be configurable."
        ),
    },

    # ---------------------------------------------------------------- #
    #  PAYMENT                                                          #
    # ---------------------------------------------------------------- #
    {
        "id": "payment-001",
        "category": "payment",
        "text": (
            "Payment gateway integration: Stripe and PayPal are the most common. Always use "
            "webhooks for asynchronous payment confirmation — never rely solely on redirect callback. "
            "PCI-DSS compliance: never store raw card numbers. Use tokenisation via the gateway "
            "(Stripe Elements / PayPal Vault). HTTPS required on all payment pages."
        ),
    },
    {
        "id": "payment-002",
        "category": "payment",
        "text": (
            "Refund architecture: full and partial refunds must be supported. Refund triggers order "
            "status change to 'refunded' and restores inventory. Refund processing time depends on "
            "gateway (Stripe: 5-10 days). Refund records must be immutable for audit trail. "
            "Chargeback handling requires webhook listener for dispute events."
        ),
    },
    {
        "id": "payment-003",
        "category": "payment",
        "text": (
            "Payment methods commonly required: credit/debit card, PayPal, Apple Pay, Google Pay, "
            "bank transfer (SEPA/BACS), buy-now-pay-later (Klarna, Afterpay). "
            "Subscription/recurring payments require saved payment methods and a billing engine "
            "with retry logic for failed charges (Stripe Billing or custom dunning management)."
        ),
    },

    # ---------------------------------------------------------------- #
    #  ORDER MANAGEMENT                                                 #
    # ---------------------------------------------------------------- #
    {
        "id": "order-001",
        "category": "order_management",
        "text": (
            "Order lifecycle state machine: pending → confirmed → processing → shipped → "
            "delivered → completed. Additional states: cancelled (allowed up to 'processing'), "
            "refunded, partially_refunded, on_hold. Each state transition emits an event "
            "(for notifications and audit). State changes must be idempotent."
        ),
    },
    {
        "id": "order-002",
        "category": "order_management",
        "text": (
            "Order schema: order_id (UUID), user_id, status, line_items[], shipping_address, "
            "billing_address, payment_method, payment_status, subtotal, tax, shipping_cost, "
            "discount, total, currency, tracking_number, created_at, updated_at. "
            "Order numbers shown to customers should be sequential and human-readable (e.g. ORD-10042)."
        ),
    },
    {
        "id": "order-003",
        "category": "order_management",
        "text": (
            "Returns and RMA (Return Merchandise Authorisation): customer requests return, admin "
            "approves and issues RMA number, customer ships back, warehouse confirms receipt, "
            "refund is triggered. Return window is typically 14-30 days. Return reasons should "
            "be captured for analytics. Restocking of returned items requires inspection workflow."
        ),
    },

    # ---------------------------------------------------------------- #
    #  USER PROFILE                                                     #
    # ---------------------------------------------------------------- #
    {
        "id": "profile-001",
        "category": "user_profile",
        "text": (
            "User profile features: personal details (name, email, phone), address book "
            "(multiple addresses with default shipping/billing), order history with reorder, "
            "saved payment methods, product reviews, notification preferences, "
            "loyalty points balance, account deletion (GDPR right to erasure)."
        ),
    },

    # ---------------------------------------------------------------- #
    #  NOTIFICATIONS                                                    #
    # ---------------------------------------------------------------- #
    {
        "id": "notif-001",
        "category": "notifications",
        "text": (
            "Required notification triggers: order confirmation, payment confirmation, "
            "order status change (shipped, delivered), return confirmation, refund processed, "
            "low stock alert (admin), new order alert (admin/vendor). "
            "Channels: email (SendGrid/AWS SES), SMS (Twilio), push notification (FCM/APNs)."
        ),
    },
    {
        "id": "notif-002",
        "category": "notifications",
        "text": (
            "Email notifications require HTML templates with plain-text fallback. "
            "Transactional emails (order confirmation) must be immediate; marketing emails "
            "require unsubscribe link (CAN-SPAM / GDPR). Notification preferences (opt-in/out "
            "per channel per type) must be stored per user. Event-driven architecture "
            "(message queue: RabbitMQ / SQS) decouples notification sending from order processing."
        ),
    },

    # ---------------------------------------------------------------- #
    #  ADMIN PANEL                                                      #
    # ---------------------------------------------------------------- #
    {
        "id": "admin-001",
        "category": "admin_panel",
        "text": (
            "Admin panel functional areas: product management (CRUD + bulk import), "
            "order management (view, update status, issue refund), customer management "
            "(view, ban, contact), inventory management, coupon/promotion management, "
            "reports (sales, revenue, top products, conversion rate), content management (CMS). "
            "Separate admin authentication with audit logging of all admin actions."
        ),
    },
    {
        "id": "admin-002",
        "category": "admin_panel",
        "text": (
            "Multi-vendor marketplace admin: vendor onboarding workflow (application, approval, "
            "agreement), vendor dashboard (own products, own orders, own payouts), commission "
            "management (percentage or flat fee), payout schedule (weekly/monthly via Stripe Connect "
            "or manual bank transfer). Super-admin vs vendor-admin permission separation is critical."
        ),
    },

    # ---------------------------------------------------------------- #
    #  PERFORMANCE                                                      #
    # ---------------------------------------------------------------- #
    {
        "id": "perf-001",
        "category": "performance",
        "text": (
            "E-commerce performance targets: page load <3s on 3G, <1s on broadband; "
            "API response <500ms at p95 under normal load, <2s at p95 under peak. "
            "Caching layers: Redis for product catalog and session (TTL 1-24h), "
            "CDN for static assets and product images. DB read replicas for reporting queries."
        ),
    },
    {
        "id": "perf-002",
        "category": "performance",
        "text": (
            "Database performance: index on product_id, category_id, order status, user_id, "
            "created_at. Avoid N+1 queries — use eager loading (JOINs or ORM includes). "
            "Connection pooling (PgBouncer for PostgreSQL) required at >100 concurrent users. "
            "Query timeout of 30s maximum to prevent cascading failures."
        ),
    },

    # ---------------------------------------------------------------- #
    #  SCALABILITY                                                      #
    # ---------------------------------------------------------------- #
    {
        "id": "scale-001",
        "category": "scalability",
        "text": (
            "Architecture decision: monolith is appropriate for <50k orders/day and MVP stage — "
            "simpler to develop and deploy. Microservices recommended for >50k orders/day or "
            "when teams need to deploy independently. Common service boundaries: "
            "catalog, cart, order, payment, notification, user, search, inventory."
        ),
    },
    {
        "id": "scale-002",
        "category": "scalability",
        "text": (
            "Horizontal scaling: stateless application servers behind a load balancer (NGINX / "
            "AWS ALB). Session state in Redis (not in-memory). Auto-scaling groups triggered by "
            "CPU >70% or request queue depth. Database scaling: read replicas for read-heavy "
            "workloads, sharding only when single-DB limits are reached (typically >1TB data)."
        ),
    },

    # ---------------------------------------------------------------- #
    #  SECURITY / COMPLIANCE                                            #
    # ---------------------------------------------------------------- #
    {
        "id": "gdpr-001",
        "category": "security_compliance",
        "text": (
            "GDPR requirements for e-commerce: (1) Explicit consent for marketing emails with "
            "timestamp. (2) Right to erasure — user data deletion must cascade across all services "
            "within 30 days. (3) Data portability — export user data as JSON/CSV on request. "
            "(4) Privacy policy and cookie consent banner required. (5) DPA agreements with all "
            "third-party processors. Data residency: EU customer data must remain in EU."
        ),
    },
    {
        "id": "pci-001",
        "category": "security_compliance",
        "text": (
            "PCI-DSS compliance for e-commerce: (1) Never log or store raw card data. "
            "(2) Use certified payment gateway tokenisation (Stripe Elements, PayPal). "
            "(3) HTTPS/TLS 1.2+ on all pages, not just checkout. (4) Regular vulnerability scans "
            "(quarterly external scans required for SAQ-A merchants). (5) Access control — "
            "only authorised staff can access cardholder data environment."
        ),
    },
    {
        "id": "security-001",
        "category": "security_compliance",
        "text": (
            "OWASP Top 10 mitigations for e-commerce: SQL injection prevention via parameterised "
            "queries/ORM. XSS prevention via output encoding and Content Security Policy header. "
            "CSRF protection via SameSite cookies and CSRF tokens. Rate limiting on login, "
            "checkout, and API endpoints. Input validation on all user-supplied data. "
            "Dependency scanning in CI pipeline (Snyk, Dependabot)."
        ),
    },

    # ---------------------------------------------------------------- #
    #  AVAILABILITY                                                     #
    # ---------------------------------------------------------------- #
    {
        "id": "avail-001",
        "category": "availability",
        "text": (
            "SLA targets: 99.9% uptime = 8.7h downtime/year; 99.99% = 52min/year. "
            "Achieving 99.9%: multi-AZ deployment, health checks, automatic failover. "
            "Achieving 99.99%: active-active multi-region, global load balancing, "
            "chaos engineering practices. RTO (Recovery Time Objective) and RPO "
            "(Recovery Point Objective) must be defined — e-commerce typically RTO <1h, RPO <1h."
        ),
    },

    # ---------------------------------------------------------------- #
    #  MULTI-CURRENCY / LANGUAGE                                        #
    # ---------------------------------------------------------------- #
    {
        "id": "i18n-001",
        "category": "multi_currency_language",
        "text": (
            "Multi-currency architecture: store all prices in the base currency (e.g. GBP) and "
            "convert at display time using real-time exchange rates (Open Exchange Rates API). "
            "Payment is charged in customer's displayed currency. Tax calculation must account "
            "for currency and jurisdiction. Rounding rules differ by currency (JPY has no decimals)."
        ),
    },
    {
        "id": "i18n-002",
        "category": "multi_currency_language",
        "text": (
            "Internationalisation (i18n): store translatable content (product names, descriptions, "
            "UI strings) in separate translation tables or a CMS with locale keys. "
            "URL structure options: subdomain (fr.store.com), path prefix (/fr/), or domain per "
            "locale. RTL support (Arabic, Hebrew) requires frontend CSS direction: rtl and "
            "mirrored layouts. Date/time formatting must respect locale."
        ),
    },

    # ---------------------------------------------------------------- #
    #  INVENTORY MANAGEMENT                                             #
    # ---------------------------------------------------------------- #
    {
        "id": "inventory-001",
        "category": "inventory_management",
        "text": (
            "Inventory management: real-time stock deduction should occur at order confirmation "
            "(not at cart add, to avoid ghost reservations). Use optimistic locking or SELECT FOR "
            "UPDATE to prevent overselling under concurrent orders. Low-stock alerts at configurable "
            "threshold (e.g. <10 units) via notification service."
        ),
    },
    {
        "id": "inventory-002",
        "category": "inventory_management",
        "text": (
            "Multi-warehouse inventory: each product-variant has stock per warehouse location. "
            "Fulfilment routing selects the nearest warehouse with stock. Inventory transfer "
            "between warehouses must be tracked. Backorder logic: allow purchase when stock=0, "
            "with estimated restock date shown. Batch stock updates via CSV import/export."
        ),
    },
]


def seed(reset: bool = False) -> None:
    """
    Populate the knowledge base with e-commerce domain documents.

    Args:
        reset: If True, clears the knowledge base before seeding.
               Use only when updating the knowledge corpus.
    """
    kb = EcommerceKnowledgeBase()

    if reset:
        print("Resetting knowledge base...")
        kb.reset()

    if kb.is_seeded() and not reset:
        print(f"Knowledge base already seeded ({kb.count()} documents). Skipping.")
        print("Use --reset to force re-seed.")
        return

    print(f"Seeding {len(ECOMMERCE_KNOWLEDGE)} documents into knowledge base...")
    kb.add_documents(ECOMMERCE_KNOWLEDGE)
    print(f"Done. Knowledge base now contains {kb.count()} documents.")
    print(f"Stored at: {DEFAULT_PERSIST_DIR}")


if __name__ == "__main__":
    import argparse
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Seed the RAMA e-commerce knowledge base.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear existing documents before seeding.",
    )
    args = parser.parse_args()
    seed(reset=args.reset)
