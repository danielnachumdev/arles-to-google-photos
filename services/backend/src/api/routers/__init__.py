from .auth import router as auth_router
from .events import router as events_router
from .jobs import router as jobs_router
from .publish import router as publish_router
from .scrape import router as scrape_router
from .settings import router as settings_router
from .version import router as version_router

__all__ = [
    "auth_router",
    "events_router",
    "jobs_router",
    "publish_router",
    "scrape_router",
    "settings_router",
    "version_router",
]
