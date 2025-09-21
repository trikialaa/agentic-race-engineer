import struct
import sys
import os

# Add parent directory to path to import constants
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import (PIT_STATUS, SECTORS, DRIVER_STATUS, RESULT_STATUS)

_HDR_FMT = "<HBBBBQfIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)

def decode_lap_data(buf: memoryview):
    """
    Decode F1 22 lap data packet with human-readable status information.
    """
    def format_lap_time(time_ms):
        """Convert milliseconds to MM:SS.mmm format"""
        if time_ms == 0:
            return "00:00.000"
        total_seconds = time_ms / 1000
        minutes = int(total_seconds // 60)
        seconds = total_seconds % 60
        return f"{minutes:02d}:{seconds:06.3f}"
    
    def format_sector_time(time_ms):
        """Convert milliseconds to SS.mmm format"""
        if time_ms == 0:
            return "00.000"
        seconds = time_ms / 1000
        return f"{seconds:06.3f}"
    
    offset = _HDR_SIZE
    laps = []
    # Correct LapData entry = 43 bytes
    fmt = "<IIHHfff" + "B"*14 + "HHB"
    size = struct.calcsize(fmt)  # 43

    for car_idx in range(22):
        values = struct.unpack_from(fmt, buf, offset)
        offset += size
        
        pit_status = values[9]
        sector = values[11]
        driver_status = values[18]
        result_status = values[19]
        
        lap_data = {
            "carIndex": car_idx,
            "lastLapTimeInMS": values[0],
            "lastLapTimeFormatted": format_lap_time(values[0]),
            "currentLapTimeInMS": values[1],
            "currentLapTimeFormatted": format_lap_time(values[1]),
            "sector1TimeInMS": values[2],
            "sector1TimeFormatted": format_sector_time(values[2]),
            "sector2TimeInMS": values[3],
            "sector2TimeFormatted": format_sector_time(values[3]),
            "lapDistance": values[4],
            "totalDistance": values[5],
            "totalDistanceKm": round(values[5] / 1000, 3),
            "safetyCarDelta": values[6],
            "carPosition": values[7],
            "currentLapNum": values[8],
            "pitStatus": pit_status,
            "pitStatusName": PIT_STATUS.get(pit_status, f"Unknown ({pit_status})"),
            "numPitStops": values[10],
            "sector": sector,
            "sectorName": SECTORS.get(sector, f"Unknown ({sector})"),
            "currentLapInvalid": bool(values[12]),
            "penalties": values[13],
            "penaltiesFormatted": f"{values[13]}s" if values[13] > 0 else "None",
            "warnings": values[14],
            "numUnservedDriveThroughPens": values[15],
            "numUnservedStopGoPens": values[16],
            "gridPosition": values[17],
            "driverStatus": driver_status,
            "driverStatusName": DRIVER_STATUS.get(driver_status, f"Unknown ({driver_status})"),
            "resultStatus": result_status,
            "resultStatusName": RESULT_STATUS.get(result_status, f"Unknown ({result_status})"),
            "pitLaneTimerActive": bool(values[20]),
            "pitLaneTimeInLaneInMS": values[21],
            "pitLaneTimeFormatted": f"{values[21]/1000:.3f}s" if values[21] > 0 else "0.000s",
            "pitStopTimerInMS": values[22],
            "pitStopTimeFormatted": f"{values[22]/1000:.3f}s" if values[22] > 0 else "0.000s",
            "pitStopShouldServePen": bool(values[23]),
        }
        laps.append(lap_data)

    # Time trial indices
    tt_pb = struct.unpack_from("<B", buf, offset)[0]; offset += 1
    tt_rival = struct.unpack_from("<B", buf, offset)[0]; offset += 1

    return {
        "laps": laps,
        "timeTrialPBIndex": tt_pb if tt_pb != 255 else None,
        "timeTrialRivalIndex": tt_rival if tt_rival != 255 else None
    }
