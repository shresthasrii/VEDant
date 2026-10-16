"""
VERDANT Semantic Building Ontology Engine (Brick Schema v1.3 & RealEstateCore)
Standard References:
- Brick Schema v1.3 (Unified semantic metadata standard for smart buildings)
- RealEstateCore v4 (REC consortium for smart real estate digital twins)
- W3C RDF / JSON-LD / Turtle Serialization

Enables interoperability with enterprise BMS (Johnson Controls OpenBlue, Siemens Desigo, Autodesk Tandem),
mapping campus spaces, equipment, meters, and sensors into a semantic graph.
"""
from typing import Dict, Any, List
from backend.db import get_db

BRICK_CONTEXT = {
    "@vocab": "https://brickschema.org/schema/Brick#",
    "brick": "https://brickschema.org/schema/Brick#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "rec": "https://w3id.org/rec#",
    "verdant": "https://verdant.ai/schema/campus#"
}


def build_brick_schema_graph() -> Dict[str, Any]:
    """
    Builds a JSON-LD semantic graph of Block A digital twin aligned with Brick Schema v1.3.
    """
    nodes = []
    
    # Building root
    nodes.append({
        "@id": "verdant:Block_A",
        "@type": "brick:Building",
        "rdfs:label": "Academic Block A",
        "rec:constructionYear": 2018,
        "rec:grossFloorAreaM2": 4200.0,
        "hasPart": [f"verdant:Floor_{f}" for f in [1, 2, 3]]
    })
    
    # Floors
    for f in [1, 2, 3]:
        nodes.append({
            "@id": f"verdant:Floor_{f}",
            "@type": "brick:Floor",
            "rdfs:label": f"Floor {f}",
            "isPartOf": "verdant:Block_A"
        })
        
    # Rooms & Subsystems from SQLite DB
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, floor, capacity, hvac_kw, lighting_kw, plug_kw, type, equipment FROM rooms")
        rooms = [dict(r) for r in cursor.fetchall()]
        
    for rm in rooms:
        rid = rm["id"]
        room_uri = f"verdant:Room_{rid}"
        hvac_zone_uri = f"verdant:HVAC_Zone_{rid}"
        vav_uri = f"verdant:VAV_{rid}"
        sensor_uri = f"verdant:Occupancy_Sensor_{rid}"
        meter_uri = f"verdant:Power_Meter_{rid}"
        thermostat_uri = f"verdant:Thermostat_{rid}"
        
        # Room Node
        nodes.append({
            "@id": room_uri,
            "@type": "brick:Room",
            "rdfs:label": f"{rm['name']} ({rid})",
            "rec:roomCode": rid,
            "rec:seatingCapacity": rm["capacity"],
            "isPartOf": f"verdant:Floor_{rm['floor']}",
            "isLocationOf": [sensor_uri, meter_uri, thermostat_uri, vav_uri],
            "hasHVACZone": hvac_zone_uri
        })
        
        # HVAC Zone & VAV Terminal
        nodes.append({
            "@id": hvac_zone_uri,
            "@type": "brick:HVAC_Zone",
            "rdfs:label": f"Thermal Zone {rid}",
            "feeds": room_uri,
            "hasPart": vav_uri
        })
        
        nodes.append({
            "@id": vav_uri,
            "@type": "brick:Variable_Air_Volume_Box",
            "rdfs:label": f"VAV Terminal Box {rid}",
            "hasPoint": [
                f"verdant:Damper_Position_{rid}",
                f"verdant:Discharge_Air_Temp_{rid}"
            ]
        })
        
        # Sensors & Points
        nodes.append({
            "@id": sensor_uri,
            "@type": "brick:Occupancy_Sensor",
            "rdfs:label": f"Occupancy Sensor {rid} (YOLOv8 Edge Vision + PIR)",
            "isLocatedIn": room_uri,
            "hasPoint": f"verdant:Occupancy_Count_Point_{rid}"
        })
        
        nodes.append({
            "@id": meter_uri,
            "@type": "brick:Electrical_Power_Sensor",
            "rdfs:label": f"Submeter {rid}",
            "isLocatedIn": room_uri,
            "ratedLoadKW": rm["hvac_kw"] + rm["lighting_kw"] + rm["plug_kw"]
        })
        
        nodes.append({
            "@id": thermostat_uri,
            "@type": "brick:Thermostat",
            "rdfs:label": f"Smart Thermostat {rid}",
            "isLocatedIn": room_uri,
            "hasPoint": [
                f"verdant:Temperature_Sensor_{rid}",
                f"verdant:Cooling_Setpoint_{rid}"
            ]
        })

    return {
        "@context": BRICK_CONTEXT,
        "graph_schema": "Brick Schema v1.3",
        "total_entities": len(nodes),
        "total_relationships": sum(len(n.get("isLocationOf", [])) + (1 if "hasHVACZone" in n else 0) for n in nodes),
        "@graph": nodes
    }


def export_brick_turtle_summary() -> str:
    """Exports human-readable Turtle TTL snippet for BIM and digital twin integration."""
    return """
@prefix brick: <https://brickschema.org/schema/Brick#> .
@prefix rec:   <https://w3id.org/rec#> .
@prefix verdant: <https://verdant.ai/schema/campus#> .

verdant:Block_A a brick:Building ;
    rec:grossFloorAreaM2 4200.0 ;
    brick:hasPart verdant:Floor_1, verdant:Floor_2, verdant:Floor_3 .

verdant:Room_202 a brick:Room ;
    rdfs:label "Seminar Hall (202)" ;
    rec:seatingCapacity 60 ;
    brick:isPartOf verdant:Floor_2 ;
    brick:isLocationOf verdant:Occupancy_Sensor_202, verdant:Power_Meter_202, verdant:VAV_202 .

verdant:Occupancy_Sensor_202 a brick:Occupancy_Sensor ;
    brick:hasPoint verdant:Occupancy_Count_202 .

verdant:HVAC_Zone_202 a brick:HVAC_Zone ;
    brick:feeds verdant:Room_202 .
"""
