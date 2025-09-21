
import struct
import sys
import os

# Add parent directory to path to import constants
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import (WEATHER_TYPES, SESSION_TYPES, TRACK_NAMES, FORMULA_TYPES, 
                      FLAG_COLORS, SAFETY_CAR_STATUS)

_HDR_FMT = "<HBBBBQfIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)

def decode_session(buf: memoryview):
    """
    Decode F1 22 session packet with human-readable session and weather information.
    """
    offset = _HDR_SIZE
    (m_weather, ) = struct.unpack_from("<B", buf, offset); offset += 1
    (m_trackTemp, ) = struct.unpack_from("<b", buf, offset); offset += 1
    (m_airTemp, ) = struct.unpack_from("<b", buf, offset); offset += 1
    (m_totalLaps, ) = struct.unpack_from("<B", buf, offset); offset += 1
    (m_trackLength, ) = struct.unpack_from("<H", buf, offset); offset += 2
    (m_sessionType, ) = struct.unpack_from("<B", buf, offset); offset += 1
    (m_trackId, ) = struct.unpack_from("<b", buf, offset); offset += 1
    (m_formula, ) = struct.unpack_from("<B", buf, offset); offset += 1
    (m_sessionTimeLeft, ) = struct.unpack_from("<H", buf, offset); offset += 2
    (m_sessionDuration, ) = struct.unpack_from("<H", buf, offset); offset += 2
    (m_pitSpeedLimit, ) = struct.unpack_from("<B", buf, offset); offset += 1
    (m_gamePaused, ) = struct.unpack_from("<B", buf, offset); offset += 1
    (m_isSpectating, ) = struct.unpack_from("<B", buf, offset); offset += 1
    (m_spectatorCarIndex, ) = struct.unpack_from("<B", buf, offset); offset += 1
    (m_sliProNativeSupport, ) = struct.unpack_from("<B", buf, offset); offset += 1
    
    # Marshal zones (21 entries)
    marshal_zones = []
    for _ in range(21):
        zoneStart = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        zoneFlag = struct.unpack_from("<b", buf, offset)[0]; offset += 1
        marshal_zones.append({
            "zoneStart": zoneStart, 
            "zoneFlag": zoneFlag,
            "flagColor": FLAG_COLORS.get(zoneFlag, f"Unknown ({zoneFlag})")
        })
    
    # Weather forecast samples (56 entries)
    weather_forecast = []
    for _ in range(56):
        vals = struct.unpack_from("<BBBbbbbB", buf, offset)
        offset += struct.calcsize("<BBBbbbbB")
        
        session_type = vals[0]
        weather_type = vals[2]
        
        weather_forecast.append({
            "sessionType": session_type,
            "sessionTypeName": SESSION_TYPES.get(session_type, f"Unknown ({session_type})"),
            "timeOffset": vals[1],
            "weather": weather_type,
            "weatherName": WEATHER_TYPES.get(weather_type, f"Unknown ({weather_type})"),
            "trackTemp": vals[3],
            "trackTempChange": vals[4],
            "airTemp": vals[5],
            "airTempChange": vals[6],
            "rainPercentage": vals[7],
        })
    
    # Parse additional session data if available
    try:
        # Try to parse more fields from the remainder
        if len(buf) > offset + 20:  # Ensure we have enough bytes
            vals = struct.unpack_from("<BBBBHIHBBB", buf, offset)
            safety_car_status = vals[5]
            game_mode = vals[7] if len(vals) > 7 else None
            
            additional_data = {
                "safetyCarStatus": safety_car_status,
                "safetyCarStatusName": SAFETY_CAR_STATUS.get(safety_car_status, f"Unknown ({safety_car_status})"),
                "gameMode": game_mode
            }
        else:
            additional_data = {}
    except:
        additional_data = {}
    
    return {
        "weather": m_weather,
        "weatherName": WEATHER_TYPES.get(m_weather, f"Unknown ({m_weather})"),
        "trackTemperature": m_trackTemp,
        "airTemperature": m_airTemp,
        "totalLaps": m_totalLaps,
        "trackLength": m_trackLength,
        "trackLengthKm": round(m_trackLength / 1000, 3),
        "sessionType": m_sessionType,
        "sessionTypeName": SESSION_TYPES.get(m_sessionType, f"Unknown ({m_sessionType})"),
        "trackId": m_trackId,
        "trackName": TRACK_NAMES.get(m_trackId, f"Unknown Track ({m_trackId})") if m_trackId >= 0 else "Unknown Track",
        "formula": m_formula,
        "formulaName": FORMULA_TYPES.get(m_formula, f"Unknown ({m_formula})"),
        "sessionTimeLeft": m_sessionTimeLeft,
        "sessionTimeLeftFormatted": f"{m_sessionTimeLeft // 60}:{m_sessionTimeLeft % 60:02d}",
        "sessionDuration": m_sessionDuration,
        "pitSpeedLimit": m_pitSpeedLimit,
        "gamePaused": bool(m_gamePaused),
        "isSpectating": bool(m_isSpectating),
        "spectatorCarIndex": m_spectatorCarIndex,
        "marshalZones": marshal_zones,
        "weatherForecast": weather_forecast,
        **additional_data
    }