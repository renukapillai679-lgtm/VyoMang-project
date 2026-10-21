"""
VyoMang backend: FastAPI + SQLite (SQLAlchemy)

Run (from the backend folder):   python -m uvicorn main:app --reload --port 8000
API explorer:                    http://localhost:8000/docs
"""
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from auth import (create_access_token, decode_access_token, hash_password,
                  verify_google_credential, verify_password)
from database import get_db, init_db
from forecast import forecast, recommend
from models import PurchaseOrder, Sale, SaleOriginal, Sku, User

app = FastAPI(title="VyoMang API")

# The page runs on port 5500 and calls this server on port 8000, so the browser needs permission (CORS).
ALLOWED_ORIGINS = [
    "http://localhost:5500", "http://127.0.0.1:5500",
    "http://localhost:8000", "http://127.0.0.1:8000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND = Path(__file__).resolve().parent.parent / "frontend" / "index.html"


# ----------------------------------------------------------------------------
# Login
# ----------------------------------------------------------------------------
def user_dict(u: User) -> dict:
    return {"id": u.id, "email": u.email, "full_name": u.full_name, "picture_url": u.picture_url}


def auth_response(u: User, **extra) -> dict:
    return {"token": create_access_token(u.id, u.email), "token_type": "bearer", "user": user_dict(u), **extra}


def current_user(authorization: str = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Please log in.")
    try:
        payload = decode_access_token(authorization[7:])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expired. Please log in again.")
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid login. Please log in again.")
    user = db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(401, "Account not found. Please log in again.")
    return user


class Credentials(BaseModel):
    email: str
    password: str


def check_credentials(c: Credentials):
    if "@" not in c.email or "." not in c.email.split("@")[-1]:
        raise HTTPException(400, "Enter a valid email address.")
    if len(c.password) < 4:
        raise HTTPException(400, "Password must be at least 4 characters.")


@app.post("/api/register")
def register(c: Credentials, db: Session = Depends(get_db)):
    check_credentials(c)
    email = c.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists.")
    salt, pw_hash = hash_password(c.password)
    user = User(email=email, full_name=email.split("@")[0], salt=salt, pw_hash=pw_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    return auth_response(user)


@app.post("/api/login")
def login(c: Credentials, db: Session = Depends(get_db)):
    check_credentials(c)
    user = db.scalar(select(User).where(User.email == c.email.strip().lower()))
    if not user or not verify_password(c.password, user.salt, user.pw_hash):
        raise HTTPException(401, "Wrong email or password.")
    return auth_response(user)


class GoogleLogin(BaseModel):
    credential: Optional[str] = None     # the Google ID token (what the page sends)
    token: Optional[str] = None          # older name for the same thing, still accepted


@app.post("/auth/google")
def google_login(body: GoogleLogin, db: Session = Depends(get_db)):
    """Receive the Google ID token, verify it with Google's public keys, then find or create the user."""
    credential = body.credential or body.token
    if not credential:
        raise HTTPException(400, "Missing Google credential.")
    info = verify_google_credential(credential)
    google_id = info["sub"]
    email = info["email"].strip().lower()

    user = db.scalar(select(User).where(User.google_id == google_id))
    if not user:                                           # same email already registered? link it
        user = db.scalar(select(User).where(User.email == email))
    is_new = user is None
    if is_new:
        user = User(email=email, google_id=google_id)
    user.google_id = google_id
    user.full_name = info.get("name") or user.full_name or email.split("@")[0]
    user.picture_url = info.get("picture") or user.picture_url
    db.add(user)
    db.commit()
    db.refresh(user)
    return auth_response(user, is_new_user=is_new)


app.add_api_route("/api/auth/google", google_login, methods=["POST"], include_in_schema=False)


@app.post("/api/logout")
def logout():
    return {"ok": True}          # tokens are stateless: the page simply forgets its token


@app.get("/api/me")
def me(user: User = Depends(current_user)):
    return user_dict(user)


@app.get("/api/health")
def health():
    return {"ok": True}


# ----------------------------------------------------------------------------
# SKUs, sales, forecast
# ----------------------------------------------------------------------------
def history_of(db: Session, sku_id: str):
    return list(db.scalars(select(Sale.units).where(Sale.sku_id == sku_id).order_by(Sale.week_no)))


def get_sku(db: Session, sku_id: str) -> Sku:
    sku = db.get(Sku, sku_id)
    if not sku:
        raise HTTPException(404, "Unknown SKU.")
    return sku


def sku_dict(s: Sku) -> dict:
    return {"id": s.id, "festival_sens": s.festival_sens, "lead_time": s.lead_time, "on_hand": s.on_hand}


@app.get("/api/skus")
def list_skus(db: Session = Depends(get_db), user: User = Depends(current_user)):
    today = date.today()
    skus, recs = [], []
    for s in db.scalars(select(Sku).order_by(text("skus.rowid"))):
        hist = history_of(db, s.id)
        skus.append({"id": s.id, "name": s.name, "festival_sens": s.festival_sens, "lead_time": s.lead_time,
                     "on_hand": s.on_hand, "price": s.price, "history": hist})
        recs.append(recommend(sku_dict(s), hist, today))
    return {"skus": skus, "recommendations": recs}


class StockUpdate(BaseModel):
    on_hand: Optional[int] = Field(default=None, ge=0)
    lead_time: Optional[int] = Field(default=None, ge=1, le=90)


@app.patch("/api/skus/{sku_id}")
def update_sku(sku_id: str, body: StockUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    sku = get_sku(db, sku_id)
    if body.on_hand is not None:
        sku.on_hand = body.on_hand
    if body.lead_time is not None:
        sku.lead_time = body.lead_time
    db.commit()
    return {"ok": True}


@app.get("/api/forecast/{sku_id}")
def forecast_for(sku_id: str, weeks: int = 8, db: Session = Depends(get_db), user: User = Depends(current_user)):
    sku = get_sku(db, sku_id)
    today = date.today()
    weeks = max(1, min(weeks, 12))
    rows = forecast(history_of(db, sku_id), sku.festival_sens, weeks, today)
    return {"sku": sku_id, "weeks": [
        {"week_start": (today + timedelta(days=7 * j)).isoformat(), "forecast": round(f["v"]),
         "low": round(f["lo"]), "high": round(f["hi"]), "festival": f["fn"], "uplift": round(f["up"], 3)}
        for j, f in enumerate(rows)]}


class SalesUpload(BaseModel):
    units: List[float]


@app.put("/api/skus/{sku_id}/sales")
def upload_sales(sku_id: str, body: SalesUpload, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_sku(db, sku_id)
    units = body.units
    if len(units) < 12 or len(units) > 520 or any(u < 0 for u in units):
        raise HTTPException(400, "Send 12 or more weekly values, all zero or above.")
    units = [round(u) for u in units[-26:]]               # keep the most recent 26 weeks
    db.execute(delete(Sale).where(Sale.sku_id == sku_id))
    db.add_all([Sale(sku_id=sku_id, week_no=i, units=u) for i, u in enumerate(units)])
    db.commit()
    return {"ok": True, "weeks_saved": len(units)}


@app.post("/api/skus/{sku_id}/sales/reset")
def reset_sales(sku_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_sku(db, sku_id)
    originals = db.scalars(select(SaleOriginal).where(SaleOriginal.sku_id == sku_id)).all()
    db.execute(delete(Sale).where(Sale.sku_id == sku_id))
    db.add_all([Sale(sku_id=o.sku_id, week_no=o.week_no, units=o.units) for o in originals])
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------------------------
# Purchase orders
# ----------------------------------------------------------------------------
class PurchaseOrderIn(BaseModel):
    sku_id: str
    qty: int = Field(gt=0, le=1_000_000)


def po_view(po: PurchaseOrder, name: str) -> dict:
    return {"id": po.id, "time": po.created[11:16], "text": f"PO-{po.id} raised: {name} × {po.qty:,}"}


@app.get("/api/pos")
def list_pos(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.execute(select(PurchaseOrder, Sku.name).join(Sku, Sku.id == PurchaseOrder.sku_id)
                      .order_by(PurchaseOrder.id.desc()).limit(50)).all()
    nxt = (db.scalar(select(func.max(PurchaseOrder.id))) or 8000) + 1
    return {"pos": [po_view(po, name) for po, name in rows], "next_no": nxt}


@app.post("/api/pos")
def create_po(body: PurchaseOrderIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    sku = get_sku(db, body.sku_id)
    po = PurchaseOrder(sku_id=sku.id, qty=body.qty, user_id=user.id,
                       created=datetime.now().isoformat(timespec="seconds"))
    db.add(po)
    db.commit()
    db.refresh(po)
    return po_view(po, sku.name)


# ----------------------------------------------------------------------------
# Optional: also serve the page from this server (http://localhost:8000)
# ----------------------------------------------------------------------------
@app.get("/")
def home():
    return FileResponse(FRONTEND)


init_db()
