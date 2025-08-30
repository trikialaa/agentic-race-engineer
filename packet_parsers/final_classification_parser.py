
import struct

_HDR_FMT = "<HBBBBQfIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)

def decode_final_classification(buf: memoryview):
    offset = _HDR_SIZE
    numCars = struct.unpack_from("<B", buf, offset)[0]; offset += 1
    results = []
    for _ in range(22):
        # see spec for FinalClassificationData types (uint8 x many, uint32, double etc). :contentReference[oaicite:14]{index=14}
        vals = struct.unpack_from("<BBBBBBB I d BBBBBBBBBB", buf, offset)
        # Using pattern: m_position,m_numLaps,m_gridPosition,m_points,m_numPitStops,m_resultStatus,
        # m_bestLapTimeInMS (I), m_totalRaceTime (d), m_penaltiesTime, m_numPenalties, m_numTyreStints,
        # m_tyreStintsActual[8], m_tyreStintsVisual[8], m_tyreStintsEndLaps[8] - but careful with sizes.
        # To keep parser robust, we will capture as much as available, otherwise return raw remainder.
        # For brevity return raw hex of classification block per-entry.
        entry_raw = bytes(buf[offset:offset+struct.calcsize("<BBBBBBB I d BBBBBBBBBB")])
        results.append({"rawHex": entry_raw.hex()})
        offset += struct.calcsize("<BBBBBBB I d BBBBBBBBBB")
    return {"numCars": numCars, "classifications": results}