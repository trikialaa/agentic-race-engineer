import struct

_HDR_FMT = "<HBBBBQfIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)

def decode_motion(buf: memoryview):
    # CarMotionData x22 then player-only arrays
    # CarMotionData: many floats and int16 direction vectors per car (see spec). :contentReference[oaicite:10]{index=10}
    offset = _HDR_SIZE
    cars = []
    for _ in range(22):
        # Based on CarMotionData struct ordering in spec:
        # 6 floats (world pos/vel), 6 int16 (world forward/ right dirs), float gForceLat, float gForceLong, float gForceVert, float yaw, pitch, roll
        vals = struct.unpack_from("<fff"         # worldPos XYZ
                                  "fff"         # worldVel XYZ
                                  "hhhhhh"      # worldForwardDirX/Y/Z, worldRightDirX/Y/Z (int16)
                                  "fff"         # gForceLateral, longitudinal, vertical
                                  "fff"         # yaw, pitch, roll
                                  , buf, offset)
        offset += struct.calcsize("<fff" "fff" "hhhhhh" "fff" "fff")
        car = {
            "worldPosition": vals[0:3],
            "worldVelocity": vals[3:6],
            "worldForwardDir": [v/32767.0 for v in vals[6:9]],
            "worldRightDir": [v/32767.0 for v in vals[9:12]],
            "gForces": vals[12:15],
            "rotation": vals[15:18],
        }
        cars.append(car)
    # extra player-only arrays (4 suspension pos/vel/acc, wheel speed/slip)
    # Each array is 4 floats
    def read4floats():
        nonlocal offset
        v = struct.unpack_from("<ffff", buf, offset)
        offset += 16
        return list(v)
    extra = {
        "suspensionPosition": read4floats(),
        "suspensionVelocity": read4floats(),
        "suspensionAcceleration": read4floats(),
        "wheelSpeed": read4floats(),
        "wheelSlip": read4floats(),
    }
    # localVelocity (3 floats), angularVelocity (3 floats), angularAcceleration (3 floats), frontWheelsAngle (float)
    localVel = struct.unpack_from("<fff", buf, offset); offset += 12
    angVel = struct.unpack_from("<fff", buf, offset); offset += 12
    angAcc = struct.unpack_from("<fff", buf, offset); offset += 12
    frontWheelsAngle = struct.unpack_from("<f", buf, offset)[0]; offset += 4
    extra.update({
        "localVelocity": list(localVel),
        "angularVelocity": list(angVel),
        "angularAcceleration": list(angAcc),
        "frontWheelsAngle": frontWheelsAngle,
    })
    return {"cars": cars, "playerExtra": extra}