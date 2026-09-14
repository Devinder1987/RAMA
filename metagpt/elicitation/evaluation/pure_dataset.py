"""
PURE Dataset Loader (W7a)
--------------------------
Loads SRS documents for PURE baseline evaluation.

Two modes:
  1. Built-in samples  — 10 representative e-commerce SRS documents
     at varying completeness levels (POOR → COMPLETE), ready to use
     without any external files.

  2. Directory loading — reads .txt files from a given directory.
     Use this to load the real 79-document PURE dataset:

       Ferrari A. et al. (2017). PURE: A Dataset of Public Requirements
       Documents. IEEE Requirements Engineering Conference.
       https://github.com/ArDoCo/PURE

     Place PURE .txt files in:  pure_data/srs/  (project root)
     Then call: PUREDatasetLoader.load(Path("pure_data/srs"))

RAMA Thesis — Devinder Shuthwal, LJMU 2026
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


# ------------------------------------------------------------------ #
#  Data model                                                          #
# ------------------------------------------------------------------ #

@dataclass
class PURESample:
    """One SRS document to be evaluated by the RAMA pipeline."""
    doc_id:     str    # e.g. "PURE-S01" or stem of filename
    filename:   str    # original filename (for traceability)
    raw_text:   str    # full SRS text
    domain:     str    # "ecommerce" | "mixed" | "other"
    word_count: int    # pre-computed from raw_text
    source:     str    # "builtin" | "file"

    def __post_init__(self):
        if self.word_count == 0:
            self.word_count = len(self.raw_text.split())


# ------------------------------------------------------------------ #
#  Built-in sample corpus                                              #
# ------------------------------------------------------------------ #
# Ten representative e-commerce SRS documents spanning POOR → COMPLETE
# completeness levels, used when the real PURE dataset is unavailable.

_BUILTIN_RAW: List[dict] = [
    {
        "doc_id": "PURE-S01",
        "filename": "sample_01_vague.txt",
        "domain": "ecommerce",
        "raw_text": (
            "Build an online shop where users can buy products. "
            "The system should be fast and easy to use. "
            "We need it done in three months."
        ),
    },
    {
        "doc_id": "PURE-S02",
        "filename": "sample_02_simple_store.txt",
        "domain": "ecommerce",
        "raw_text": (
            "We need an e-commerce website where customers can browse and purchase products. "
            "Users should be able to create accounts and log in securely. "
            "Products should be organised in categories for easy navigation. "
            "The platform needs a shopping cart and checkout process. "
            "Payment via credit card is required."
        ),
    },
    {
        "doc_id": "PURE-S03",
        "filename": "sample_03_basic_admin.txt",
        "domain": "ecommerce",
        "raw_text": (
            "Build a web-based online store for selling electronic products. "
            "Customers can register, login, browse the product catalogue, add items to cart, and place orders. "
            "Admins can add, edit, and delete products and manage inventory levels. "
            "Order management allows admins to view and update order status. "
            "Payment processing via credit card should be supported. "
            "The website must be secure and handle concurrent users. "
            "Product reviews and ratings should be available for customers. "
            "Email notifications for order confirmations are required."
        ),
    },
    {
        "doc_id": "PURE-S04",
        "filename": "sample_04_b2c_nfr.txt",
        "domain": "ecommerce",
        "raw_text": (
            "Develop a B2C e-commerce platform for a clothing retailer. "
            "Customers can browse products by category, use search and filters, "
            "add items to cart, and checkout using PayPal or Stripe. "
            "User authentication with secure login and registration is required. "
            "The platform should support order tracking and a returns management workflow. "
            "Admins manage the product catalogue, inventory levels, and promotional discounts. "
            "The system must support 10,000 concurrent users with page load times under 3 seconds. "
            "GDPR compliance is mandatory for EU customers. "
            "Product pages must be SEO-optimised with structured metadata and canonical URLs. "
            "Mobile-responsive design is required across all device sizes."
        ),
    },
    {
        "doc_id": "PURE-S05",
        "filename": "sample_05_multi_vendor.txt",
        "domain": "ecommerce",
        "raw_text": (
            "Build a multi-vendor marketplace where multiple sellers list and sell products. "
            "Customers browse, search, and purchase from different vendors via a unified cart. "
            "Vendor registration, profile management, and an admin approval workflow are required. "
            "Each vendor manages their own product catalogue and inventory independently. "
            "The platform charges a 15% commission on each completed sale. "
            "Payment processing via Stripe with automatic vendor payouts upon order completion. "
            "Order management tracks which vendor is responsible for each line item. "
            "Customers can leave product reviews and view overall vendor ratings. "
            "The platform must scale to 500 vendors and 1 million product listings. "
            "An analytics dashboard allows vendors to track sales, revenue, and conversion metrics."
        ),
    },
    {
        "doc_id": "PURE-S06",
        "filename": "sample_06_subscription.txt",
        "domain": "ecommerce",
        "raw_text": (
            "Build an e-commerce platform for selling subscription boxes to consumers. "
            "Customers subscribe to monthly, quarterly, or annual membership plans. "
            "Recurring payment processing via Stripe with automatic renewal and retry logic. "
            "Customers can pause, skip a cycle, or cancel via a self-service portal. "
            "One-time product purchases are supported alongside active subscriptions. "
            "Customers select personalisation preferences at signup to customise box contents. "
            "Inventory management tracks subscription fulfilment quantities per delivery cycle. "
            "Admin dashboard shows subscriber counts, churn rate, and revenue per plan tier. "
            "Email notifications are sent for upcoming renewals, successful charges, and shipments. "
            "Customer portal supports updating payment methods, delivery addresses, and preferences."
        ),
    },
    {
        "doc_id": "PURE-S07",
        "filename": "sample_07_fashion.txt",
        "domain": "ecommerce",
        "raw_text": (
            "Build a fashion e-commerce platform with social commerce features. "
            "Customers browse and filter products by style, size, colour, and brand. "
            "User-generated lookbooks: customers share outfit photos with tagged products. "
            "Personalised product recommendations based on browsing history and purchase behaviour. "
            "Size guide and fit predictor to reduce return rates. "
            "Wishlist functionality with sharing capabilities. "
            "Multi-step checkout with address autocomplete and saved payment methods via Stripe. "
            "Free standard shipping on orders over £50; express shipping available at checkout. "
            "Order tracking with carrier API integration and SMS delivery notifications. "
            "Self-service returns: customers generate return labels from the order portal. "
            "Loyalty programme with Silver, Gold, and Platinum membership tiers. "
            "Admins manage brand partnerships, seasonal promotions, and discount codes. "
            "Product reviews support photo uploads and a verified-purchase badge. "
            "Social login via Google and Facebook is supported at registration."
        ),
    },
    {
        "doc_id": "PURE-S08",
        "filename": "sample_08_grocery.txt",
        "domain": "ecommerce",
        "raw_text": (
            "Build an online grocery ordering and home delivery platform. "
            "Customers browse products by department, use search with autocomplete, and add to cart. "
            "Real-time inventory reflects current store stock to prevent overselling. "
            "Customers select 2-hour delivery windows up to 7 days in advance. "
            "Substitution preferences let customers accept or reject out-of-stock alternatives. "
            "Same-day delivery is available for orders placed before 12:00 noon. "
            "Geo-location identifies the nearest fulfilment store and delivery coverage. "
            "Payment via credit card, Apple Pay, and EBT for eligible customers. "
            "Promotional pricing and loyalty discounts applied automatically at checkout. "
            "Minimum order value of £35 is enforced for home delivery. "
            "Driver mobile app provides route optimisation and delivery confirmation. "
            "Age verification workflow enforced for alcohol and tobacco products. "
            "SMS and push notifications update customers on picking, packing, and delivery status. "
            "The platform must handle 50,000 concurrent users during peak shopping periods."
        ),
    },
    {
        "doc_id": "PURE-S09",
        "filename": "sample_09_b2b_wholesale.txt",
        "domain": "ecommerce",
        "raw_text": (
            "Develop a B2B wholesale ordering portal for an industrial supplies manufacturer. "
            "Business customers register and are vetted by the sales team before account activation. "
            "Tiered pricing: 5% discount for orders over £5,000 and 10% for orders over £20,000. "
            "Product catalogue with 50,000 SKUs supporting size, material, and finish variants. "
            "Minimum order quantities are enforced at the individual product level. "
            "Purchase orders and tax-compliant invoices are generated automatically for each order. "
            "Net 30 and Net 60 payment terms are managed against per-customer credit limits. "
            "ERP integration synchronises real-time inventory levels and order status. "
            "Sales representatives can log in and place orders on behalf of assigned customers. "
            "Quote request workflow: customers submit RFQ, sales reps respond within 24 hours. "
            "Shipping to multiple business addresses with freight cost calculation by weight and zone. "
            "Tax exemption certificate upload and validation for eligible business customers. "
            "Order history and one-click reorder functionality for repeat purchases. "
            "Admin reporting covers monthly sales by account, product turnover, and outstanding invoices."
        ),
    },
    {
        "doc_id": "PURE-S10",
        "filename": "sample_10_comprehensive.txt",
        "domain": "ecommerce",
        "raw_text": (
            "Build a comprehensive multi-category e-commerce platform for a national retailer. "
            "The platform targets B2C consumers and must support 200,000 concurrent users with sub-2-second page loads. "
            "Customer registration and login via email/password or OAuth 2.0 with Google and Facebook. "
            "Full product catalogue with hierarchical categories, faceted search, and AI-powered personalised recommendations. "
            "Product pages include high-resolution images, videos, detailed descriptions, specifications, "
            "and customer reviews with photo uploads and verified-purchase badges. "
            "Shopping cart persists across sessions; wishlist with price-drop email notifications. "
            "Multi-step checkout: address selection, delivery option, payment, and order review. "
            "Payment methods: Visa, Mastercard, PayPal, Apple Pay, Google Pay, and Klarna buy-now-pay-later. "
            "PCI-DSS Level 1 compliance for all payment data; GDPR and CCPA data protection. "
            "Order management: real-time status updates, courier tracking integration, and estimated delivery dates. "
            "Self-service returns portal: customers initiate returns, print labels, and track refund status. "
            "Inventory management with low-stock alerts, automatic reorder points, and multi-warehouse support. "
            "Promotions engine: percentage and fixed-amount discount coupons, buy-X-get-Y, flash sales, and bundle deals. "
            "Loyalty programme: points earned per purchase, redeemable for discounts; Silver, Gold, and Platinum tiers. "
            "Vendor marketplace: third-party sellers list products; platform charges 12% commission with automatic payouts. "
            "SEO: canonical URLs, structured data (schema.org), XML sitemaps, and admin meta-tag management. "
            "Admin dashboard: sales analytics, customer cohort analysis, and inventory reports. "
            "Native iOS and Android mobile applications with full feature parity to the web platform. "
            "Availability: 99.9% uptime SLA with automated failover across two geographic regions. "
            "Accessibility: WCAG 2.1 AA compliance across all customer-facing pages."
        ),
    },
]


# ------------------------------------------------------------------ #
#  Loader                                                              #
# ------------------------------------------------------------------ #

class PUREDatasetLoader:
    """
    Loads PURESample objects for PURE baseline evaluation.

    Usage:
        samples = PUREDatasetLoader.load_builtin()          # 10 built-in docs
        samples = PUREDatasetLoader.load_from_dir(path)     # .txt files
        samples = PUREDatasetLoader.load(path)              # auto-detect
    """

    @staticmethod
    def load_builtin() -> List[PURESample]:
        """Return the 10 built-in sample SRS documents."""
        samples = []
        for d in _BUILTIN_RAW:
            text = d["raw_text"]
            samples.append(PURESample(
                doc_id=d["doc_id"],
                filename=d["filename"],
                raw_text=text,
                domain=d["domain"],
                word_count=len(text.split()),
                source="builtin",
            ))
        return samples

    @staticmethod
    def load_from_dir(path: Path) -> List[PURESample]:
        """
        Load .txt SRS files from a directory.
        Files are sorted alphabetically; doc_id is the filename stem.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"PURE dataset directory not found: {path}")

        samples = []
        for txt_file in sorted(path.glob("*.txt")):
            text = txt_file.read_text(encoding="utf-8", errors="replace").strip()
            if not text:
                continue
            samples.append(PURESample(
                doc_id=txt_file.stem,
                filename=txt_file.name,
                raw_text=text,
                domain="ecommerce",
                word_count=len(text.split()),
                source="file",
            ))
        return samples

    @staticmethod
    def load(path: Optional[Path] = None) -> List[PURESample]:
        """
        Auto-detect: load from directory if it exists and contains .txt files,
        otherwise fall back to built-in samples.
        """
        if path is not None:
            path = Path(path)
            if path.exists() and any(path.glob("*.txt")):
                return PUREDatasetLoader.load_from_dir(path)

        default_dir = Path(__file__).parent.parent.parent.parent / "pure_data" / "srs"
        if default_dir.exists() and any(default_dir.glob("*.txt")):
            return PUREDatasetLoader.load_from_dir(default_dir)

        return PUREDatasetLoader.load_builtin()


# ------------------------------------------------------------------ #
#  CLI entry point                                                     #
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    samples = PUREDatasetLoader.load_builtin()
    print(f"Loaded {len(samples)} built-in PURE samples\n")
    for s in samples:
        print(f"  {s.doc_id:<12}  words={s.word_count:<4}  domain={s.domain}  source={s.source}")
        print(f"             {s.raw_text[:90]}...")
        print()
