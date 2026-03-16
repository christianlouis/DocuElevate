"""
API Router module that combines all API endpoints
"""

import logging

from fastapi import APIRouter

from app.api.admin_users import router as admin_users_router
from app.api.api_tokens import router as api_tokens_router
from app.api.audit_logs import router as audit_logs_router
from app.api.azure import router as azure_router
from app.api.backup import router as backup_router
from app.api.billing import router as billing_router
from app.api.compliance import router as compliance_router
from app.api.database import router as database_router
from app.api.diagnostic import router as diagnostic_router
from app.api.dropbox import router as dropbox_router
from app.api.duplicates import router as duplicates_router
from app.api.files import router as files_router
from app.api.google_drive import router as google_drive_router
from app.api.i18n import router as i18n_router
from app.api.imap_accounts import router as imap_accounts_router
from app.api.imap_profiles import router as imap_profiles_router
from app.api.integrations import router as integrations_router
from app.api.logs import router as logs_router
from app.api.mobile import router as mobile_router
from app.api.notifications import router as notifications_router
from app.api.onboarding import router as onboarding_router
from app.api.onedrive import router as onedrive_router
from app.api.openai import router as openai_router
from app.api.pipelines import router as pipelines_router
from app.api.plans import router as plans_router
from app.api.process import router as process_router
from app.api.profile import router as profile_router
from app.api.queue import router as queue_router
from app.api.routing_rules import router as routing_rules_router
from app.api.saved_searches import router as saved_searches_router
from app.api.scheduled_jobs import router as scheduled_jobs_router
from app.api.search import router as search_router
from app.api.settings import router as settings_router
from app.api.shared_links import public_router as shared_links_public_router
from app.api.shared_links import router as shared_links_router
from app.api.similarity import router as similarity_router
from app.api.subscriptions import router as subscriptions_router
from app.api.system_reset import router as system_reset_router
from app.api.translation import router as translation_router
from app.api.url_upload import router as url_upload_router

# Import all the individual routers
from app.api.user import router as user_router
from app.api.webhooks import router as webhooks_router

# Set up logging
logger = logging.getLogger(__name__)

# Create the main router that includes all the others
router = APIRouter()

# Include all the routers
router.include_router(admin_users_router)
router.include_router(api_tokens_router)
router.include_router(user_router)
router.include_router(backup_router)
router.include_router(files_router)
router.include_router(process_router)
router.include_router(diagnostic_router)
router.include_router(onedrive_router)
router.include_router(dropbox_router)
router.include_router(openai_router)
router.include_router(azure_router)
router.include_router(google_drive_router)
router.include_router(logs_router)
router.include_router(settings_router)
router.include_router(url_upload_router)
router.include_router(search_router)
router.include_router(queue_router)
router.include_router(saved_searches_router)
router.include_router(similarity_router)
router.include_router(shared_links_router)
router.include_router(shared_links_public_router)
router.include_router(duplicates_router)
router.include_router(webhooks_router)
router.include_router(database_router)
router.include_router(subscriptions_router)
router.include_router(plans_router)
router.include_router(onboarding_router)
router.include_router(billing_router)
router.include_router(pipelines_router)
router.include_router(profile_router)
router.include_router(routing_rules_router)
router.include_router(imap_accounts_router)
router.include_router(imap_profiles_router)
router.include_router(integrations_router)
router.include_router(notifications_router)
router.include_router(scheduled_jobs_router)
router.include_router(audit_logs_router)
router.include_router(i18n_router)
router.include_router(mobile_router)
router.include_router(compliance_router)
router.include_router(system_reset_router)
router.include_router(translation_router)
