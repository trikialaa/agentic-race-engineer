import struct

_HDR_FMT = "<HBBBBQfIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)

def decode_lap_data(buf: memoryview):
    offset = _HDR_SIZE
    laps = []
    # Correct LapData entry = 43 bytes
    fmt = "<IIHHfff" + "B"*14 + "HHB"
    size = struct.calcsize(fmt)  # 43

    for _ in range(22):
        values = struct.unpack_from(fmt, buf, offset)
        offset += size
        laps.append({
            "lastLapTimeInMS": values[0],
            "currentLapTimeInMS": values[1],
            "sector1TimeInMS": values[2],
            "sector2TimeInMS": values[3],
            "lapDistance": values[4],
            "totalDistance": values[5],
            "safetyCarDelta": values[6],
            "carPosition": values[7],
            "currentLapNum": values[8],
            "pitStatus": values[9],
            "numPitStops": values[10],
            "sector": values[11],
            "currentLapInvalid": values[12],
            "penalties": values[13],
            "warnings": values[14],
            "numUnservedDriveThroughPens": values[15],
            "numUnservedStopGoPens": values[16],
            "gridPosition": values[17],
            "driverStatus": values[18],
            "resultStatus": values[19],
            "pitLaneTimerActive": values[20],
            "pitLaneTimeInLaneInMS": values[21],
            "pitStopTimerInMS": values[22],
            "pitStopShouldServePen": values[23],
        })

    # two trailing indices
    tt_pb = struct.unpack_from("<B", buf, offset)[0]; offset += 1
    tt_rival = struct.unpack_from("<B", buf, offset)[0]; offset += 1

    return {
        "laps": laps,
        "timeTrialPBIndex": tt_pb,
        "timeTrialRivalIndex": tt_rival
    }
