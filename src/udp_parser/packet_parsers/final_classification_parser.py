import struct

_HDR_FMT = "<HBBBBBQfIIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)

RESULT_REASON_NAMES = {
    0: "Invalid",
    1: "Retired",
    2: "Finished",
    3: "Terminal damage",
    4: "Inactive",
    5: "Not enough laps completed",
    6: "Black flagged",
    7: "Red flagged",
    8: "Mechanical failure",
    9: "Session skipped",
    10: "Session simulated"
}


def decode_final_classification(buf: memoryview):
    offset = _HDR_SIZE
    num_cars = struct.unpack_from("<B", buf, offset)[0]; offset += 1
    classifications = []

    for _ in range(22):
        position = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        numLaps = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        gridPosition = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        points = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        numPitStops = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        resultStatus = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        resultReason = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        bestLapTime = struct.unpack_from("<I", buf, offset)[0]; offset += 4
        totalRaceTime = struct.unpack_from("<d", buf, offset)[0]; offset += 8
        penaltiesTime = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        numPenalties = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        numTyreStints = struct.unpack_from("<B", buf, offset)[0]; offset += 1

        tyreStintsActual = list(struct.unpack_from("<8B", buf, offset))
        offset += struct.calcsize("<8B")
        tyreStintsVisual = list(struct.unpack_from("<8B", buf, offset))
        offset += struct.calcsize("<8B")
        tyreStintsEndLaps = list(struct.unpack_from("<8B", buf, offset))
        offset += struct.calcsize("<8B")

        classifications.append({
            "position": position,
            "numLaps": numLaps,
            "gridPosition": gridPosition,
            "points": points,
            "numPitStops": numPitStops,
            "resultStatus": resultStatus,
            "resultReason": resultReason,
            "resultReasonName": RESULT_REASON_NAMES.get(resultReason, f"Unknown ({resultReason})"),
            "bestLapTimeInMS": bestLapTime,
            "totalRaceTime": totalRaceTime,
            "penaltiesTime": penaltiesTime,
            "numPenalties": numPenalties,
            "numTyreStints": numTyreStints,
            "tyreStintsActual": tyreStintsActual,
            "tyreStintsVisual": tyreStintsVisual,
            "tyreStintsEndLaps": tyreStintsEndLaps,
        })

    return {"numCars": num_cars, "classificationData": classifications}
