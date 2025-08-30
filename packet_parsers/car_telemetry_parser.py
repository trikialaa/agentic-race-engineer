
import struct

_HDR_FMT = "<HBBBBQfIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)

def decode_car_telemetry(buf: memoryview):
    offset = _HDR_SIZE
    cars = []
    for _ in range(22):
        m_speed = struct.unpack_from("<H", buf, offset)[0]; offset += 2
        m_throttle = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        m_steer = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        m_brake = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        m_clutch = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        m_gear = struct.unpack_from("<b", buf, offset)[0]; offset += 1
        m_engineRPM = struct.unpack_from("<H", buf, offset)[0]; offset += 2
        m_drs = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        m_revLightsPercent = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        m_revLightsBitValue = struct.unpack_from("<H", buf, offset)[0]; offset += 2
        brakesTemp = list(struct.unpack_from("<HHHH", buf, offset)); offset += 8
        tyresSurfaceTemp = list(struct.unpack_from("<BBBB", buf, offset)); offset += 4
        tyresInnerTemp = list(struct.unpack_from("<BBBB", buf, offset)); offset += 4
        engineTemp = struct.unpack_from("<H", buf, offset)[0]; offset += 2
        tyresPressure = list(struct.unpack_from("<ffff", buf, offset)); offset += 16
        surfaceType = list(struct.unpack_from("<BBBB", buf, offset)); offset += 4
        cars.append({
            "speedKph": m_speed, "throttle": m_throttle, "steer": m_steer, "brake": m_brake,
            "clutch": m_clutch, "gear": m_gear, "engineRPM": m_engineRPM, "drs": m_drs,
            "revLightsPercent": m_revLightsPercent, "revLightsBitValue": m_revLightsBitValue,
            "brakesTemperature": brakesTemp, "tyresSurfaceTemperature": tyresSurfaceTemp,
            "tyresInnerTemperature": tyresInnerTemp, "engineTemperature": engineTemp,
            "tyresPressure": tyresPressure, "surfaceType": surfaceType
        })
    m_mfdPanelIndex = struct.unpack_from("<B", buf, offset)[0]; offset += 1
    m_mfdPanelIndexSecondary = struct.unpack_from("<B", buf, offset)[0]; offset += 1
    m_suggestedGear = struct.unpack_from("<b", buf, offset)[0]; offset += 1
    return {"carTelemetry": cars, "mfdPanelIndex": m_mfdPanelIndex, "mfdPanelIndexSecondary": m_mfdPanelIndexSecondary, "suggestedGear": m_suggestedGear}
