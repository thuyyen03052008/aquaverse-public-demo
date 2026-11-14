"""Local-first session authentication and farm ownership enforcement.

The cookie is HttpOnly and sessions are stored hashed in SQLite. Mutating
endpoints require an anti-CSRF header. This is not yet a hardened public auth
service: rate limits, email verification, and HTTPS deployment remain P1 tasks.
"""

from datetime import datetime, timedelta
import hashlib
import os
import re
import secrets
import time
from collections import defaultdict, deque
from threading import Lock
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth_models import FarmOwnership, LoginSession, User, utcnow
from .connect_models import HarvestBatch
from .db import get_db
from .models import FarmingUnit, ProductionCycle

COOKIE_NAME = 'aquaverse_session'
SESSION_HOURS = 24
hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=2)
router = APIRouter(prefix='/api/auth', tags=['AquaAccount'])


class RegisterData(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=12, max_length=128)
    display_name: str = Field(min_length=2, max_length=120)

    @field_validator('email')
    @classmethod
    def email_format(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value, flags=re.ASCII):
            raise ValueError('Please enter a valid email address')
        return value


class LoginData(BaseModel):
    email: str
    password: str


class ProfileData(BaseModel):
    display_name: str = Field(min_length=2, max_length=120)
    experience_level: str = Field(pattern='^(beginner|intermediate|experienced)$')
    goal: str = Field(min_length=2, max_length=200)
    preferred_species_id: str = Field(default='monopterus_albus', max_length=80)


def serialize_user(user: User) -> dict:
    return {'id': user.id, 'email': user.email, 'display_name': user.display_name,
            'experience_level': user.experience_level, 'goal': user.goal,
            'preferred_species_id': user.preferred_species_id}


def _session_digest(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def current_session(request: Request, db: Session) -> LoginSession:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail='Vui lòng đăng nhập')
    row = db.scalar(select(LoginSession).where(LoginSession.token_sha256 == _session_digest(token)))
    if row is None or row.expires_at <= utcnow():
        raise HTTPException(status_code=401, detail='Phiên đăng nhập không hợp lệ hoặc đã hết hạn')
    return row


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth = current_session(request, db)
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        provided = request.headers.get('X-AQUAVERSE-CSRF', '')
        if not secrets.compare_digest(provided, auth.csrf_token):
            raise HTTPException(status_code=403, detail='Missing or invalid CSRF token')
    user = db.get(User, auth.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail='User no longer exists')
    return user


def require_farm_owner(db: Session, farm_id: int, user_id: int):
    owner = db.get(FarmOwnership, farm_id)
    if owner is None or owner.user_id != user_id:
        raise HTTPException(status_code=404, detail='Resource not found')


def owned_farm_for_tank(db: Session, tank_id: int) -> int | None:
    tank = db.get(FarmingUnit, tank_id)
    return None if tank is None else tank.farm_id


def owned_farm_for_cycle(db: Session, cycle_id: int) -> int | None:
    cycle = db.get(ProductionCycle, cycle_id)
    return None if cycle is None else owned_farm_for_tank(db, cycle.unit_id)


def owned_farm_for_batch(db: Session, batch_id: int) -> int | None:
    batch = db.get(HarvestBatch, batch_id)
    return None if batch is None else owned_farm_for_cycle(db, batch.cycle_id)


