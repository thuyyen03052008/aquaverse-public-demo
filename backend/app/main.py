"""AQUAVERSE Phase 5A: authenticated local-first API."""

from contextlib import asynccontextmanager
import os
from pathlib import Path
from time import monotonic
from collections import defaultdict, deque
from threading import Lock
from fastapi.responses import FileResponse, JSONResponse
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db, init_database
from .auth import router as auth_router, current_user, authorize_resource, require_farm_owner, owned_farm_for_tank
from .auth_models import FarmOwnership, User
from .journal_routes import router as journal_router
from .decision_routes import router as decision_router
from .outcome_routes import router as outcome_router
from .mentor_routes import router as mentor_router
from .connect_routes import router as connect_router
from .models import CultureSystem, Farm, FarmingUnit, ProductionCycle, Species
from .schemas import (
    CultureSystemRead, CycleCreate, CycleRead,
    FarmCreate, FarmRead, SpeciesRead, TankCreate, TankRead,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.getenv('AQUAVERSE_PUBLIC_DEMO') == '1':
        if os.getenv('AQUAVERSE_DEMO_AUTOLOGIN') == '1':
            raise RuntimeError('Cannot mix isolated local demo and public visitor demo')
        if os.getenv('AQUAVERSE_SECURE_COOKIES') != '1':
            raise RuntimeError('Public demo requires secure session cookies')
        if os.getenv('OPENAI_API_KEY'):
            raise RuntimeError('Public demo must not expose a billable AI key')
    init_database()
    yield


app = FastAPI(title="AQUAVERSE API", version="0.9.0", lifespan=lifespan)

# CORS restricted to local development; owner-scoped cookie auth.
# Still NOT public-production-ready (rate limits, email validation, deployment security).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "aquaverse-api", "version": "0.9.0"}


@app.get("/api/species", response_model=list[SpeciesRead])
def list_species(db: Session = Depends(get_db)):
    return db.scalars(select(Species).order_by(Species.common_name_vi)).all()


@app.get("/api/culture-systems", response_model=list[CultureSystemRead])
def list_culture_systems(db: Session = Depends(get_db)):
    return db.scalars(select(CultureSystem).order_by(CultureSystem.name_vi)).all()


@app.get("/api/farms", response_model=list[FarmRead])
def list_farms(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Farm).join(FarmOwnership, Farm.id == FarmOwnership.farm_id).where(FarmOwnership.user_id == user.id).order_by(Farm.id)).all()


