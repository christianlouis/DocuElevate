"""View routes for admin plan management pages."""

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.routing import APIRouter

from app.auth import require_login
from app.views.base import templates

router = APIRouter()


@router.get("/admin/plans", response_class=HTMLResponse)
@require_login
async def plan_designer(request: Request) -> HTMLResponse:
    """Admin Plan Designer page."""
    return templates.TemplateResponse("admin_plans.html", {"request": request})


@router.get("/admin/stripe-wizard", response_class=HTMLResponse)
@require_login
async def stripe_wizard(request: Request) -> HTMLResponse:
    """Admin Stripe Setup Wizard page."""
    return templates.TemplateResponse("admin_stripe_wizard.html", {"request": request})