def authorize_resource(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Central owner guard for all existing nested API routes."""
    path = request.path_params
    if 'batch_id' in path:
        farm_id = owned_farm_for_batch(db, int(path['batch_id']))
    elif 'cycle_id' in path:
        farm_id = owned_farm_for_cycle(db, int(path['cycle_id']))
    elif 'tank_id' in path:
        farm_id = owned_farm_for_tank(db, int(path['tank_id']))
    elif 'farm_id' in path:
        farm_id = int(path['farm_id'])
    else:
        return user  # e.g. mentor question with no resource ID
    if farm_id is None:
        raise HTTPException(status_code=404, detail='Resource not found')
    require_farm_owner(db, farm_id, user.id)
    return user


def _set_session(response: Response, user: User, db: Session) -> dict:
    token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    db.add(LoginSession(user_id=user.id, token_sha256=_session_digest(token), csrf_token=csrf_token,
                        expires_at=utcnow() + timedelta(hours=SESSION_HOURS)))
    db.commit()
    response.set_cookie(
        key=COOKIE_NAME, value=token, httponly=True, secure=os.getenv('AQUAVERSE_SECURE_COOKIES') == '1',
        samesite='lax', max_age=SESSION_HOURS * 3600, path='/api',
    )
    return {'user': serialize_user(user), 'csrf_token': csrf_token}


@router.post('/register', status_code=status.HTTP_201_CREATED)
def register(payload: RegisterData, response: Response, db: Session = Depends(get_db)):
    # Default-off self registration: demo accounts are seeded offline.
    if os.getenv('AQUAVERSE_PUBLIC_DEMO') == '1' or os.getenv('AQUAVERSE_ALLOW_SELF_SIGNUP') != '1':
        raise HTTPException(status_code=403, detail='Chức năng đăng ký đã tắt. Vui lòng dùng tài khoản đã được cấp.')
    if db.scalar(select(User.id).where(User.email == payload.email)):
        raise HTTPException(status_code=409, detail='Email đã được đăng ký')
    user = User(email=payload.email, password_hash=hasher.hash(payload.password), display_name=payload.display_name)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail='Email đã được đăng ký')
    db.refresh(user)
    return _set_session(response, user, db)


@router.post('/login')
def login(payload: LoginData, response: Response, db: Session = Depends(get_db)):
    if os.getenv('AQUAVERSE_PUBLIC_DEMO') == '1':
        raise HTTPException(status_code=403, detail='Public demo does not accept password logins')
    user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
    try:
        verified = user is not None and hasher.verify(user.password_hash, payload.password)
    except (VerifyMismatchError, VerificationError):
        verified = False
    if not verified:
        raise HTTPException(status_code=401, detail='Email hoặc mật khẩu không đúng')
    return _set_session(response, user, db)




def _require_isolated_local_demo(request: Request, db: Session) -> None:
    """Fail closed: passwordless bootstrap ONLY for the private local demo DB.

    Never enable this endpoint for the normal database or a public deployment.
    The demo server must bind to 127.0.0.1.
    """
    if os.getenv('AQUAVERSE_DEMO_AUTOLOGIN') != '1':
        raise HTTPException(status_code=403, detail='Chế độ xem demo tự động chưa được bật')
    if request.client is None or request.client.host not in ('127.0.0.1', '::1'):
        raise HTTPException(status_code=403, detail='Demo chỉ chạy trên máy này')
    if request.headers.get('origin') not in ('http://localhost:5173', 'http://127.0.0.1:5173'):
        raise HTTPException(status_code=403, detail='Nguồn yêu cầu demo không hợp lệ')
    expected = (Path.home() / 'Desktop' / 'AQUAVERSE_DEMO' / 'aquaverse_demo.sqlite3').resolve()
    url = db.get_bind().url
    if (expected.is_symlink() or expected.parent.is_symlink() or
            url.drivername != 'sqlite' or not url.database or Path(url.database).resolve() != expected):
        raise HTTPException(status_code=403, detail='Từ chối mở tự động trên cơ sở dữ liệu không phải DEMO')


# Public-demo mode is intentionally separate from the original local-only demo gate.
# Each browser receives its own owner-scoped account; NEVER share the local demo account.
_visitor_lock = Lock()
_visitor_attempts = defaultdict(deque)


def _open_public_visitor_session(request: Request, response: Response, db: Session) -> dict:
    origin = (os.getenv('AQUAVERSE_PUBLIC_ORIGIN') or os.getenv('RENDER_EXTERNAL_URL') or '').rstrip('/')
    if not origin or (not origin.startswith('https://') and origin not in ('http://testserver', 'http://localhost:8000')):
        raise HTTPException(status_code=503, detail='Public demo domain is not configured for HTTPS')
    # Do not trust unverified Origin or derive an allow-list from user-controlled Host.
    if not secrets.compare_digest(request.headers.get('origin', ''), origin):
        raise HTTPException(status_code=403, detail='Cross-origin demo session denied')
    if request.cookies.get(COOKIE_NAME):
        try:
            old = current_session(request, db)
            visitor = db.get(User, old.user_id)
            if visitor and visitor.email.endswith('@visitor.aquaverse.invalid'):
                return {'user': serialize_user(visitor), 'csrf_token': old.csrf_token}
        except HTTPException:
            pass
    # Basic abuse limit, per application instance; not a substitute for edge/WAF controls.
    ip = request.client.host if request.client else 'unknown'
    now = time.monotonic()
    with _visitor_lock:
        hits = _visitor_attempts[ip]
        while hits and now - hits[0] > 3600:
            hits.popleft()
        if len(hits) >= 6:
            raise HTTPException(status_code=429, detail='Too many demo sessions; try again later')
        hits.append(now)
        if len(_visitor_attempts) > 5000:
            for key in list(_visitor_attempts):
                if not _visitor_attempts[key] or now - _visitor_attempts[key][-1] > 3600:
                    _visitor_attempts.pop(key, None)
    visitor = User(email=f'{secrets.token_hex(20)}@visitor.aquaverse.invalid',
                   password_hash=hasher.hash(secrets.token_urlsafe(30)),
                   display_name='Khách tham quan', experience_level='beginner',
                   goal='explore_demo', preferred_species_id='monopterus_albus')
    db.add(visitor)
    db.commit()
    db.refresh(visitor)
    return _set_session(response, visitor, db)


@router.post('/demo-session')
def demo_session(request: Request, response: Response, db: Session = Depends(get_db)):
    """Issue an ordinary cookie+CSRF session, without a login form.

    Reuse the existing owner checks and NEVER grant anonymous access to APIs.
    """
    if os.getenv('AQUAVERSE_PUBLIC_DEMO') == '1':
        return _open_public_visitor_session(request, response, db)
    _require_isolated_local_demo(request, db)
    demo = db.scalar(select(User).where(User.email == 'demo@aquaverse.local'))
    if demo is None:
        raise HTTPException(status_code=503, detail='Chưa có tài khoản demo trong database. Hãy chạy script tạo dữ liệu demo.')
    return _set_session(response, demo, db)

@router.get('/me')
def me(request: Request, db: Session = Depends(get_db)):
    sess = current_session(request, db)
    user = db.get(User, sess.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail='User not found')
    return {'user': serialize_user(user), 'csrf_token': sess.csrf_token}


@router.post('/logout')
def logout(request: Request, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = current_session(request, db)
    db.delete(session)
    db.commit()
    response.delete_cookie(COOKIE_NAME, path='/api')
    return {'ok': True}


@router.post('/profile')
def update_profile(payload: ProfileData, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.display_name = payload.display_name.strip()
    user.experience_level = payload.experience_level
    user.goal = payload.goal.strip()
    user.preferred_species_id = payload.preferred_species_id
    db.commit()
    db.refresh(user)
    return serialize_user(user)
