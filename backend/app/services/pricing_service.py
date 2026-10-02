from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from app.models.pricing import PricingRule
import logging

logger = logging.getLogger("pricing_service")

DEFAULT_PRICING_CONFIGS = [
    # Paper, Color, DoubleSided, Rate, MinPrice
    {"paper_size": "A4", "is_color": False, "is_double_sided": False, "price_per_page": 2.0, "min_order_price": 5.0},
    {"paper_size": "A4", "is_color": False, "is_double_sided": True,  "price_per_page": 1.5, "min_order_price": 5.0},
    {"paper_size": "A4", "is_color": True,  "is_double_sided": False, "price_per_page": 10.0, "min_order_price": 10.0},
    {"paper_size": "A4", "is_color": True,  "is_double_sided": True,  "price_per_page": 8.0, "min_order_price": 10.0},
    
    {"paper_size": "A3", "is_color": False, "is_double_sided": False, "price_per_page": 5.0, "min_order_price": 10.0},
    {"paper_size": "A3", "is_color": False, "is_double_sided": True,  "price_per_page": 4.0, "min_order_price": 10.0},
    {"paper_size": "A3", "is_color": True,  "is_double_sided": False, "price_per_page": 20.0, "min_order_price": 20.0},
    {"paper_size": "A3", "is_color": True,  "is_double_sided": True,  "price_per_page": 15.0, "min_order_price": 20.0},
    
    {"paper_size": "Letter", "is_color": False, "is_double_sided": False, "price_per_page": 2.0, "min_order_price": 5.0},
    {"paper_size": "Letter", "is_color": False, "is_double_sided": True,  "price_per_page": 1.5, "min_order_price": 5.0},
    {"paper_size": "Letter", "is_color": True,  "is_double_sided": False, "price_per_page": 10.0, "min_order_price": 10.0},
    {"paper_size": "Letter", "is_color": True,  "is_double_sided": True,  "price_per_page": 8.0, "min_order_price": 10.0},
]

class PricingService:

    @staticmethod
    def seed_defaults_if_empty(db: Session):
        """Populate initial pricing rules if database is empty."""
        count = db.query(PricingRule).count()
        if count == 0:
            logger.info("Seeding default pricing rules into database...")
            for config in DEFAULT_PRICING_CONFIGS:
                rule = PricingRule(**config)
                db.add(rule)
            db.commit()

    @staticmethod
    def calculate_price(
        db: Session,
        paper_size: str,
        color_mode: str, # "BW" or "Color"
        sides: str,      # "single" or "double"
        total_pages: int,
        copies: int
    ) -> Dict[str, Any]:
        """Calculates total order price dynamically from database pricing rules."""
        is_color = (color_mode.upper() == "COLOR")
        is_double = (sides.lower() == "double")
        paper_size_normalized = paper_size.upper()

        # Query matching active rule
        rule = db.query(PricingRule).filter(
            PricingRule.paper_size == paper_size_normalized,
            PricingRule.is_color == is_color,
            PricingRule.is_double_sided == is_double,
            PricingRule.is_active == True
        ).first()

        # Fallback query if exact double/single rule missing
        if not rule:
            rule = db.query(PricingRule).filter(
                PricingRule.paper_size == paper_size_normalized,
                PricingRule.is_color == is_color,
                PricingRule.is_active == True
            ).first()

        # Fallback default rate if database has no matching rule
        rate_per_page = rule.price_per_page if rule else (10.0 if is_color else 2.0)
        min_order_price = rule.min_order_price if rule else 5.0
        additional_charge = rule.additional_charge if rule else 0.0

        subtotal = total_pages * copies * rate_per_page
        calc_total = subtotal + additional_charge
        final_total = max(min_order_price, calc_total)

        return {
            "rate_per_page": rate_per_page,
            "subtotal": round(subtotal, 2),
            "additional_charge": round(additional_charge, 2),
            "min_order_price": round(min_order_price, 2),
            "total_amount": round(final_total, 2),
            "total_pages": total_pages,
            "copies": copies,
            "paper_size": paper_size_normalized,
            "color_mode": "Color" if is_color else "B&W",
            "sides": "Double-sided" if is_double else "Single-sided"
        }

pricing_service = PricingService()
