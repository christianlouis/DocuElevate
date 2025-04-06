"""
Status and configuration views for the application.
"""
from fastapi import Request
from datetime import datetime
import os
import subprocess

from app.views.base import APIRouter, templates, require_login, settings

router = APIRouter()

@router.get("/status")
@require_login
async def status_dashboard(request: Request):
    """
    Status dashboard showing all configured integration targets
    """
    from app.utils.config_validator import get_provider_status
    
    # Get provider status
    providers = get_provider_status()
    
    # Get build date from settings
    build_date = getattr(settings, 'build_date', 'Unknown')
    
    # Try to get container information
    container_info = {}
    try:
        # Check for Docker environment
        if os.path.exists('/.dockerenv'):
            # We're inside a Docker container
            container_info['is_docker'] = True
            
            # Try to get container ID
            try:
                with open('/proc/self/cgroup', 'r') as f:
                    for line in f:
                        if 'docker' in line:
                            container_id = line.split('/')[-1].strip()
                            container_info['id'] = container_id[:12]  # Short ID format
                            break
            except Exception:
                container_info['id'] = 'Unknown'
            
            # Try to get Git commit SHA from runtime info
            try:
                # First check runtime info directory
                if os.path.exists('/app/runtime_info/GIT_SHA'):
                    with open('/app/runtime_info/GIT_SHA', 'r') as f:
                        git_sha = f.read().strip()
                # Then try environment variable
                else:
                    git_sha = os.environ.get('GIT_COMMIT_SHA', '')
                
                # If still not found, try the original file location
                if not git_sha and os.path.exists('/.git-commit-sha'):
                    with open('/.git-commit-sha', 'r') as f:
                        git_sha = f.read().strip()
                
                container_info['git_sha'] = git_sha[:7] if git_sha and git_sha != 'unknown' else 'Unknown'
            except Exception:
                container_info['git_sha'] = 'Unknown'
            
            # Try to get runtime information
            try:
                if os.path.exists('/app/runtime_info/RUNTIME_INFO'):
                    with open('/app/runtime_info/RUNTIME_INFO', 'r') as f:
                        container_info['runtime_info'] = f.read().strip()
            except Exception:
                pass
        else:
            container_info['is_docker'] = False
            
            # If not in Docker, try to get Git info directly
            try:
                git_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], 
                                                stderr=subprocess.DEVNULL, 
                                                text=True).strip()[:7]
                container_info['git_sha'] = git_sha
            except (subprocess.SubprocessError, FileNotFoundError):
                container_info['git_sha'] = 'Unknown'
    except Exception:
        container_info = {'is_docker': False, 'id': 'Unknown', 'git_sha': 'Unknown'}
    
    return templates.TemplateResponse(
        "status_dashboard.html",
        {
            "request": request, 
            "providers": providers,
            "app_version": settings.version,
            "build_date": build_date,
            "debug_enabled": getattr(settings, 'debug', False),
            "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "container_info": container_info
        }
    )

@router.get("/env")
@require_login
async def env_debug(request: Request):
    """
    Debug endpoint to view environment variables and settings
    Uses actual debug setting from config
    """
    # Use the actual debug setting from configuration
    debug_enabled = settings.debug
    
    # Get settings data
    from app.utils.config_validator import get_settings_for_display
    settings_data = get_settings_for_display(show_values=debug_enabled)
    
    return templates.TemplateResponse(
        "env_debug.html",
        {
            "request": request, 
            "settings": settings_data,
            "debug_enabled": debug_enabled,
            "app_version": settings.version
        }
    )
