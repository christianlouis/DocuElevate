"""
Aggregated view routers for the application.
"""

from fastapi import APIRouter

from app.views.admin_users import router as admin_users_router
from app.views.api_tokens import router as api_tokens_router
from app.views.backup import router as backup_router
from app.views.compliance import router as compliance_router
from app.views.db_wizard import router as db_wizard_router
from app.views.dropbox import router as dropbox_router
from app.views.filemanager import router as filemanager_router

# Import all the view routers
from app.views.general import router as general_router
from app.views.google_drive import router as google_drive_router
from app.views.help import router as help_router  # Built-in help / How-To docs
from app.views.imap_accounts import router as imap_accounts_router
from app.views.integrations import router as integrations_router  # Unified integrations dashboard
from app.views.license_routes import router as license_router  # Add the license router
from app.views.notifications import router as notifications_router
from app.views.onboarding import router as onboarding_router
from app.views.onedrive import router as onedrive_router
from app.views.pipelines import router as pipelines_router  # Processing pipelines
from app.views.plans import router as plans_router  # Admin Plan Designer
from app.views.queue import router as queue_router
from app.views.scheduled_jobs import router as scheduled_jobs_router  # Scheduled batch jobs
from app.views.search import router as search_router
from app.views.settings import router as settings_router
from app.views.share import router as share_router
from app.views.shared_links import router as shared_links_router
from app.views.status import router as status_router
from app.views.subscriptions import router as subscriptions_router  # Pricing + subscription pages
from app.views.wizard import router as wizard_router

# Create a main router that includes all the view routers
router = APIRouter()
router.include_router(wizard_router)  # Wizard first (for /setup)
router.include_router(db_wizard_router)  # Database wizard
router.include_router(admin_users_router)  # Admin user management
router.include_router(api_tokens_router)  # API token management
router.include_router(shared_links_router)  # Shared links management
router.include_router(share_router)  # Public share landing pages (no auth)
router.include_router(backup_router)  # Backup dashboard
router.include_router(general_router)
router.include_router(status_router)
router.include_router(onedrive_router)
router.include_router(dropbox_router)
router.include_router(google_drive_router)
router.include_router(license_router)  # Include the license router
router.include_router(settings_router)
router.include_router(filemanager_router)
router.include_router(search_router)
router.include_router(queue_router)
router.include_router(subscriptions_router)  # Pricing + subscription pages
router.include_router(plans_router)  # Admin Plan Designer
router.include_router(onboarding_router)  # User onboarding wizard
router.include_router(pipelines_router)  # Processing pipelines
router.include_router(imap_accounts_router)  # Per-user IMAP ingestion accounts
router.include_router(integrations_router)  # Unified integrations dashboard
router.include_router(notifications_router)  # User notification dashboard
router.include_router(scheduled_jobs_router)  # Admin scheduled batch jobs
router.include_router(help_router)  # Built-in help / How-To docs
router.include_router(compliance_router)  # Compliance templates dashboard
