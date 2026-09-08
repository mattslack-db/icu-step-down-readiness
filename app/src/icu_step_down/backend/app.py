from .core import create_app
from .router import router
from .routers.analytics import router as analytics_router
from .routers.census import router as census_router
from .routers.patients import router as patients_router

app = create_app(routers=[router, census_router, patients_router, analytics_router])
