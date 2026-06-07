import struct

_HDR_FMT = "<HBBBBBQfIIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)


def decode_tyre_sets(buf: memoryview):
    offset = _HDR_SIZE
    car_idx = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    tyre_sets = []
    for _ in range(20):
        actual_compound = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        visual_compound = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        wear = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        available = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        recommended_session = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        life_span = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        usable_life = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        lap_delta_time = struct.unpack_from("<h", buf, offset)[0]
        offset += 2
        fitted = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        tyre_sets.append(
            {
                "actualTyreCompound": actual_compound,
                "visualTyreCompound": visual_compound,
                "wear": wear,
                "available": bool(available),
                "recommendedSession": recommended_session,
                "lifeSpan": life_span,
                "usableLife": usable_life,
                "lapDeltaTime": lap_delta_time,
                "isFitted": bool(fitted),
            }
        )
    fitted_idx = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    return {"carIndex": car_idx, "tyreSets": tyre_sets, "fittedIndex": fitted_idx}
