
import struct

_HDR_FMT = "<HBBBBQfIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)

def decode_session_history(buf: memoryview):
    offset = _HDR_SIZE
    carIdx = struct.unpack_from("<B", buf, offset)[0]; offset += 1
    numLaps = struct.unpack_from("<B", buf, offset)[0]; offset += 1
    numTyreStints = struct.unpack_from("<B", buf, offset)[0]; offset += 1
    bestLap = struct.unpack_from("<B", buf, offset)[0]; offset += 1
    bestS1 = struct.unpack_from("<B", buf, offset)[0]; offset += 1
    bestS2 = struct.unpack_from("<B", buf, offset)[0]; offset += 1
    bestS3 = struct.unpack_from("<B", buf, offset)[0]; offset += 1
    lapHistory = []
    for _ in range(100):
        lapTime = struct.unpack_from("<I", buf, offset)[0]; offset += 4
        s1 = struct.unpack_from("<H", buf, offset)[0]; offset += 2
        s2 = struct.unpack_from("<H", buf, offset)[0]; offset += 2
        s3 = struct.unpack_from("<H", buf, offset)[0]; offset += 2
        lapValid = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        lapHistory.append({"lapTimeInMS": lapTime, "s1": s1, "s2": s2, "s3": s3, "validFlags": lapValid})
    tyreStints = []
    for _ in range(8):
        endLap = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        tyreActual = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        tyreVisual = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        tyreStints.append({"endLap": endLap, "tyreActual": tyreActual, "tyreVisual": tyreVisual})
    return {"carIdx": carIdx, "numLaps": numLaps, "numTyreStints": numTyreStints, "bestLapNum": bestLap, "bestSector1LapNum": bestS1, "bestSector2LapNum": bestS2, "bestSector3LapNum": bestS3, "lapHistory": lapHistory, "tyreStints": tyreStints}