@app.post("/api/farms", response_model=FarmRead, status_code=status.HTTP_201_CREATED)
def create_farm(data: FarmCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    farm = Farm(**data.model_dump())
    db.add(farm)
    db.flush()
    db.add(FarmOwnership(farm_id=farm.id, user_id=user.id))
    db.commit()
    db.refresh(farm)
    return farm


@app.get("/api/farms/{farm_id}/tanks", response_model=list[TankRead])
def list_tanks(farm_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_farm_owner(db, farm_id, user.id)
    if db.get(Farm, farm_id) is None:
        raise HTTPException(status_code=404, detail="Farm not found")
    return db.scalars(select(FarmingUnit).where(FarmingUnit.farm_id == farm_id).order_by(FarmingUnit.id)).all()


@app.post("/api/farms/{farm_id}/tanks", response_model=TankRead, status_code=status.HTTP_201_CREATED)
def create_tank(farm_id: int, data: TankCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    require_farm_owner(db, farm_id, user.id)
    if db.get(Farm, farm_id) is None:
        raise HTTPException(status_code=404, detail="Farm not found")
    if db.get(CultureSystem, data.culture_system_id) is None:
        raise HTTPException(status_code=422, detail="Unsupported culture system")
    # The only supported Phase 1 culture system is the mud-free tank.
    if data.culture_system_id != "mudfree_tank":
        raise HTTPException(status_code=422, detail="Culture system not yet validated for this MVP")
    tank = FarmingUnit(farm_id=farm_id, **data.model_dump())
    db.add(tank)
    db.commit()
    db.refresh(tank)
    return tank


@app.get("/api/tanks/{tank_id}/cycles", response_model=list[CycleRead])
def list_cycles(tank_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    farm_id = owned_farm_for_tank(db, tank_id)
    if farm_id is None:
        raise HTTPException(status_code=404, detail="Tank not found")
    require_farm_owner(db, farm_id, user.id)
    if db.get(FarmingUnit, tank_id) is None:
        raise HTTPException(status_code=404, detail="Tank not found")
    return db.scalars(select(ProductionCycle).where(ProductionCycle.unit_id == tank_id).order_by(ProductionCycle.id)).all()


@app.post("/api/tanks/{tank_id}/cycles", response_model=CycleRead, status_code=status.HTTP_201_CREATED)
def create_cycle(tank_id: int, data: CycleCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    farm_id = owned_farm_for_tank(db, tank_id)
    if farm_id is None:
        raise HTTPException(status_code=404, detail="Tank not found")
    require_farm_owner(db, farm_id, user.id)
    if db.get(FarmingUnit, tank_id) is None:
        raise HTTPException(status_code=404, detail="Tank not found")
    species = db.get(Species, data.species_id)
    if species is None or species.status != "pilot":
        raise HTTPException(status_code=422, detail="Species is not supported in the current MVP")
    cycle = ProductionCycle(unit_id=tank_id, **data.model_dump())
    db.add(cycle)
    db.commit()
    db.refresh(cycle)
    return cycle


# Public auth endpoints; private routes require a valid session and owner checks.
app.include_router(auth_router)

# Journal tables are added by SQLAlchemy create_all on lifespan startup.
app.include_router(journal_router, dependencies=[Depends(authorize_resource)])

app.include_router(decision_router, dependencies=[Depends(authorize_resource)])

app.include_router(outcome_router, dependencies=[Depends(authorize_resource)])

# Source-grounded AquaMentor; does not access private farm records.
app.include_router(mentor_router, dependencies=[Depends(current_user)])

# AquaConnect Lite — local-only quality documentation and public-preview traceability.
def authorize_public_or_owner(request: Request, db: Session = Depends(get_db)):
    if request.url.path.startswith('/api/public/trace/') and request.method == 'GET':
        return None
    return authorize_resource_direct(request, db)


def authorize_resource_direct(request: Request, db: Session):
    """Same guard as Depends(authorize_resource), invoked with FastAPI injected user."""
    from .auth import current_session, require_farm_owner, owned_farm_for_batch, owned_farm_for_cycle
    from .auth import COOKIE_NAME
    from .auth_models import User
    import secrets
    session = current_session(request, db)
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and not secrets.compare_digest(
        request.headers.get('X-AQUAVERSE-CSRF', ''), session.csrf_token
    ):
        raise HTTPException(status_code=403, detail='Missing or invalid CSRF token')
    user = db.get(User, session.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail='User not found')
    path = request.path_params
    if 'batch_id' in path:
        farm_id = owned_farm_for_batch(db, int(path['batch_id']))
    elif 'cycle_id' in path:
        farm_id = owned_farm_for_cycle(db, int(path['cycle_id']))
    else:
        raise HTTPException(status_code=404, detail='Resource not found')
    if farm_id is None:
        raise HTTPException(status_code=404, detail='Resource not found')
    require_farm_owner(db, farm_id, user.id)
    return user


# Public trace is deliberately excluded from auth guard; all other Connect endpoints
# are guarded by a route-aware permission check.
app.include_router(connect_router, dependencies=[Depends(authorize_public_or_owner)])


# For deployment, FastAPI serves the Vite production build from the same host.
# This avoids exposing the local dev server or relying on cross-site auth cookies.
_PUBLIC_DIST = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'


@app.middleware('http')
async def public_demo_safety(request: Request, call_next):
    if os.getenv('AQUAVERSE_PUBLIC_DEMO') == '1':
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            # Block uploads/private documents and account auth in the anonymous demo.
            if (request.url.path.endswith('/documents') and request.method == 'POST') or request.url.path in ('/api/auth/register', '/api/auth/login'):
                return JSONResponse({'detail': 'Not available in public demo'}, status_code=403)
            if int(request.headers.get('content-length') or '0') > 100_000:
                return JSONResponse({'detail': 'Request too large for public demo'}, status_code=413)
        # With a single Render instance this is a modest abuse control, not a WAF.
        if request.method == 'POST':
            ip = request.client.host if request.client else 'unknown'
            now = monotonic()
            with _public_rate_lock:
                hits = _public_rate[ip]
                while hits and now - hits[0] > 60:
                    hits.popleft()
                if len(hits) >= 80:
                    return JSONResponse({'detail': 'Rate limit reached'}, status_code=429)
                hits.append(now)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['X-Frame-Options'] = 'DENY'
    if os.getenv('AQUAVERSE_PUBLIC_DEMO') == '1':
        response.headers['Cache-Control'] = 'no-store' if request.url.path.startswith('/api/') else 'public, max-age=300'
    return response


_public_rate_lock = Lock()
_public_rate = defaultdict(deque)


@app.get('/{asset_path:path}', include_in_schema=False)
def static_web_app(asset_path: str):
    if asset_path.startswith('api/') or not _PUBLIC_DIST.is_dir():
        raise HTTPException(status_code=404, detail='Not found')
    file = (_PUBLIC_DIST / asset_path).resolve()
    if file.is_file() and file.is_relative_to(_PUBLIC_DIST.resolve()):
        return FileResponse(file)
    if asset_path.startswith('assets/') or ('.' in asset_path.split('/')[-1]):
        raise HTTPException(status_code=404, detail='Asset not found')
    return FileResponse(_PUBLIC_DIST / 'index.html')
