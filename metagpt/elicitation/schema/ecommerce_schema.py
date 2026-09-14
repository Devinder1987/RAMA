"""
E-commerce Input-Completeness Schema
--------------------------------------
Defines the required categories for a complete e-commerce SRS.

Each category has:
  - weight      : architectural impact (3=critical, 2=important, 1=optional)
  - keywords    : terms whose presence in SRS signals coverage
  - question    : the clarifying question to ask if category is missing
  - suggestions : concrete answer options shown to the user
  - description : brief rationale used in evaluation reports
  - group       : FUNCTIONAL | NON_FUNCTIONAL | DOMAIN

RAMA Thesis — Devinder Shuthwal, LJMU 2026
"""

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class SchemaCategory:
    name: str
    weight: int                  # 3=critical, 2=important, 1=optional
    keywords: List[str]
    question: str
    suggestions: List[str]       # selectable answer options shown to user
    description: str
    group: str                   # FUNCTIONAL | NON_FUNCTIONAL | DOMAIN


ECOMMERCE_SCHEMA: Dict[str, SchemaCategory] = {

    # ------------------------------------------------------------------ #
    #  FUNCTIONAL REQUIREMENTS                                             #
    # ------------------------------------------------------------------ #

    "authentication": SchemaCategory(
        name="authentication",
        weight=3,
        group="FUNCTIONAL",
        keywords=[
            "login", "logout", "register", "signup", "sign up",
            "oauth", "jwt", "token", "auth", "password", "sso",
            "social login", "session", "2fa", "two-factor",
        ],
        question=(
            "What authentication method is required?"
        ),
        suggestions=[
            "Email / password",
            "Google OAuth",
            "Facebook OAuth",
            "Apple Sign-in",
            "SSO / SAML 2.0 (enterprise)",
            "Two-factor authentication (2FA)",
            "Passwordless / magic link",
        ],
        description="Auth underpins every user-facing service and determines session, token, and identity architecture.",
    ),

    "product_catalog": SchemaCategory(
        name="product_catalog",
        weight=3,
        group="FUNCTIONAL",
        keywords=[
            "product", "catalog", "catalogue", "listing", "item",
            "category", "sku", "variant", "stock keeping", "merchandise",
            "collection", "brand", "tag",
        ],
        question=(
            "What type of products will the catalog contain and how are they structured?"
        ),
        suggestions=[
            "Simple products (no variants)",
            "Products with variants (size / colour / material)",
            "Digital / downloadable products",
            "Bundled or kit products",
            "Virtual products (services)",
            "Configurable products (custom options)",
            "Subscription products",
        ],
        description="Product catalog scale and variant model determine the core data schema and storage choices.",
    ),

    "search_and_filter": SchemaCategory(
        name="search_and_filter",
        weight=2,
        group="FUNCTIONAL",
        keywords=[
            "search", "filter", "sort", "facet", "full-text",
            "elasticsearch", "algolia", "typesense", "autocomplete",
            "keyword", "query",
        ],
        question=(
            "What search and filter capabilities are required?"
        ),
        suggestions=[
            "Basic keyword search (SQL LIKE)",
            "Full-text search (Elasticsearch / Algolia)",
            "Faceted filtering (price, category, brand, rating)",
            "Autocomplete / type-ahead",
            "Search by image",
            "Voice search",
            "Personalised / AI-powered search results",
        ],
        description="Search architecture (SQL LIKE vs dedicated engine) is a major infrastructure decision at scale.",
    ),

    "shopping_cart": SchemaCategory(
        name="shopping_cart",
        weight=3,
        group="FUNCTIONAL",
        keywords=[
            "cart", "basket", "add to cart",
            "bag", "quantity", "line item",
        ],
        question=(
            "How should the shopping cart behave?"
        ),
        suggestions=[
            "Session-based guest cart (lost on browser close)",
            "Persistent cart — database-backed, across devices",
            "Guest cart merge into account on login",
            "Multiple carts / saved lists per user",
            "Quick add to cart (without page reload)",
            "Cart expiry reminder notification",
        ],
        description="Cart persistence strategy (Redis vs DB) and guest-merge logic affect session and auth design.",
    ),

    "wishlist": SchemaCategory(
        name="wishlist",
        weight=2,
        group="FUNCTIONAL",
        keywords=[
            "wishlist", "wish list", "favourite", "favorite",
            "save for later", "bookmark", "saved items",
        ],
        question=(
            "Is a wishlist or 'save for later' feature required?"
        ),
        suggestions=[
            "No wishlist needed",
            "Single wishlist per user",
            "Multiple named wishlists per user",
            "Public / shareable wishlist (URL link)",
            "Wishlist → cart (move items to cart)",
            "Price-drop alerts for wishlist items",
            "Guest wishlist (no login required)",
            "Admin analytics on wishlist popularity",
        ],
        description="Wishlist design (single vs multiple, public vs private) affects the data model and notification service.",
    ),

    "checkout": SchemaCategory(
        name="checkout",
        weight=3,
        group="FUNCTIONAL",
        keywords=[
            "checkout", "billing", "shipping address", "delivery address",
            "coupon", "discount", "promo", "voucher", "guest checkout",
            "order summary",
        ],
        question=(
            "What checkout flow and options are required?"
        ),
        suggestions=[
            "Multi-step checkout (separate pages per step)",
            "Single-page checkout (all steps in one view)",
            "Guest checkout (no account required)",
            "Express checkout (pre-filled saved details)",
            "One-click checkout (Amazon-style)",
            "Coupon / promo code entry at checkout",
            "Address auto-complete (Google Places API)",
        ],
        description="Checkout flow complexity (steps, guest support, coupons) drives the order creation service design.",
    ),

    "payment": SchemaCategory(
        name="payment",
        weight=3,
        group="FUNCTIONAL",
        keywords=[
            "payment", "stripe", "paypal", "card", "credit card",
            "debit", "wallet", "bank transfer", "refund", "partial refund",
            "invoice", "subscription", "recurring", "pci",
        ],
        question=(
            "Which payment methods and gateways must be supported?"
        ),
        suggestions=[
            "Credit / debit card (Stripe)",
            "PayPal",
            "Apple Pay / Google Pay",
            "Bank transfer (SEPA / BACS)",
            "Buy Now Pay Later (Klarna / Afterpay)",
            "Cash on delivery",
            "Invoice / net terms (B2B)",
            "Cryptocurrency",
            "Recurring / subscription billing",
        ],
        description="Payment gateway choice drives PCI-DSS scope, webhook handling, and refund service architecture.",
    ),

    "promotions_coupons": SchemaCategory(
        name="promotions_coupons",
        weight=2,
        group="FUNCTIONAL",
        keywords=[
            "promotion", "coupon", "discount code", "promo code",
            "offer", "flash sale", "deal", "voucher", "campaign",
            "loyalty", "referral", "reward",
        ],
        question=(
            "What promotional and discount features are required?"
        ),
        suggestions=[
            "Percentage discount (e.g. 20% off)",
            "Fixed amount discount (e.g. £10 off)",
            "Free shipping promotion",
            "Buy X get Y free",
            "Flash sale / limited-time offers",
            "First-order discount for new customers",
            "Loyalty points / rewards programme",
            "Referral / affiliate discount codes",
            "Minimum order value threshold for discount",
            "Product or category-specific coupons",
        ],
        description="Promotion engine complexity (stacking rules, eligibility logic) is a separate architectural concern from checkout.",
    ),

    "order_management": SchemaCategory(
        name="order_management",
        weight=3,
        group="FUNCTIONAL",
        keywords=[
            "order", "tracking", "shipment", "return", "cancellation",
            "fulfilment", "fulfillment", "status", "dispatch", "delivery",
            "invoice", "receipt",
        ],
        question=(
            "What is the required order lifecycle and fulfilment model?"
        ),
        suggestions=[
            "Standard lifecycle: pending → confirmed → shipped → delivered",
            "Click & collect (in-store pickup)",
            "Split orders (multiple shipments from different warehouses)",
            "Cancellation allowed before shipment",
            "Returns / RMA management",
            "Partial fulfilment (ship available items first)",
            "Dropshipping (third-party fulfilment)",
        ],
        description="Order lifecycle states directly map to the state machine and event model in the order service.",
    ),

    "user_profile": SchemaCategory(
        name="user_profile",
        weight=2,
        group="FUNCTIONAL",
        keywords=[
            "profile", "account", "address book", "order history",
            "preferences", "settings", "my account", "saved",
        ],
        question=(
            "What features should the user profile / account section include?"
        ),
        suggestions=[
            "Basic profile (name, email, phone)",
            "Address book (multiple shipping / billing addresses)",
            "Order history with one-click reorder",
            "Saved payment methods",
            "Product reviews and ratings",
            "Loyalty points balance",
            "Referral programme tracking",
            "Account deletion (GDPR right to erasure)",
        ],
        description="Profile scope determines the account service API surface and the data stored per user.",
    ),

    "notifications": SchemaCategory(
        name="notifications",
        weight=2,
        group="FUNCTIONAL",
        keywords=[
            "email", "sms", "notification", "alert", "confirmation",
            "push notification", "reminder", "sendgrid", "twilio",
            "fcm", "webhook", "event",
        ],
        question=(
            "What notifications are required and via which channels?"
        ),
        suggestions=[
            "Email — transactional (order confirmation, shipping)",
            "Email — marketing / newsletters",
            "SMS order status updates",
            "Push notifications (mobile app)",
            "In-app notification centre",
            "WhatsApp Business messages",
            "Admin alerts (low stock, new orders)",
        ],
        description="Notification channels and triggers define the messaging infrastructure and event bus requirements.",
    ),

    "admin_panel": SchemaCategory(
        name="admin_panel",
        weight=2,
        group="FUNCTIONAL",
        keywords=[
            "admin", "dashboard", "cms", "content management",
            "back office", "backoffice", "vendor", "seller",
            "manage", "report", "analytics",
        ],
        question=(
            "What does the admin panel need to cover?"
        ),
        suggestions=[
            "Product management (CRUD + bulk import/export)",
            "Order management (view / update status / issue refund)",
            "Customer management (view / contact / ban)",
            "Inventory management",
            "Coupon and promotion management",
            "Sales reports and analytics dashboard",
            "CMS (content pages, banners, blog)",
            "Multi-vendor / seller management",
        ],
        description="Admin panel scope and multi-role RBAC model affect API permission design and frontend architecture.",
    ),

    # ------------------------------------------------------------------ #
    #  NON-FUNCTIONAL REQUIREMENTS                                         #
    # ------------------------------------------------------------------ #

    "performance": SchemaCategory(
        name="performance",
        weight=3,
        group="NON_FUNCTIONAL",
        keywords=[
            "concurrent", "users", "response time", "latency",
            "throughput", "tps", "rps", "p95", "p99",
            "millisecond", "second", "fast", "performance",
        ],
        question=(
            "What are the performance targets for the system?"
        ),
        suggestions=[
            "<1 s API response (high-end, low-latency)",
            "<2 s API response (standard e-commerce)",
            "100 – 1,000 concurrent users",
            "1,000 – 10,000 concurrent users",
            "10,000+ concurrent users (enterprise / flash sale scale)",
            "CDN for static assets and product images",
            "Redis caching for catalog and sessions",
        ],
        description="Performance targets determine caching strategy, DB indexing, CDN use, and horizontal scaling needs.",
    ),

    "scalability": SchemaCategory(
        name="scalability",
        weight=2,
        group="NON_FUNCTIONAL",
        keywords=[
            "scale", "scalable", "horizontal", "vertical",
            "microservice", "monolith", "load", "cloud",
            "kubernetes", "docker", "container", "auto-scaling",
            "black friday", "peak", "traffic spike",
        ],
        question=(
            "What is the expected scalability and deployment model?"
        ),
        suggestions=[
            "Monolith — simpler, suitable for MVP / small scale",
            "Modular monolith — structured but single deployable",
            "Microservices — highly scalable, independent deployments",
            "Serverless functions (AWS Lambda / Cloudflare Workers)",
            "Auto-scaling cloud deployment (AWS / GCP / Azure)",
            "On-premise / self-hosted",
            "Multi-region deployment for global traffic",
        ],
        description="Architecture style (monolith vs microservices) is the most consequential structural decision.",
    ),

    "security_compliance": SchemaCategory(
        name="security_compliance",
        weight=3,
        group="NON_FUNCTIONAL",
        keywords=[
            "gdpr", "pci", "pci-dss", "ssl", "tls", "https",
            "encryption", "owasp", "compliance", "regulation",
            "data protection", "privacy", "audit", "penetration",
        ],
        question=(
            "Which security standards and compliance requirements apply?"
        ),
        suggestions=[
            "GDPR (EU data protection)",
            "PCI-DSS (payment card security)",
            "OWASP Top 10 hardening",
            "ISO 27001 (information security management)",
            "SOC 2 (service organisation controls)",
            "CCPA (California Consumer Privacy Act)",
            "Age verification (alcohol, adult content)",
        ],
        description="Compliance requirements (GDPR, PCI-DSS) directly constrain data storage, logging, and encryption design.",
    ),

    "availability": SchemaCategory(
        name="availability",
        weight=2,
        group="NON_FUNCTIONAL",
        keywords=[
            "uptime", "sla", "availability", "99.9", "99.99",
            "disaster recovery", "failover", "redundancy",
            "high availability", "ha", "backup", "rto", "rpo",
        ],
        question=(
            "What uptime SLA and disaster recovery requirements apply?"
        ),
        suggestions=[
            "99.5% uptime (standard / budget hosting)",
            "99.9% uptime (commercial grade — 8.7 h downtime/year)",
            "99.99% uptime (enterprise — 52 min downtime/year)",
            "Automatic failover on server failure",
            "Multi-AZ (availability zone) deployment",
            "Disaster recovery plan with defined RTO / RPO",
            "Daily + hourly database backups",
        ],
        description="SLA target determines infrastructure redundancy, failover strategy, and backup architecture.",
    ),

    # ------------------------------------------------------------------ #
    #  DOMAIN-SPECIFIC REQUIREMENTS                                        #
    # ------------------------------------------------------------------ #

    "business_model": SchemaCategory(
        name="business_model",
        weight=3,
        group="DOMAIN",
        keywords=[
            "b2b", "b2c", "d2c", "dtc", "business to business",
            "wholesale", "retail", "direct to consumer",
            "marketplace", "multi-vendor", "enterprise",
        ],
        question=(
            "What is the primary business model of the platform?"
        ),
        suggestions=[
            "B2C — sell to individual consumers (retail)",
            "B2B — sell to businesses (wholesale, bulk pricing, net terms)",
            "D2C — manufacturer / brand selling direct to consumer",
            "Marketplace — multiple third-party sellers on one platform",
            "B2B2C — sell to businesses who resell to consumers",
            "Subscription box model",
            "Hybrid (e.g. B2C + B2B on same platform)",
        ],
        description="Business model is the most fundamental architectural decision — it shapes pricing, user roles, and checkout rules.",
    ),

    "application_type": SchemaCategory(
        name="application_type",
        weight=3,
        group="DOMAIN",
        keywords=[
            "saas", "standalone", "multi-tenant", "single-tenant",
            "self-hosted", "cloud", "white-label", "on-premise",
        ],
        question=(
            "Should this be a SaaS (multi-tenant) or a standalone (single-tenant) application?"
        ),
        suggestions=[
            "Standalone — single tenant, one client, dedicated infrastructure",
            "SaaS multi-tenant — shared infrastructure, multiple clients",
            "White-label SaaS — rebranded and resold to other businesses",
            "Self-hosted / on-premise (client manages own servers)",
            "Cloud-native managed (AWS / GCP / Azure fully managed services)",
            "Hybrid (self-hosted core + cloud third-party services)",
        ],
        description="SaaS vs standalone is a foundational decision that drives data isolation, billing, and deployment architecture.",
    ),

    "rental_service": SchemaCategory(
        name="rental_service",
        weight=2,
        group="DOMAIN",
        keywords=[
            "rental", "rent", "lease", "hire", "borrow",
            "deposit", "duration", "return date", "availability calendar",
        ],
        question=(
            "Does the platform need to support product rentals in addition to (or instead of) purchases?"
        ),
        suggestions=[
            "No rental — purchase only",
            "Short-term rental (hourly / daily)",
            "Long-term rental (weekly / monthly)",
            "Lease-to-own (rental with purchase option)",
            "Security deposit management",
            "Rental availability calendar (prevent double-booking)",
            "Damage / return condition tracking",
            "Late return fees / rental extensions",
        ],
        description="Rental support requires an availability calendar, deposit logic, and return-condition workflow not present in standard e-commerce.",
    ),

    "order_frequency": SchemaCategory(
        name="order_frequency",
        weight=2,
        group="DOMAIN",
        keywords=[
            "frequency", "repeat", "recurring", "reorder",
            "fast moving", "fmcg", "commodity", "seasonal",
            "subscription", "replenishment",
        ],
        question=(
            "What is the expected order frequency pattern for the primary product type?"
        ),
        suggestions=[
            "High frequency — consumables (groceries, cosmetics, pet food — daily / weekly)",
            "Medium frequency — fashion (clothing, shoes, accessories — monthly / seasonal)",
            "Low frequency — considered purchases (electronics, appliances, furniture — annually)",
            "Subscription-based recurring orders (weekly / monthly auto-replenishment)",
            "Mixed catalog (multiple frequency tiers in one store)",
            "Seasonal / event-driven (gifts, holiday collections)",
            "B2B bulk replenishment (infrequent, high-volume orders)",
        ],
        description="Order frequency determines caching TTL, recommendation engine strategy, and repeat-purchase UX design.",
    ),

    "seo": SchemaCategory(
        name="seo",
        weight=2,
        group="DOMAIN",
        keywords=[
            "seo", "search engine", "google", "sitemap", "slug",
            "meta tag", "canonical", "structured data", "schema.org",
            "open graph", "robots", "page rank",
        ],
        question=(
            "What SEO features are required?"
        ),
        suggestions=[
            "SEO-friendly URL slugs (/products/red-running-shoes)",
            "Editable meta title and description per product / page",
            "Sitemap.xml auto-generation and submission",
            "Structured data / Schema.org markup (rich snippets)",
            "Canonical URLs (prevent duplicate content penalties)",
            "Open Graph tags (Facebook / LinkedIn social sharing)",
            "Twitter Card tags",
            "Robots.txt control",
            "Breadcrumb navigation (helps Google crawl hierarchy)",
        ],
        description="SEO features affect URL routing, page rendering strategy (SSR vs CSR), and CMS architecture.",
    ),

    "geo_location": SchemaCategory(
        name="geo_location",
        weight=2,
        group="DOMAIN",
        keywords=[
            "geo", "geolocation", "location", "region", "country",
            "delivery zone", "shipping zone", "tax zone",
            "ip detection", "local", "store locator",
        ],
        question=(
            "Are geo-location or region-specific features required?"
        ),
        suggestions=[
            "Delivery zone restrictions (only ship to selected countries / regions)",
            "Region-based pricing (different prices per country)",
            "Auto-detect user location via IP geolocation",
            "Country-based currency auto-switch",
            "Tax calculation by jurisdiction (VAT, GST, US state tax)",
            "Store locator / local pickup points on map",
            "Geo-blocking (restrict platform access by country)",
            "GDPR-aware data residency (EU data stays in EU)",
        ],
        description="Geo features affect routing, tax engines, CDN configuration, and data residency compliance.",
    ),

    "multi_currency_language": SchemaCategory(
        name="multi_currency_language",
        weight=2,
        group="DOMAIN",
        keywords=[
            "currency", "multi-currency", "language", "multi-language",
            "i18n", "internationalisation", "localization", "localisation",
            "region", "country", "locale", "translation", "rtl",
        ],
        question=(
            "Is multi-currency or multi-language support required?"
        ),
        suggestions=[
            "Single currency, single language (simplest)",
            "Multi-currency — 2 to 5 currencies",
            "Multi-currency — global (20+ currencies with live FX rates)",
            "Multi-language — 2 to 3 languages",
            "Full i18n (unlimited languages via translation management)",
            "RTL language support (Arabic, Hebrew, Farsi)",
            "Auto-detect locale from browser / IP",
        ],
        description="i18n and multi-currency support affect data models, pricing logic, and frontend rendering architecture.",
    ),

    "inventory_management": SchemaCategory(
        name="inventory_management",
        weight=2,
        group="DOMAIN",
        keywords=[
            "inventory", "stock", "warehouse", "low-stock",
            "backorder", "restock", "out of stock", "quantity",
            "reserve", "allocation",
        ],
        question=(
            "What level of inventory management is required?"
        ),
        suggestions=[
            "Single warehouse — basic stock count per product",
            "Multi-warehouse — stock tracked per location",
            "Real-time stock deduction at order confirmation",
            "Backorder support (purchase allowed when stock = 0)",
            "Low-stock alerts at configurable threshold",
            "Supplier / purchase order management",
            "Barcode / QR code scanning for stock updates",
            "CSV bulk import / export for stock levels",
        ],
        description="Inventory model (single vs multi-warehouse, backorder logic) drives stock reservation and concurrency design.",
    ),
}


# ------------------------------------------------------------------ #
#  Helpers                                                             #
# ------------------------------------------------------------------ #

def get_all_categories() -> List[str]:
    return list(ECOMMERCE_SCHEMA.keys())


def get_category(name: str) -> SchemaCategory:
    return ECOMMERCE_SCHEMA[name]


def get_by_group(group: str) -> Dict[str, SchemaCategory]:
    return {k: v for k, v in ECOMMERCE_SCHEMA.items() if v.group == group}


def get_critical_categories() -> Dict[str, SchemaCategory]:
    return {k: v for k, v in ECOMMERCE_SCHEMA.items() if v.weight == 3}


def total_categories() -> int:
    return len(ECOMMERCE_SCHEMA)


def total_weight() -> int:
    return sum(c.weight for c in ECOMMERCE_SCHEMA.values())
