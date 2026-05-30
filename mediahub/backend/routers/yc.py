from fastapi import APIRouter, Query
from utils import YOUTH_CENTERS_MOCK, distance_km

router = APIRouter()


@router.get("/api/youth-centers")
def get_youth_centers(lat: float = Query(...), lon: float = Query(...)):
    centers = []
    for center in YOUTH_CENTERS_MOCK:
        center_lat, center_lon = center["coordinates"]
        centers.append({
            **center,
            "lat": center_lat,
            "lon": center_lon,
            "distance_km": distance_km(lat, lon, center_lat, center_lon),
        })
    return sorted(centers, key=lambda c: c["distance_km"])
