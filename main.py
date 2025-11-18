import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Product, Order, OrderItem

app = FastAPI(title="Egg Store API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Helpers ----------

def to_str_id(doc: dict):
    d = doc.copy()
    if d.get("_id"):
        d["id"] = str(d.pop("_id"))
    return d


def seed_products():
    if db is None:
        return
    count = db["product"].count_documents({})
    if count > 0:
        return

    sample_products: List[Product] = [
        Product(
            title="Free-Range Eggs (12 pcs)",
            description="Fresh farm free-range chicken eggs. Rich yolks and great taste.",
            price=4.99,
            category="chicken",
            in_stock=True,
            image="https://images.unsplash.com/photo-1517959105821-eaf2591984dd?q=80&w=1200&auto=format&fit=crop"
        ),
        Product(
            title="Organic Eggs (12 pcs)",
            description="Certified organic eggs from pasture-raised hens.",
            price=5.99,
            category="organic",
            in_stock=True,
            image="https://images.unsplash.com/photo-1518806118471-f28b20a1d79d?q=80&w=1200&auto=format&fit=crop"
        ),
        Product(
            title="Omega-3 Enriched Eggs (12 pcs)",
            description="Omega-3 enriched for a healthier choice.",
            price=6.49,
            category="enriched",
            in_stock=True,
            image="https://images.unsplash.com/photo-1522335789203-aabd1fc54bc9?q=80&w=1200&auto=format&fit=crop"
        ),
        Product(
            title="Quail Eggs (24 pcs)",
            description="Delicate and delicious quail eggs.",
            price=7.49,
            category="quail",
            in_stock=True,
            image="https://images.unsplash.com/photo-1577208288347-0d412b7a4f35?q=80&w=1200&auto=format&fit=crop"
        ),
        Product(
            title="Duck Eggs (6 pcs)",
            description="Large and rich duck eggs for special recipes.",
            price=4.49,
            category="duck",
            in_stock=True,
            image="https://images.unsplash.com/photo-1517957741781-7f3fd1563bb3?q=80&w=1200&auto=format&fit=crop"
        ),
    ]

    for p in sample_products:
        db["product"].insert_one(p.model_dump())


# Seed data on startup if DB available
seed_products()


# ---------- Models for requests ----------

class OrderItemInput(BaseModel):
    product_id: str
    quantity: int = Field(ge=1)

class CreateOrderInput(BaseModel):
    items: List[OrderItemInput]
    customer_name: str
    email: str
    address: str
    payment_method: str = Field("card")  # "card" or "cod"


# ---------- Routes ----------

@app.get("/")
def read_root():
    return {"message": "Egg Store Backend is running"}


@app.get("/api/products")
def list_products():
    if db is None:
        # Fallback static list if DB not configured
        return [
            {
                "id": "0",
                "title": "Free-Range Eggs (12 pcs)",
                "description": "Fresh farm free-range chicken eggs. Rich yolks and great taste.",
                "price": 4.99,
                "category": "chicken",
                "in_stock": True,
                "image": "https://images.unsplash.com/photo-1517959105821-eaf2591984dd?q=80&w=1200&auto=format&fit=crop",
            }
        ]
    products = list(db["product"].find({}))
    return [to_str_id(p) for p in products]


@app.post("/api/orders")
def create_order(payload: CreateOrderInput):
    if not payload.items:
        raise HTTPException(status_code=400, detail="No items in order")

    # Build full items with price/title from DB
    items: List[OrderItem] = []
    total = 0.0

    for it in payload.items:
        # Validate product
        if db is None:
            # Fallback values
            price = 4.99
            title = "Free-Range Eggs (12 pcs)"
        else:
            try:
                prod = db["product"].find_one({"_id": ObjectId(it.product_id)})
            except Exception:
                prod = None
            if not prod:
                raise HTTPException(status_code=404, detail=f"Product not found: {it.product_id}")
            price = float(prod.get("price", 0))
            title = prod.get("title", "Eggs")
        subtotal = price * it.quantity
        total += subtotal
        items.append(OrderItem(product_id=it.product_id, title=title, price=price, quantity=it.quantity, subtotal=subtotal))

    # Simulate payment processing
    status = "paid" if payload.payment_method == "card" else "pending"

    order_model = Order(
        items=items,
        customer_name=payload.customer_name,
        email=payload.email,
        address=payload.address,
        payment_method=payload.payment_method if payload.payment_method in ["card", "cod"] else "card",
        total_amount=round(total, 2),
        status=status,
    )

    try:
        order_id = create_document("order", order_model)
    except Exception:
        # If DB not available, still return a fake id
        order_id = "demo-order-id"

    return {"order_id": order_id, "status": status, "total": round(total, 2)}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    # Check environment variables
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
