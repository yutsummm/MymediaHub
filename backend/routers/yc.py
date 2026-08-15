from fastapi import APIRouter, Depends, Query

from utils import YOUTH_CENTERS_MOCK, distance_km, get_current_user_id

router = APIRouter()


@router.get("/api/youth-centers")
def get_youth_centers(
    lat: float = Query(...),
    lon: float = Query(...),
    user_id: int = Depends(get_current_user_id),
):
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
