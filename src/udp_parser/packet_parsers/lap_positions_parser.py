import struct

_HDR_FMT = "<HBBBBBQfIIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)


def decode_lap_positions(buf: memoryview):
    offset = _HDR_SIZE
    num_laps = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    lap_start = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    positions = []
    for _ in range(50):
        row = list(struct.unpack_from("<22B", buf, offset))
        offset += struct.calcsize("<22B")
        positions.append(row)
    return {
        "numLaps": num_laps,
        "lapStart": lap_start,
        "positions": positions,
    }
