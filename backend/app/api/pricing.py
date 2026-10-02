from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.admin import Admin
from app.models.pricing import PricingRule
from app.schemas.pricing import PricingRuleCreate, PricingRuleUpdate, PricingRuleOut
from app.api.auth import get_current_admin
from app.services.pricing_service import pricing_service

router = APIRouter(prefix="/api/pricing", tags=["Pricing Engine"])

@router.get("", response_model=List[PricingRuleOut])
def get_pricing_rules(
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    """Retrieve all pricing rules for paper sizes, color modes, and sides."""
    pricing_service.seed_defaults_if_empty(db)
    rules = db.query(PricingRule).order_by(PricingRule.paper_size, PricingRule.is_color).all()
    return rules

@router.post("", response_model=PricingRuleOut)
def create_pricing_rule(
    req: PricingRuleCreate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    """Create a new pricing rule."""
    rule = PricingRule(**req.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule

@router.put("/{rule_id}", response_model=PricingRuleOut)
def update_pricing_rule(
    rule_id: int,
    req: PricingRuleUpdate,
    db: Session = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin)
):
    """Update price per page, minimum price, or additional fees."""
    rule = db.query(PricingRule).filter(PricingRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Pricing rule not found")

    for key, val in req.model_dump(exclude_unset=True).items():
        setattr(rule, key, val)

    db.commit()
    db.refresh(rule)
    return rule
