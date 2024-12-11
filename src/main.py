from typing import Optional, List
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from uuid import uuid4
from pymongo import MongoClient
import math
from fastapi.middleware.cors import CORSMiddleware
from bson import ObjectId
from fastapi.responses import JSONResponse

app = FastAPI()

# Database connection
client = MongoClient('mongodb://root:example@localhost:27017/?authMechanism=DEFAULT')
db = client['placedb']
locations = db['locations']
reviews = db['reviews']


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Models
class Location(BaseModel):
    _id: str
    name: str
    lat: float
    lng: float
    category: str


class LocationCreateRequest(BaseModel):
    name: str
    lat: float
    lng: float
    category: str


class LocationViewRequest(BaseModel):
    lat: Optional[str] = None
    lng: Optional[str] = None
    radius_km: Optional[float] = None
    name: Optional[str] = None
    category: Optional[str] = None


class Review(BaseModel):
    _id: str
    location_id: str
    rating: float = Field(..., ge=0, le=5)
    content: str


class ReviewCreateRequest(BaseModel):
    location_id: str
    rating: float = Field(..., ge=0, le=5)
    content: str


class ReviewViewRequest(BaseModel):
    location_id: str


# ID Serializer
def serialize_mongo_document(document):
    if "_id" in document:
        document["_id"] = str(document["_id"])
    return document


# Endpoints
@app.post("/locations/")
def create_location(location: LocationCreateRequest):
    location_id = str(uuid4())
    location_data = {**location.dict(), "_id": location_id}
    locations.insert_one(location_data)
    return {"message": "Location created", "location": location_data}


@app.post("/locations/get/", response_model=List[Location])
def get_locations(request: LocationViewRequest):
    """
    Retrieve locations based on optional filters: lat, lng, radius_km, name, or category.
    """
    query = {}

    if request.lat and request.lng and request.radius_km:
        lat, lng, radius_km = float(request.lat), float(request.lng), request.radius_km

        lat_diff = radius_km / 111
        lng_diff = radius_km / (111 * abs(math.cos(math.radians(lat))))

        min_lat = lat - lat_diff
        max_lat = lat + lat_diff
        min_lng = lng - lng_diff
        max_lng = lng + lng_diff

        query.update({
            "lat": {"$gte": min_lat, "$lte": max_lat},
            "lng": {"$gte": min_lng, "$lte": max_lng},
        })

    if request.name:
        query["name"] = {"$regex": request.name, "$options": "i"}
    if request.category:
        query["category"] = {"$regex": request.category, "$options": "i"}

    location_results = list(locations.find(query, {"_id": 1, "name": 1, "lat": 1, "lng": 1, "category": 1}))

    if not location_results:
        raise HTTPException(status_code=404, detail="No locations found matching the criteria")

    return JSONResponse(content=location_results)


@app.post("/reviews/")
def create_review(review: ReviewCreateRequest):
    review_id = str(uuid4())
    review_data = {**review.dict(), "_id": review_id}
    inserted_review = reviews.insert_one(review_data)
    review_data["_id"] = str(inserted_review.inserted_id)
    return {"message": "Review added", "review": review_data}


@app.get("/reviews/{location_id}", response_model=List[Review])
def get_reviews(location_id: str):
    location_reviews = list(reviews.find({"location_id": location_id}))
    if not location_reviews:
        raise HTTPException(status_code=404, detail="No reviews found for this location")
    serialized_reviews = [serialize_mongo_document(review) for review in location_reviews]
    return serialized_reviews


if __name__ == "__main__":
    uvicorn.run(app)
