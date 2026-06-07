import os
import struct
import sys

# Add parent directory to path to import constants
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import (
    DRS_STATUS,
    MFD_PANELS,
    SPEED_CONVERSIONS,
    SURFACE_TYPES,
    TEMP_THRESHOLDS,
    WHEEL_ORDER,
)

_HDR_FMT = "<HBBBBBQfIIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)


def decode_car_telemetry(buf: memoryview):
    """
    Decode F1 25 car telemetry packet with enhanced temperature warnings and surface information.
    """

    def get_temp_status(temp, warning_threshold, critical_threshold):
        """Get temperature status with warning levels"""
        if temp >= critical_threshold:
            return "CRITICAL"
        elif temp >= warning_threshold:
            return "WARNING"
        else:
            return "OK"

    def format_gear(gear):
        """Format gear display"""
        if gear == 0:
            return "N"
        elif gear == -1:
            return "R"
        else:
            return str(gear)

    offset = _HDR_SIZE
    cars = []

    for car_idx in range(22):
        m_speed = struct.unpack_from("<H", buf, offset)[0]
        offset += 2
        m_throttle = struct.unpack_from("<f", buf, offset)[0]
        offset += 4
        m_steer = struct.unpack_from("<f", buf, offset)[0]
        offset += 4
        m_brake = struct.unpack_from("<f", buf, offset)[0]
        offset += 4
        m_clutch = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        m_gear = struct.unpack_from("<b", buf, offset)[0]
        offset += 1
        m_engineRPM = struct.unpack_from("<H", buf, offset)[0]
        offset += 2
        m_drs = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        m_revLightsPercent = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        m_revLightsBitValue = struct.unpack_from("<H", buf, offset)[0]
        offset += 2
        brakesTemp = list(struct.unpack_from("<HHHH", buf, offset))
        offset += 8
        tyresSurfaceTemp = list(struct.unpack_from("<BBBB", buf, offset))
        offset += 4
        tyresInnerTemp = list(struct.unpack_from("<BBBB", buf, offset))
        offset += 4
        engineTemp = struct.unpack_from("<H", buf, offset)[0]
        offset += 2
        tyresPressure = list(struct.unpack_from("<ffff", buf, offset))
        offset += 16
        surfaceType = list(struct.unpack_from("<BBBB", buf, offset))
        offset += 4

        # Enhanced surface type information
        surface_names = [SURFACE_TYPES.get(s, f"Unknown ({s})") for s in surfaceType]

        # Temperature analysis
        engine_temp_status = get_temp_status(
            engineTemp, TEMP_THRESHOLDS["engine_warning"], TEMP_THRESHOLDS["engine_critical"]
        )

        brake_temp_status = [
            get_temp_status(
                temp, TEMP_THRESHOLDS["brake_warning"], TEMP_THRESHOLDS["brake_critical"]
            )
            for temp in brakesTemp
        ]

        tyre_temp_status = [
            get_temp_status(temp, TEMP_THRESHOLDS["tyre_warning"], TEMP_THRESHOLDS["tyre_critical"])
            for temp in tyresSurfaceTemp
        ]

        car_data = {
            "carIndex": car_idx,
            "speedKph": m_speed,
            "speedMph": round(m_speed * SPEED_CONVERSIONS["kmh_to_mph"], 1),
            "throttle": m_throttle,
            "throttlePercent": round(m_throttle * 100, 1),
            "steer": m_steer,
            "brake": m_brake,
            "brakePercent": round(m_brake * 100, 1),
            "clutch": m_clutch,
            "gear": m_gear,
            "gearDisplay": format_gear(m_gear),
            "engineRPM": m_engineRPM,
            "drs": m_drs,
            "drsStatus": DRS_STATUS.get(m_drs, f"Unknown ({m_drs})"),
            "revLightsPercent": m_revLightsPercent,
            "revLightsBitValue": m_revLightsBitValue,
            # Temperature data with status
            "brakesTemperature": brakesTemp,
            "brakeTempStatus": brake_temp_status,
            "tyresSurfaceTemperature": tyresSurfaceTemp,
            "tyreTempStatus": tyre_temp_status,
            "tyresInnerTemperature": tyresInnerTemp,
            "engineTemperature": engineTemp,
            "engineTempStatus": engine_temp_status,
            # Tyre pressure
            "tyresPressure": tyresPressure,
            "tyresPressurePSI": [round(p, 1) for p in tyresPressure],
            # Surface information
            "surfaceType": surfaceType,
            "surfaceNames": surface_names,
            "surfaceByWheel": {WHEEL_ORDER[i]: surface_names[i] for i in range(4)},
            # Warning flags
            "hasEngineWarning": engine_temp_status in ["WARNING", "CRITICAL"],
            "hasBrakeWarning": any(
                status in ["WARNING", "CRITICAL"] for status in brake_temp_status
            ),
            "hasTyreWarning": any(status in ["WARNING", "CRITICAL"] for status in tyre_temp_status),
        }
        cars.append(car_data)

    # MFD and suggested gear
    m_mfdPanelIndex = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_mfdPanelIndexSecondary = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    m_suggestedGear = struct.unpack_from("<b", buf, offset)[0]
    offset += 1

    return {
        "carTelemetry": cars,
        "mfdPanelIndex": m_mfdPanelIndex,
        "mfdPanelName": MFD_PANELS.get(m_mfdPanelIndex, f"Unknown ({m_mfdPanelIndex})"),
        "mfdPanelIndexSecondary": m_mfdPanelIndexSecondary,
        "mfdPanelNameSecondary": MFD_PANELS.get(
            m_mfdPanelIndexSecondary, f"Unknown ({m_mfdPanelIndexSecondary})"
        ),
        "suggestedGear": m_suggestedGear,
        "suggestedGearDisplay": format_gear(m_suggestedGear)
        if m_suggestedGear != 0
        else "No suggestion",
    }
