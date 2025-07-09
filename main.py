import os
from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import Column, Integer, String, Boolean, create_engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from passlib.context import CryptContext
from typing import Optional, List
import requests
from datetime import datetime, timedelta
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Static directory handling compatible with Render
try:
    os.makedirs("static", exist_ok=True)
    open("static/.keep", "w").close()  # Create empty file to preserve directory
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception as e:
    print(f"Static directory warning: {str(e)}")

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./test.db")
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
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    class Config:
        orm_mode = True

class UserLogin(BaseModel):
    username: str
    password: str

class CompanyCreate(BaseModel):
    name: str
    email: EmailStr
    number: int
    address: str

class CompanyOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    number: int
    address: str
    class Config:
        orm_mode = True

class PackageCreate(BaseModel):
    package_name: str

class PackageOut(BaseModel):
    id: int
    package_name: str
    class Config:
        orm_mode = True

class Fuel(BaseModel):
    current_time: datetime

class RouteRequest(BaseModel):
    start_location: str
    end_location: str

class RouteOut(BaseModel):
    start_location: str
    end_location: str
    waypoints: Optional[List[str]] = None
    distance: Optional[float] = None
    estimated_time: Optional[float] = None
    traffic_conditions: Optional[str] = None
    route_type: Optional[str] = None

class Weather(BaseModel):
    hurricane: bool = False
    tornado: bool = False
    snow: bool = False
    flood: bool = False
    wildfire: bool = False
    earthquake: bool = False

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/api/geoapify/create_user", response_model=UserOut)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(UserDB).filter((UserDB.username == user.username) | (UserDB.email == user.email)).first():
        raise HTTPException(status_code=400, detail="Username or email already registered")
    hashed_pw = pwd_context.hash(user.password)
    db_user = UserDB(username=user.username, email=user.email, password=hashed_pw)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.post("/api/geoapify/login")
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(UserDB).filter(UserDB.username == user.username).first()
    if not db_user or not pwd_context.verify(user.password, db_user.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {"message": "Login successful", "user_id": db_user.id}

@app.post("/api/geoapify/create_company", response_model=CompanyOut)
def create_company(company: CompanyCreate, db: Session = Depends(get_db)):
    if db.query(CompanyDB).filter((CompanyDB.name == company.name) | (CompanyDB.email == company.email)).first():
        raise HTTPException(status_code=400, detail="Company name or email already registered")
    db_company = CompanyDB(name=company.name, email=company.email, number=company.number, address=company.address)
    db.add(db_company)
    db.commit()
    db.refresh(db_company)
    return db_company

@app.post("/api/geoapify/add_package", response_model=PackageOut)
def add_package(package: PackageCreate, db: Session = Depends(get_db)):
    new_package = PackageDB(package_name=package.package_name)
    db.add(new_package)
    db.commit()
    db.refresh(new_package)
    return new_package

@app.get("/api/geoapify/list_packages", response_model=List[PackageOut])
def list_packages(db: Session = Depends(get_db)):
    packages = db.query(PackageDB).all()
    return packages

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

GEOAPIFY_API_KEY = os.environ.get("GEOAPIFY_API_KEY", "your_api_key_here")
MAPMATCHING_URL = "https://api.geoapify.com/v1/mapmatching"

@app.post("/api/geoapify/get_route", response_model=RouteOut)
def get_route(route: RouteRequest):
    if not GEOAPIFY_API_KEY or GEOAPIFY_API_KEY == "your_api_key_here":
        raise HTTPException(status_code=500, detail="Geoapify API key not configured")
    
    params = {
        "apiKey": GEOAPIFY_API_KEY,
        "waypoints": f"{route.start_location}|{route.end_location}",
        "mode": "drive"
    }
    
    try:
        response = requests.get(MAPMATCHING_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=503, detail=f"Error connecting to Geoapify: {str(e)}")
    
    features = data.get("features", [])
    if not features:
        raise HTTPException(status_code=404, detail="No route found")
    
    route_info = features[0].get("properties", {})
    return RouteOut(
        start_location=route.start_location,
        end_location=route.end_location,
        distance=route_info.get("distance"),
        estimated_time=route_info.get("duration"),
        traffic_conditions=route_info.get("traffic"),
        route_type="fastest"
    )

def fetch_weather_alerts() -> Weather:
    weather = Weather()
    try:
        response = requests.get("https://api.weather.gov/alerts/active/NJ", timeout=5)
        response.raise_for_status()
        data = response.json()
        
        for alert in data.get("features", []):
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
        raise HTTPException(status_code=503, detail=f"Weather API error: {str(e)}")
    return weather

@app.get("/api/geoapify/fetch_weather_alerts", response_model=Weather)
def list_weather():
    return fetch_weather_alerts()

