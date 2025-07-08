from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, Field, validator
from sqlalchemy import Column, Integer, String, Boolean, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from passlib.context import CryptContext
from typing import Optional, List
import requests
from datetime import datetime, timedelta
import uuid

DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    password = Column(String)
    is_active = Column(Boolean, default=True)

class CompanyDB(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    number = Column(Integer)
    address = Column(String)

class PackageDB(Base):
    __tablename__ = "packages"
    id = Column(Integer, primary_key=True, index=True)
    package_name = Column(String, index=True)

Base.metadata.create_all(bind=engine)

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class CompanyCreate(BaseModel):
    name: str
    email: str
    number: int
    address: str

class Package(BaseModel):
    package_id: int
    package_name: str

class Fuel(BaseModel):
    current_time: datetime

class Route(BaseModel):
    start_location: str
    end_location: str
    waypoints: Optional[List[str]] = None
    distance: Optional[float] = None
    estimated_time: Optional[float] = None
    traffic_conditions: Optional[str] = None
    route_type: Optional[str] = None

app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/api/geoapify/create_user")
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    hashed_pw = pwd_context.hash(user.password)
    db_user = UserDB(username=user.username, email=user.email, password=hashed_pw)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return {"id": db_user.id, "username": db_user.username, "email": db_user.email}

@app.post("/api/geoapify/create_company")
def create_company(company: CompanyCreate, db: Session = Depends(get_db)):
    db_company = CompanyDB(name=company.name, email=company.email, number=company.number, address=company.address)
    db.add(db_company)
    db.commit()
    db.refresh(db_company)
    return {"id": db_company.id, "name": db_company.name, "email": db_company.email, "number": db_company.number, "address": db_company.address}

@app.post("/api/geoapify/add_package")
def add_package(package: Package, db: Session = Depends(get_db)):
    new_package = PackageDB(id=package.package_id, package_name=package.package_name)
    db.add(new_package)
    db.commit()
    db.refresh(new_package)
    return {"id": new_package.id, "package_name": new_package.package_name}

@app.get("/api/geoapify/list_packages")
def list_packages(db: Session = Depends(get_db)):
    packages = db.query(PackageDB).all()
    return [{"id": p.id, "package_name": p.package_name} for p in packages]

@app.delete("/api/geoapify/remove_package/{package_id}")
def remove_package(package_id: int, db: Session = Depends(get_db)):
    deleted = db.query(PackageDB).filter(PackageDB.id == package_id).delete()
    db.commit()
    if deleted:
        return {"detail": "Package deleted"}
    else:
        raise HTTPException(status_code=404, detail="Package not found")

@app.post("/api/geoapify/fuel")
def fuel(estimate: Fuel):
    next_refuel_time = estimate.current_time + timedelta(hours=30)
    return {
        "current_time": estimate.current_time,
        "next_refuel_time": next_refuel_time,
        "hours_until_refuel": 30
    }

GEOAPIFY_API_KEY = "API_KEY"
MAPMATCHING_URL = "https://api.geoapify.com/v1/mapmatching"

@app.post("/api/geoapify/get_route")
def get_route(start_location: str, end_location: str):
    params = {
        "apiKey": GEOAPIFY_API_KEY,
        "waypoints": f"{start_location}|{end_location}",
        "mode": "drive"
    }
    response = requests.get(MAPMATCHING_URL, params=params)
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Error fetching route data")
    data = response.json()
    features = data.get("features", [])
    if not features:
        raise HTTPException(status_code=404, detail="No route found")
    route_info = features[0].get("properties", {})
    route = Route(
        start_location=start_location,
        end_location=end_location,
        distance=route_info.get("distance"),
        estimated_time=route_info.get("duration"),
        traffic_conditions=route_info.get("traffic"),
        route_type="fastest"
    )
    return route

class Weather(BaseModel):
    hurricane: bool = False
    tornado: bool = False
    snow: bool = False
    flood: bool = False
    wildfire: bool = False
    earthquake: bool = False

def fetch_weather_alerts() -> Weather:
    weather = Weather()
    try:
        response = requests.get("https://api.weather.gov/alerts/active/NJ").json()
        for alert in response.get("features", []):
            event = alert["properties"]["event"].lower()
            if "hurricane" in event:
                weather.hurricane = True
            elif "tornado" in event:
                weather.tornado = True
            elif "flood" in event:
                weather.flood = True
            elif "snow" in event or "winter" in event:
                weather.snow = True
            elif "fire" in event or "wildfire" in event:
                weather.wildfire = True
    except Exception as e:
        print("Weather API error:", e)
    return weather

@app.post("/api/geoapify/fetch_weather_alerts")
def list_weather() -> Weather:
    return fetch_weather_alerts()
