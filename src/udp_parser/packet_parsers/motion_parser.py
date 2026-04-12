import struct

_HDR_FMT = "<HBBBBBQfIIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)

def decode_motion(buf: memoryview):
    """Decode the F1 25 motion packet (car data only)."""
    offset = _HDR_SIZE
    cars = []
    for _ in range(22):
        vals = struct.unpack_from(
            "<fff"      # worldPosition XYZ
            "fff"       # worldVelocity XYZ
            "hhhhhh"    # worldForwardDir / worldRightDir
            "fff"       # gForceLateral / Longitudinal / Vertical
            "fff",      # yaw / pitch / roll
            buf,
            offset,
        )
        offset += struct.calcsize("<fff" "fff" "hhhhhh" "fff" "fff")
        car = {
            "worldPosition": vals[0:3],
            "worldVelocity": vals[3:6],
            "worldForwardDir": [v / 32767.0 for v in vals[6:9]],
            "worldRightDir": [v / 32767.0 for v in vals[9:12]],
            "gForces": vals[12:15],
            "rotation": vals[15:18],
        }
        cars.append(car)
    return {"cars": cars}
