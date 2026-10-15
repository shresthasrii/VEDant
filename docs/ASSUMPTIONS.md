# VERDANT · Engineering & Modeling Assumptions

## 1. Energy & Emission Factors (`backend/config/factors.json`)

| Parameter | Default Value | Unit | Engineering Justification & Provenance |
| :--- | :--- | :--- | :--- |
| **Electricity Tariff** | `8.0` | ₹ / kWh | Typical commercial/institutional HT educational tariff in India (e.g. BESCOM / MSEDCL / TANGEDCO). Configurable. |
| **Grid Emission Factor** | `0.70` | kg CO₂ / kWh | Modeled placeholder based on CEA (Central Electricity Authority) CO2 Baseline Database for the Indian Power Sector (User flagged: *Verify latest CEA regional baseline value*). |
| **HVAC Setpoint Sensitivity** | `0.06` (6%) | per °C | ASHRAE 55 and standard building energy modeling rule of thumb: ~6% chiller/compressor energy variation per 1°C setpoint drift from 24°C standard comfort setpoint. |
| **HVAC Ventilation Floor** | `0.35` (35%) | fraction | Minimum outdoor air ventilation required by ASHRAE 62.1 to preserve indoor air quality (IAQ) and prevent CO2 buildup even when rooms are empty. |
| **Lighting Dimming (Sparse)** | `0.40` (40%) | fraction | Modeled luminaire output for occupancy under 15% via smart DALI / 0-10V ballasts. |
| **Lighting Standby (Vacant)** | `0.10` (10%) | fraction | Parasitic driver/emergency path lighting power when room is vacant. |
| **Warmup / Corridor Energy** | `1.5` | kWh / room-day | Fixed startup energy to pull down temperature and illuminate access corridors when an otherwise unpowered room is activated. |

---

## 2. RoomWise™ Consolidation Assumptions (`backend/config/constraints.json`)

1. **Safety Margin (Capacity)**:
   - Configured at `10%`. Effective attendance $A_{\text{eff}}$ multiplied by $1.10$ must fit within room capacity:
     $$A_{\text{eff}} \times (1 + \text{margin}) \le \text{Room Capacity}$$
2. **Specialized Equipment & Room Type**:
   - Labs must remain in labs. A class requiring computers, oscilloscopes, or drafting stations can only move to a space possessing a superset of those features.
3. **Wheelchair Accessibility**:
   - Classes flagged with accessibility needs cannot be relocated to non-accessible floors/rooms.
4. **Compatibility Groups**:
   - Multiple sections may share a space and time slot *only* if explicitly assigned the same `compatibility_group` (e.g., combined sections approved by academic dean). Unrelated classes are **never** combined simply because attendance fits.
5. **Instructor Travel & Fatigue**:
   - Floor changes between consecutive lecture periods are restricted to $\le 1$ level to avoid instructor delay.
6. **Disruption Penalty**:
   - Modeled at `2.0 kWh-equivalent` per moved lecture to balance energy savings against organizational friction.

---

## 3. Privacy & Computer Vision

- **Local Processing**: Video streams are analyzed frame-by-frame on CPU/GPU.
- **Zero Raw Persistence**: Video frames are analyzed in memory for person bounding boxes (COCO class 0) and immediately deleted from RAM. No images or videos are ever written to disk.
- **Zero Identification**: No face recognition, biometric logging, or student tracking exists.
- **Data Model**: The database records only `{room_id, timestamp, count, confidence}`.
