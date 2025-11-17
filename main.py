import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import IPad

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def serialize_doc(doc: dict) -> dict:
    """Convert Mongo document to JSON-serializable dict"""
    if not doc:
        return doc
    d = dict(doc)
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    # Convert any nested ObjectIds if present
    for k, v in list(d.items()):
        if isinstance(v, ObjectId):
            d[k] = str(v)
    return d


@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


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


# ---------------------------
# iPad Catalog API
# ---------------------------

@app.get("/api/ipads")
def list_ipads(
    q: Optional[str] = None,
    chip: Optional[str] = None,
    min_display: Optional[float] = Query(None, ge=0),
    max_display: Optional[float] = Query(None, ge=0),
):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    filter_dict = {}

    if q:
        # Simple regex search on name
        filter_dict["name"] = {"$regex": q, "$options": "i"}
    if chip:
        filter_dict["chip"] = chip
    if min_display is not None or max_display is not None:
        rng = {}
        if min_display is not None:
            rng["$gte"] = float(min_display)
        if max_display is not None:
            rng["$lte"] = float(max_display)
        filter_dict["display_size"] = rng

    docs = get_documents("ipad", filter_dict)
    return [serialize_doc(d) for d in docs]


@app.post("/api/ipads", status_code=201)
def create_ipad(model: IPad):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    inserted_id = create_document("ipad", model)
    return {"id": inserted_id}


class CompareRequest(BaseModel):
    a: str
    b: str


@app.post("/api/ipads/compare")
def compare_ipads(payload: CompareRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    try:
        a_doc = db["ipad"].find_one({"_id": ObjectId(payload.a)})
        b_doc = db["ipad"].find_one({"_id": ObjectId(payload.b)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id format")

    if not a_doc or not b_doc:
        raise HTTPException(status_code=404, detail="One or both models not found")

    a = serialize_doc(a_doc)
    b = serialize_doc(b_doc)

    # Simple heuristic for recommendation
    def score(x: dict) -> float:
        base = 0
        chip_score = {
            "M4": 5,
            "M3": 4.5,
            "M2": 4,
            "M1": 3.5,
            "A15": 3,
            "A14": 2.5,
        }
        base += chip_score.get(x.get("chip", "").upper(), 2)
        base += float(x.get("display_size", 0)) * 0.2
        base += (1 if x.get("cellular") else 0) * 0.3
        base += len(x.get("storage_options", [])) * 0.1
        return base

    a_score = score(a)
    b_score = score(b)

    recommendation = "A" if a_score >= b_score else "B"

    return {
        "a": a,
        "b": b,
        "scores": {"a": a_score, "b": b_score},
        "recommended": recommendation,
    }


@app.post("/api/ipads/seed")
def seed_ipads():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    count = db["ipad"].count_documents({})
    if count > 0:
        return {"inserted": 0, "message": "Catalog already has data"}

    demo: List[IPad] = [
        IPad(
            name="iPad Pro 11",
            generation="M4 (2024)",
            chip="M4",
            display_size=11.0,
            storage_options=[256, 512, 1024],
            base_price=999.0,
            colors=["Silver", "Space Black"],
            supports_pencil="Apple Pencil Pro",
            cellular=True,
            image_url="https://store.storeimages.cdn-apple.com/4982/as-images.apple.com/is/ipad-pro-11-digitalmat-gallery-1-202404?wid=728&hei=666&fmt=png-alpha&.v=1712605559398",
        ),
        IPad(
            name="iPad Air 13",
            generation="M2 (2024)",
            chip="M2",
            display_size=13.0,
            storage_options=[128, 256, 512],
            base_price=799.0,
            colors=["Blue", "Purple", "Starlight", "Space Gray"],
            supports_pencil="Apple Pencil Pro",
            cellular=True,
            image_url="https://store.storeimages.cdn-apple.com/4982/as-images.apple.com/is/ipad-air-13-digitalmat-gallery-1-202405?wid=728&hei=666&fmt=png-alpha&.v=1713836176004",
        ),
        IPad(
            name="iPad (10th gen)",
            generation="A14 (2022)",
            chip="A14",
            display_size=10.9,
            storage_options=[64, 256],
            base_price=349.0,
            colors=["Blue", "Pink", "Yellow", "Silver"],
            supports_pencil="USB‑C Apple Pencil",
            cellular=True,
            image_url="https://store.storeimages.cdn-apple.com/4982/as-images.apple.com/is/ipad-10th-gen-hero-blue-wifi-select?wid=540&hei=540&fmt=jpeg&qlt=90&.v=1664481087749",
        ),
        IPad(
            name="iPad mini",
            generation="A15 (2021)",
            chip="A15",
            display_size=8.3,
            storage_options=[64, 256],
            base_price=499.0,
            colors=["Space Gray", "Pink", "Purple", "Starlight"],
            supports_pencil="Apple Pencil (2nd gen)",
            cellular=True,
            image_url="https://store.storeimages.cdn-apple.com/4982/as-images.apple.com/is/ipad-mini-select-202109_GEO_US?wid=540&hei=540&fmt=jpeg&qlt=90&.v=1631751068000",
        ),
    ]

    inserted = 0
    for item in demo:
        create_document("ipad", item)
        inserted += 1

    return {"inserted": inserted}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
