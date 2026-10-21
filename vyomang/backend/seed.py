"""Sample data, added only when the database is empty."""
import random
from datetime import date, datetime, time

from auth import hash_password
from models import PurchaseOrder, Sale, SaleOriginal, Sku, User

# id, name, base weekly sales, weekly trend, festival sensitivity, delivery days, on hand, price
SEED_SKUS = [
    ("SKU-1042", "Basmati rice 5kg", 680, 7, 1.0, 7, 240, 14),
    ("SKU-2210", "Cold-press oil 1L", 450, 4, 0.8, 9, 410, 11),
    ("SKU-3307", "Gift tin assortment", 240, 6, 2.2, 12, 95, 32),
    ("SKU-0871", "Ghee 500ml", 300, 3, 1.3, 6, 230, 18),
    ("SKU-4403", "Dry fruit mix 500g", 200, 3, 1.6, 8, 480, 21),
    ("SKU-5519", "Chai blend 250g", 330, 2, 0.7, 5, 1900, 7),
    ("SKU-7788", "Sugar 1kg", 900, 3, 0.5, 4, 3600, 2),
    ("SKU-6120", "Almond pack 1kg", 140, 0, 1.1, 10, 3100, 26),
]


def seed_if_empty(db):
    if db.query(Sku).count() > 0:
        return
    rnd = random.Random(11)
    for sid, name, base, trend, fs, lead, on_hand, price in SEED_SKUS:
        db.add(Sku(id=sid, name=name, festival_sens=fs, lead_time=lead, on_hand=on_hand, price=price))
        for i in range(26):
            units = round((base - trend * (25 - i)) * (1 + (rnd.random() - 0.5) * 0.12))
            db.add(Sale(sku_id=sid, week_no=i, units=units))
            db.add(SaleOriginal(sku_id=sid, week_no=i, units=units))
    demo = db.query(User).filter(User.email == "demo@vyomang.com").first()
    if not demo:
        salt, pw_hash = hash_password("demo1234")
        demo = User(email="demo@vyomang.com", full_name="Demo Manager", salt=salt, pw_hash=pw_hash)
        db.add(demo)
        db.flush()
    today = date.today()
    for po_id, sku, qty, hh, mm in [(8809, "SKU-3307", 2400, 6, 10), (8812, "SKU-1042", 1800, 6, 42)]:
        db.add(PurchaseOrder(id=po_id, sku_id=sku, qty=qty, user_id=demo.id,
                             created=datetime.combine(today, time(hh, mm)).isoformat()))
    db.commit()
