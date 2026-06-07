import os
import struct
import sys

# Add parent directory to path to import constants
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import (
    ASSIST_LEVELS,
    DYNAMIC_RACING_LINE,
    DYNAMIC_RACING_LINE_TYPE,
    FLAG_COLORS,
    FORMULA_TYPES,
    GAME_MODES,
    GEARBOX_ASSIST,
    RULESETS,
    SAFETY_CAR_STATUS,
    SESSION_LENGTH,
    SESSION_TYPES,
    TRACK_NAMES,
    WEATHER_TYPES,
)

_HDR_FMT = "<HBBBBBQfIIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)


def decode_session(buf: memoryview):
    """
    Decode the F1 25 session packet with the expanded set of controls and options.
    """
    offset = _HDR_SIZE
    m_weather = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_trackTemperature = struct.unpack_from("<b", buf, offset)[0]
    offset += 1
    m_airTemperature = struct.unpack_from("<b", buf, offset)[0]
    offset += 1
    m_totalLaps = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_trackLength = struct.unpack_from("<H", buf, offset)[0]
    offset += 2
    m_sessionType = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_trackId = struct.unpack_from("<b", buf, offset)[0]
    offset += 1
    m_formula = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_sessionTimeLeft = struct.unpack_from("<H", buf, offset)[0]
    offset += 2
    m_sessionDuration = struct.unpack_from("<H", buf, offset)[0]
    offset += 2
    m_pitSpeedLimit = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_gamePaused = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_isSpectating = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_spectatorCarIndex = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_sliProNativeSupport = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_numMarshalZones = struct.unpack_from("<B", buf, offset)[0]
    offset += 1

    marshal_zones = []
    for zone_index in range(21):
        zone_start = struct.unpack_from("<f", buf, offset)[0]
        offset += 4
        zone_flag = struct.unpack_from("<b", buf, offset)[0]
        offset += 1
        marshal_zones.append(
            {
                "zoneStart": zone_start,
                "zoneFlag": zone_flag,
                "flagName": FLAG_COLORS.get(zone_flag, f"Unknown ({zone_flag})"),
                "isActive": zone_index < m_numMarshalZones,
            }
        )

    m_safetyCarStatus = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_networkGame = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_numWeatherForecastSamples = struct.unpack_from("<B", buf, offset)[0]
    offset += 1

    weather_forecast = []
    for sample_index in range(64):
        vals = struct.unpack_from("<BBBbbbbB", buf, offset)
        offset += struct.calcsize("<BBBbbbbB")
        sample = {
            "sessionType": vals[0],
            "sessionTypeName": SESSION_TYPES.get(vals[0], f"Unknown ({vals[0]})"),
            "timeOffset": vals[1],
            "weather": vals[2],
            "weatherName": WEATHER_TYPES.get(vals[2], f"Unknown ({vals[2]})"),
            "trackTemp": vals[3],
            "trackTempChange": vals[4],
            "airTemp": vals[5],
            "airTempChange": vals[6],
            "rainPercentage": vals[7],
            "isValidSample": sample_index < m_numWeatherForecastSamples,
        }
        if sample["isValidSample"]:
            weather_forecast.append(sample)

    m_forecastAccuracy = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_aiDifficulty = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_seasonLinkIdentifier = struct.unpack_from("<I", buf, offset)[0]
    offset += 4
    m_weekendLinkIdentifier = struct.unpack_from("<I", buf, offset)[0]
    offset += 4
    m_sessionLinkIdentifier = struct.unpack_from("<I", buf, offset)[0]
    offset += 4
    m_pitStopWindowIdealLap = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_pitStopWindowLatestLap = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_pitStopRejoinPosition = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_steeringAssist = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_brakingAssist = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_gearboxAssist = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_pitAssist = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_pitReleaseAssist = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_ERSAssist = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_DRSAssist = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_dynamicRacingLine = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_dynamicRacingLineType = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_gameMode = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_ruleSet = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_timeOfDay = struct.unpack_from("<I", buf, offset)[0]
    offset += 4
    m_sessionLength = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_speedUnitsLeadPlayer = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_temperatureUnitsLeadPlayer = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_speedUnitsSecondaryPlayer = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_temperatureUnitsSecondaryPlayer = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_numSafetyCarPeriods = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_numVirtualSafetyCarPeriods = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_numRedFlagPeriods = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_equalCarPerformance = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_recoveryMode = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_flashbackLimit = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_surfaceType = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_lowFuelMode = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_raceStarts = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_tyreTemperature = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_pitLaneTyreSim = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_carDamage = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_carDamageRate = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_collisions = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_collisionsOffForFirstLapOnly = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_mpUnsafePitRelease = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_mpOffForGriefing = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_cornerCuttingStringency = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_parcFermeRules = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_pitStopExperience = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_safetyCar = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_safetyCarExperience = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_formationLap = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_formationLapExperience = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_redFlags = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_affectsLicenceLevelSolo = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_affectsLicenceLevelMP = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_numSessionsInWeekend = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    weekend_structure = list(struct.unpack_from("<12B", buf, offset))
    offset += struct.calcsize("<12B")
    m_sector2LapDistanceStart = struct.unpack_from("<f", buf, offset)[0]
    offset += 4
    m_sector3LapDistanceStart = struct.unpack_from("<f", buf, offset)[0]
    offset += 4

    return {
        "weather": m_weather,
        "weatherName": WEATHER_TYPES.get(m_weather, f"Unknown ({m_weather})"),
        "trackTemperature": m_trackTemperature,
        "airTemperature": m_airTemperature,
        "totalLaps": m_totalLaps,
        "trackLength": m_trackLength,
        "trackLengthKm": round(m_trackLength / 1000, 3),
        "sessionType": m_sessionType,
        "sessionTypeName": SESSION_TYPES.get(m_sessionType, f"Unknown ({m_sessionType})"),
        "trackId": m_trackId,
        "trackName": TRACK_NAMES.get(m_trackId, f"Unknown ({m_trackId})")
        if m_trackId >= 0
        else "Unknown Track",
        "formula": m_formula,
        "formulaName": FORMULA_TYPES.get(m_formula, f"Unknown ({m_formula})"),
        "sessionTimeLeft": m_sessionTimeLeft,
        "sessionTimeLeftFormatted": f"{m_sessionTimeLeft // 60}:{m_sessionTimeLeft % 60:02d}",
        "sessionDuration": m_sessionDuration,
        "pitSpeedLimit": m_pitSpeedLimit,
        "gamePaused": bool(m_gamePaused),
        "isSpectating": bool(m_isSpectating),
        "spectatorCarIndex": m_spectatorCarIndex,
        "sliProNativeSupport": bool(m_sliProNativeSupport),
        "marshalZones": marshal_zones,
        "safetyCarStatus": m_safetyCarStatus,
        "safetyCarStatusName": SAFETY_CAR_STATUS.get(
            m_safetyCarStatus, f"Unknown ({m_safetyCarStatus})"
        ),
        "networkGame": bool(m_networkGame),
        "numMarshalZones": m_numMarshalZones,
        "weatherForecast": weather_forecast,
        "numWeatherForecastSamples": m_numWeatherForecastSamples,
        "forecastAccuracy": m_forecastAccuracy,
        "aiDifficulty": m_aiDifficulty,
        "seasonLinkIdentifier": m_seasonLinkIdentifier,
        "weekendLinkIdentifier": m_weekendLinkIdentifier,
        "sessionLinkIdentifier": m_sessionLinkIdentifier,
        "pitStopWindowIdealLap": m_pitStopWindowIdealLap,
        "pitStopWindowLatestLap": m_pitStopWindowLatestLap,
        "pitStopRejoinPosition": m_pitStopRejoinPosition,
        "steeringAssist": bool(m_steeringAssist),
        "brakingAssist": m_brakingAssist,
        "brakingAssistName": ASSIST_LEVELS.get(m_brakingAssist, f"Unknown ({m_brakingAssist})"),
        "gearboxAssist": m_gearboxAssist,
        "gearboxAssistName": GEARBOX_ASSIST.get(m_gearboxAssist, f"Unknown ({m_gearboxAssist})"),
        "pitAssist": bool(m_pitAssist),
        "pitReleaseAssist": bool(m_pitReleaseAssist),
        "ERSAssist": bool(m_ERSAssist),
        "DRSAssist": bool(m_DRSAssist),
        "dynamicRacingLine": m_dynamicRacingLine,
        "dynamicRacingLineName": DYNAMIC_RACING_LINE.get(
            m_dynamicRacingLine, f"Unknown ({m_dynamicRacingLine})"
        ),
        "dynamicRacingLineType": m_dynamicRacingLineType,
        "dynamicRacingLineTypeName": DYNAMIC_RACING_LINE_TYPE.get(
            m_dynamicRacingLineType, f"Unknown ({m_dynamicRacingLineType})"
        ),
        "gameMode": m_gameMode,
        "gameModeName": GAME_MODES.get(m_gameMode, f"Unknown ({m_gameMode})"),
        "ruleSet": m_ruleSet,
        "ruleSetName": RULESETS.get(m_ruleSet, f"Unknown ({m_ruleSet})"),
        "timeOfDay": m_timeOfDay,
        "sessionLength": m_sessionLength,
        "sessionLengthName": SESSION_LENGTH.get(m_sessionLength, f"Unknown ({m_sessionLength})"),
        "speedUnitsLeadPlayer": "KPH" if m_speedUnitsLeadPlayer == 1 else "MPH",
        "temperatureUnitsLeadPlayer": "Fahrenheit" if m_temperatureUnitsLeadPlayer else "Celsius",
        "speedUnitsSecondaryPlayer": "KPH" if m_speedUnitsSecondaryPlayer == 1 else "MPH",
        "temperatureUnitsSecondaryPlayer": "Fahrenheit"
        if m_temperatureUnitsSecondaryPlayer
        else "Celsius",
        "numSafetyCarPeriods": m_numSafetyCarPeriods,
        "numVirtualSafetyCarPeriods": m_numVirtualSafetyCarPeriods,
        "numRedFlagPeriods": m_numRedFlagPeriods,
        "equalCarPerformance": bool(m_equalCarPerformance),
        "recoveryMode": m_recoveryMode,
        "flashbackLimit": m_flashbackLimit,
        "surfaceType": m_surfaceType,
        "lowFuelMode": m_lowFuelMode,
        "raceStarts": m_raceStarts,
        "tyreTemperature": m_tyreTemperature,
        "pitLaneTyreSim": bool(m_pitLaneTyreSim),
        "carDamage": m_carDamage,
        "carDamageRate": m_carDamageRate,
        "collisions": m_collisions,
        "collisionsOffForFirstLapOnly": bool(m_collisionsOffForFirstLapOnly),
        "mpUnsafePitRelease": bool(m_mpUnsafePitRelease),
        "mpOffForGriefing": bool(m_mpOffForGriefing),
        "cornerCuttingStringency": m_cornerCuttingStringency,
        "parcFermeRules": bool(m_parcFermeRules),
        "pitStopExperience": m_pitStopExperience,
        "safetyCar": m_safetyCar,
        "safetyCarExperience": m_safetyCarExperience,
        "formationLap": bool(m_formationLap),
        "formationLapExperience": m_formationLapExperience,
        "redFlags": m_redFlags,
        "affectsLicenceLevelSolo": bool(m_affectsLicenceLevelSolo),
        "affectsLicenceLevelMP": bool(m_affectsLicenceLevelMP),
        "numSessionsInWeekend": m_numSessionsInWeekend,
        "weekendStructure": weekend_structure,
        "sector2LapDistanceStart": m_sector2LapDistanceStart,
        "sector3LapDistanceStart": m_sector3LapDistanceStart,
    }
