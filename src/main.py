from typing import Union, List
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from uuid import uuid4
from pymongo import MongoClient

app = FastAPI()

client = MongoClient('mongodb://root:example@localhost:27017/?authMechanism=DEFAULT')
db = client['placedb']
users = db['users']
locations = db['locations']
reviews = db['reviews']


# Models
class User(BaseModel):
    id: str
    name: str


class UserCreateRequest(BaseModel):
    name: str


class UserRequest(BaseModel):
    value: str


class Location(BaseModel):
    id: str
    name: str
    lat: float
    lng: float
    category: str


class LocationCreateRequest(BaseModel):
    name: str
    lat: float
    lng: float
    category: str


class LocationRequest(BaseModel):
    id: str


class Review(BaseModel):
    review_id: str
    user_id: str
    location_id: str
    rating: float
    content: str


class ReviewCreateRequest(BaseModel):
    user_id: str
    location_id: str
    rating: float
    content: str


class ReviewRequest(BaseModel):
    id: str


# User Endpoints
@app.post('/users')
def create_user(body: UserCreateRequest):
    user_id = str(uuid4())
    user = {'_id': user_id, 'name': body.name}
    users.insert_one(user)
    return JSONResponse(content={'id': user_id, 'message': 'User created successfully'})


@app.post('/users/{parameter}')
def get_user(parameter: str, body: UserRequest):
    """
    Search for a user by a dynamic parameter.
    Accepts a JSON body with a "value" key specifying the search value.
    """
    value = body.value
    if not value:
        raise HTTPException(status_code=400, detail="Request body must include a 'value' key.")

    # Adjust the key for '_id' if searching by 'id'
    key = "_id" if parameter == "id" else parameter

    # Build the query
    query = {key: value}
    if key == "_id":  # Special handling for MongoDB's ObjectId
        query["_id"] = value

    # Perform the query
    user = users.find_one(query)
    if not user:
        raise HTTPException(status_code=404, detail=f"User with {parameter} '{value}' not found")

    # Serialize '_id' to string for JSON response
    if "_id" in user:
        user["_id"] = str(user["_id"])
    return user


@app.get('/users')
def get_all_users():
    return [{"_id": str(user["_id"]), **user} for user in users.find({})]


@app.delete('/users/delete')
def delete_user(body: UserRequest):
    result = users.delete_one({'_id': body.value})
    if result.deleted_count == 1:
        return JSONResponse(content={'message': 'Successfully deleted'})
    raise HTTPException(status_code=404, detail="User not found")


# Location Endpoints
@app.post('/locations')
def create_location(body: LocationCreateRequest):
    existing_location = locations.find_one({'lat': body.lat, 'lng': body.lng})
    if existing_location:
        return JSONResponse(content={'message': 'Location already exists', 'location': existing_location})
    location_id = str(uuid4())
    location = {
        '_id': location_id,
        'name': body.name,
        'lat': body.lat,
        'lng': body.lng,
        'category': body.category
    }
    locations.insert_one(location)
    return JSONResponse(content={'id': location_id, 'message': 'Location created successfully'})


@app.post('/locations/get')
def get_location(body: LocationRequest):
    location = locations.find_one({'_id': body.id})
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")
    location['_id'] = str(location['_id'])
    return location


@app.get('/locations')
def get_all_locations():
    return [{"_id": str(location["_id"]), **location} for location in locations.find({})]


@app.post('/locations/delete')
def delete_location(body: LocationRequest):
    result = locations.delete_one({'_id': body.id})
    if result.deleted_count == 1:
        return JSONResponse(content={'message': 'Successfully deleted'})
    raise HTTPException(status_code=404, detail="Location not found")


# Review Endpoints
@app.post('/reviews')
def create_review(body: ReviewCreateRequest):
    review_id = str(uuid4())
    review = {
        '_id': review_id,
        'location_id': body.location_id,
        'user_id': body.user_id,
        'rating': body.rating,
        'content': body.content
    }
    reviews.insert_one(review)
    return JSONResponse(content={'id': review_id, 'message': 'Review added successfully'})


@app.post('/reviews/get')
def get_review(body: ReviewRequest):
    review = reviews.find_one({'_id': body.id})
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    review['_id'] = str(review['_id'])
    return review


@app.get('/reviews')
def get_all_reviews():
    return [{"_id": str(review["_id"]), **review} for review in reviews.find({})]


@app.post('/reviews/delete')
def delete_review(body: ReviewRequest):
    result = reviews.delete_one({'_id': body.id})
    if result.deleted_count == 1:
        return JSONResponse(content={'message': 'Successfully deleted'})
    raise HTTPException(status_code=404, detail="Review not found")


if __name__ == '__main__':
    uvicorn.run(app)
