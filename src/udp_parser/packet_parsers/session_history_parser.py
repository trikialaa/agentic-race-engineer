import struct

_HDR_FMT = "<HBBBBBQfIIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)


def _format_lap(ms: int) -> str:
    if not ms:
        return "00:00.000"
    mins = ms // 60000
    secs = (ms % 60000) / 1000.0
    return f"{mins:02d}:{secs:06.3f}"


def _format_sector(ms: int) -> str:
    if not ms:
        return "00.000"
    return f"{ms / 1000.0:.3f}"


def decode_session_history(buf: memoryview):
    offset = _HDR_SIZE
    carIdx = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    numLaps = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    numTyreStints = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    bestLap = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    bestS1 = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    bestS2 = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    bestS3 = struct.unpack_from("<B", buf, offset)[0]
    offset += 1
    lapHistory = []
    for _ in range(100):
        lapTime = struct.unpack_from("<I", buf, offset)[0]
        offset += 4
        s1_ms = struct.unpack_from("<H", buf, offset)[0]
        offset += 2
        s1_min = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        s2_ms = struct.unpack_from("<H", buf, offset)[0]
        offset += 2
        s2_min = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        s3_ms = struct.unpack_from("<H", buf, offset)[0]
        offset += 2
        s3_min = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        lapValid = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        s1 = s1_ms + s1_min * 60000
        s2 = s2_ms + s2_min * 60000
        s3 = s3_ms + s3_min * 60000
        lapHistory.append(
            {
                "lapTimeInMS": lapTime,
                "lapTimeFormatted": _format_lap(lapTime),
                "s1InMS": s1,
                "s2InMS": s2,
                "s3InMS": s3,
                "s1": _format_sector(s1),
                "s2": _format_sector(s2),
                "s3": _format_sector(s3),
                "validFlags": lapValid,
            }
        )
    tyreStints = []
    for _ in range(8):
        endLap = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        tyreActual = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        tyreVisual = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        tyreStints.append({"endLap": endLap, "tyreActual": tyreActual, "tyreVisual": tyreVisual})
    return {
        "carIdx": carIdx,
        "numLaps": numLaps,
        "numTyreStints": numTyreStints,
        "bestLapNum": bestLap,
        "bestSector1LapNum": bestS1,
        "bestSector2LapNum": bestS2,
        "bestSector3LapNum": bestS3,
        "lapHistory": lapHistory,
        "tyreStints": tyreStints,
    }
