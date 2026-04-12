import struct

_HDR_FMT = "<HBBBBBQfIIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)


def _read_floats(buf: memoryview, offset: int, count: int):
    fmt = "<" + "f" * count
    values = struct.unpack_from(fmt, buf, offset)
    return list(values), offset + struct.calcsize(fmt)


def decode_motion_ex(buf: memoryview):
    """Decode the F1 25 Motion Ex packet (player-only extended data)."""
    offset = _HDR_SIZE
    data = {}

    data["suspensionPosition"], offset = _read_floats(buf, offset, 4)
    data["suspensionVelocity"], offset = _read_floats(buf, offset, 4)
    data["suspensionAcceleration"], offset = _read_floats(buf, offset, 4)
    data["wheelSpeed"], offset = _read_floats(buf, offset, 4)
    data["wheelSlipRatio"], offset = _read_floats(buf, offset, 4)
    data["wheelSlipAngle"], offset = _read_floats(buf, offset, 4)
    data["wheelLatForce"], offset = _read_floats(buf, offset, 4)
    data["wheelLongForce"], offset = _read_floats(buf, offset, 4)

    data["heightOfCOGAboveGround"] = struct.unpack_from("<f", buf, offset)[0]
    offset += 4

    data["localVelocity"], offset = _read_floats(buf, offset, 3)
    data["angularVelocity"], offset = _read_floats(buf, offset, 3)
    data["angularAcceleration"], offset = _read_floats(buf, offset, 3)

    data["frontWheelsAngle"] = struct.unpack_from("<f", buf, offset)[0]
    offset += 4
    data["wheelVertForce"], offset = _read_floats(buf, offset, 4)

    data["frontAeroHeight"] = struct.unpack_from("<f", buf, offset)[0]
    offset += 4
    data["rearAeroHeight"] = struct.unpack_from("<f", buf, offset)[0]
    offset += 4
    data["frontRollAngle"] = struct.unpack_from("<f", buf, offset)[0]
    offset += 4
    data["rearRollAngle"] = struct.unpack_from("<f", buf, offset)[0]
    offset += 4
    data["chassisYaw"] = struct.unpack_from("<f", buf, offset)[0]
    offset += 4
    data["chassisPitch"] = struct.unpack_from("<f", buf, offset)[0]
    offset += 4

    data["wheelCamber"], offset = _read_floats(buf, offset, 4)
    data["wheelCamberGain"], offset = _read_floats(buf, offset, 4)

    return {"playerExtra": data}
