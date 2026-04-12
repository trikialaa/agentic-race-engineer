
import struct

_HDR_FMT = "<HBBBBBQfIIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)

def decode_car_setups(buf: memoryview):
    offset = _HDR_SIZE
    setups = []
    for _ in range(22):
        # struct CarSetupData per spec (see doc). Read fields in order.
        frontWing = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        rearWing = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        onThrottle = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        offThrottle = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        frontCamber = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        rearCamber = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        frontToe = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        rearToe = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        frontSusp = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        rearSusp = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        frontARB = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        rearARB = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        frontSuspHeight = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        rearSuspHeight = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        brakePressure = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        brakeBias = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        rearLeftTyrePressure = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        rearRightTyrePressure = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        frontLeftTyrePressure = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        frontRightTyrePressure = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        ballast = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        fuelLoad = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        setups.append({
            "frontWing": frontWing, "rearWing": rearWing, "onThrottle": onThrottle, "offThrottle": offThrottle,
            "frontCamber": frontCamber, "rearCamber": rearCamber, "frontToe": frontToe, "rearToe": rearToe,
            "frontSuspension": frontSusp, "rearSuspension": rearSusp, "frontAntiRollBar": frontARB, "rearAntiRollBar": rearARB,
            "frontSuspensionHeight": frontSuspHeight, "rearSuspensionHeight": rearSuspHeight,
            "brakePressure": brakePressure, "brakeBias": brakeBias,
            "tyrePressures": [rearLeftTyrePressure, rearRightTyrePressure, frontLeftTyrePressure, frontRightTyrePressure],
            "ballast": ballast, "fuelLoad": fuelLoad
        })
    return {"carSetups": setups}
