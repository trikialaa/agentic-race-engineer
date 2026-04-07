
import struct
import sys
import os

# Add parent directory to path to import constants
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import (
    WEATHER_TYPES,
    SESSION_TYPES,
    TRACK_NAMES,
    FORMULA_TYPES,
    FLAG_COLORS,
    SAFETY_CAR_STATUS,
    GAME_MODES,
    RULESETS,
    SESSION_LENGTH,
    ASSIST_LEVELS,
    GEARBOX_ASSIST,
    DYNAMIC_RACING_LINE,
    DYNAMIC_RACING_LINE_TYPE,
)

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
    
    marshal_zones = []
    weather_forecast = []
    additional_data = {}

    try:
        (m_numMarshalZones,) = struct.unpack_from("<B", buf, offset); offset += 1
        for zone_index in range(21):
            zoneStart = struct.unpack_from("<f", buf, offset)[0]; offset += 4
            zoneFlag = struct.unpack_from("<b", buf, offset)[0]; offset += 1
            marshal_zones.append({
                "zoneStart": zoneStart,
                "zoneFlag": zoneFlag,
                "flagColor": FLAG_COLORS.get(zoneFlag, f"Unknown ({zoneFlag})"),
                "isActive": zone_index < m_numMarshalZones
            })

        (m_safetyCarStatus, m_networkGame, m_numWeatherForecastSamples) = \
            struct.unpack_from("<BBB", buf, offset)
        offset += struct.calcsize("<BBB")

        for sample_index in range(56):
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
                "isValidSample": sample_index < m_numWeatherForecastSamples
            })

        additional_fmt = "<BBIII14BIB"
        additional_size = struct.calcsize(additional_fmt)
        if len(buf) >= offset + additional_size:
            (
                forecast_accuracy,
                ai_difficulty,
                season_link_identifier,
                weekend_link_identifier,
                session_link_identifier,
                pit_stop_window_ideal_lap,
                pit_stop_window_latest_lap,
                pit_stop_rejoin_position,
                steering_assist,
                braking_assist,
                gearbox_assist,
                pit_assist,
                pit_release_assist,
                ers_assist,
                drs_assist,
                dynamic_racing_line,
                dynamic_racing_line_type,
                game_mode,
                rule_set,
                time_of_day,
                session_length,
            ) = struct.unpack_from(additional_fmt, buf, offset)

            additional_data = {
                "numMarshalZones": m_numMarshalZones,
                "safetyCarStatus": m_safetyCarStatus,
                "safetyCarStatusName": SAFETY_CAR_STATUS.get(
                    m_safetyCarStatus, f"Unknown ({m_safetyCarStatus})"
                ),
                "networkGame": bool(m_networkGame),
                "networkGameName": "Online" if m_networkGame else "Offline",
                "numWeatherForecastSamples": m_numWeatherForecastSamples,
                "forecastAccuracy": forecast_accuracy,
                "aiDifficulty": ai_difficulty,
                "seasonLinkIdentifier": season_link_identifier,
                "weekendLinkIdentifier": weekend_link_identifier,
                "sessionLinkIdentifier": session_link_identifier,
                "pitStopWindowIdealLap": pit_stop_window_ideal_lap,
                "pitStopWindowLatestLap": pit_stop_window_latest_lap,
                "pitStopRejoinPosition": pit_stop_rejoin_position,
                "steeringAssist": bool(steering_assist),
                "brakingAssist": braking_assist,
                "brakingAssistName": ASSIST_LEVELS.get(
                    braking_assist, f"Unknown ({braking_assist})"
                ),
                "gearboxAssist": gearbox_assist,
                "gearboxAssistName": GEARBOX_ASSIST.get(
                    gearbox_assist, f"Unknown ({gearbox_assist})"
                ),
                "pitAssist": bool(pit_assist),
                "pitReleaseAssist": bool(pit_release_assist),
                "ERSAssist": bool(ers_assist),
                "DRSAssist": bool(drs_assist),
                "dynamicRacingLine": dynamic_racing_line,
                "dynamicRacingLineName": DYNAMIC_RACING_LINE.get(
                    dynamic_racing_line, f"Unknown ({dynamic_racing_line})"
                ),
                "dynamicRacingLineType": dynamic_racing_line_type,
                "dynamicRacingLineTypeName": DYNAMIC_RACING_LINE_TYPE.get(
                    dynamic_racing_line_type, f"Unknown ({dynamic_racing_line_type})"
                ),
                "gameMode": game_mode,
                "gameModeName": GAME_MODES.get(game_mode, f"Unknown ({game_mode})"),
                "ruleSet": rule_set,
                "ruleSetName": RULESETS.get(rule_set, f"Unknown ({rule_set})"),
                "timeOfDay": time_of_day,
                "sessionLength": session_length,
                "sessionLengthName": SESSION_LENGTH.get(
                    session_length, f"Unknown ({session_length})"
                ),
            }
    except struct.error:
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
