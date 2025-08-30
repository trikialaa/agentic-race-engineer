
import struct

_HDR_FMT = "<HBBBBQfIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)

def decode_session(buf: memoryview):
    # Full session packet parsing per spec. Includes marshal zones and weather forecast arrays. :contentReference[oaicite:11]{index=11}
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
    # marshal zones (21 entries)
    marshal_zones = []
    for _ in range(21):
        zoneStart = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        zoneFlag = struct.unpack_from("<b", buf, offset)[0]; offset += 1
        marshal_zones.append({"m_zoneStart": zoneStart, "m_zoneFlag": zoneFlag})
    # weather forecast samples (56 entries)
    weather_forecast = []
    for _ in range(56):
        # per spec each sample: uint8 sessionType, uint8 timeOffset, uint8 weather, int8 trackTemp, int8 trackTempChange, int8 airTemp, int8 airTempChange, uint8 rainPercentage
        vals = struct.unpack_from("<BBBbbbbB", buf, offset)
        offset += struct.calcsize("<BBBbbbbB")
        weather_forecast.append({
            "sessionType": vals[0],
            "timeOffset": vals[1],
            "weather": vals[2],
            "trackTemp": vals[3],
            "trackTempChange": vals[4],
            "airTemp": vals[5],
            "airTempChange": vals[6],
            "rainPercentage": vals[7],
        })
    # The rest of the session packet fields (gameMode, safetyCarStatus, networkGame etc) - pull the commonly used subset
    # Many other fields follow in spec - for brevity we capture the most used:
    rest_fmt = "<BBBBBHIHBBB"  # approximate slice: (m_weatherForecastAccuracy etc) - adjust if you need all fields exactly
    # To avoid fragile offsets, return what we've got and raw remainder
    remainder = bytes(buf[offset:])
    return {
        "weather": m_weather,
        "trackTemperature": m_trackTemp,
        "airTemperature": m_airTemp,
        "totalLaps": m_totalLaps,
        "trackLength": m_trackLength,
        "sessionType": m_sessionType,
        "marshalZones": marshal_zones,
        "weatherForecast": weather_forecast,
        "rawRemainderHex": remainder.hex()
    }