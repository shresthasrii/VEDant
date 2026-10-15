from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import Dict, Any, List
from backend.services.timetable import get_all_classes, validate_timetable, parse_and_import_csv
from backend.schemas import ClassItem

router = APIRouter(prefix="/timetable", tags=["timetable"])

@router.get("")
def get_timetable() -> Dict[str, Any]:
    classes = get_all_classes()
    conflicts = validate_timetable()
    return {
        "classes": classes,
        "total_classes": len(classes),
        "conflicts": conflicts,
        "provenance": "SIMULATED"
    }

@router.post("")
async def upload_timetable_csv(file: UploadFile = File(...)) -> Dict[str, Any]:
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted.")
        
    contents = await file.read()
    text = contents.decode("utf-8")
    result = parse_and_import_csv(text)
    return result
