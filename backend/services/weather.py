import math
from typing import Dict, Any, List

def get_microclimate_forecast() -> Dict[str, Any]:
    """
    Returns 24-hour campus microclimate forecast including ambient temperature,
    relative humidity, solar insolation (W/m2), and thermal envelope load.
    """
    hourly_weather = []
    
    # Campus parameters
    base_t = 23.5  # dawn minimum temperature
    peak_t = 36.8  # 14:00 afternoon peak temperature
    amplitude = (peak_t - base_t) / 2.0
    mid_t = base_t + amplitude
    
    for h in range(24):
        # Diurnal temperature cycle: peaks at h=14
        angle = (h - 14) * (2.0 * math.pi / 24.0)
        temp_c = mid_t + amplitude * math.cos(angle)
        
        # Relative humidity (inversely related to temperature)
        rh_pct = max(38.0, min(82.0, 78.0 - (temp_c - 24.0) * 3.2))
        
        # Solar insolation W/m2 (daylight hours 06:00 - 18:00)
        if 6 <= h <= 18:
            solar_angle = (h - 12) * (math.pi / 12.0)
            solar_wm2 = max(0.0, 840.0 * math.cos(solar_angle))
        else:
            solar_wm2 = 0.0
            
        # Cooling degree impact: relative to indoor baseline setpoint 24.0 C
        delta_t = max(0.0, temp_c - 24.0)
        # Envelope thermal heat gain index (kW thermal load across building)
        envelope_heat_gain_kw = delta_t * 1.8 + (solar_wm2 / 840.0) * 4.2
        
        hourly_weather.append({
            "hour": h,
            "time": f"{h:02d}:00",
            "temperature_c": round(temp_c, 1),
            "humidity_pct": round(rh_pct, 1),
            "solar_wm2": round(solar_wm2, 1),
            "cooling_load_impact_kw": round(envelope_heat_gain_kw, 2)
        })
        
    avg_temp = sum(w["temperature_c"] for w in hourly_weather) / 24.0
    max_temp = max(w["temperature_c"] for w in hourly_weather)
    min_temp = min(w["temperature_c"] for w in hourly_weather)
    
    return {
        "location": "Academic Block A Microclimate Station",
        "current_temperature_c": hourly_weather[15]["temperature_c"],
        "min_temperature_c": round(min_temp, 1),
        "max_temperature_c": round(max_temp, 1),
        "avg_temperature_c": round(avg_temp, 1),
        "solar_peak_wm2": 840.0,
        "precooling_window": "05:00 - 07:00 (Thermal Mass coasting recommended)",
        "precooling_saving_pct": 11.5,
        "hourly": hourly_weather,
        "advisory": (
            f"Afternoon peak temperature forecast at {max_temp}°C (14:00). "
            "Pre-cooling the academic block at 05:00–07:00 off-peak rate (₹5.50/kWh) "
            "avoids 11.5% chiller peak load during 14:00–16:00 solar surge."
        )
    }
