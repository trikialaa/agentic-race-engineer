import struct
import sys
import os

# Add parent directory to path to import constants
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import (PIT_STATUS, SECTORS, DRIVER_STATUS, RESULT_STATUS)

_HDR_FMT = "<HBBBBBQfIIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)

def decode_lap_data(buf: memoryview):
    """
    Decode the F1 25 lap data packet with the extra delta and speed-trap fields.
    """
    def _format_time(minutes, ms):
        total = ms + minutes * 60000
        if total == 0:
            return "00:00.000"
        mins = int(total // 60000)
        secs = (total % 60000) / 1000
        return f"{mins:02d}:{secs:06.3f}"

    def _format_delta(minutes, ms):
        if minutes == 0 and ms == 0:
            return "0.000s"
        total = ms + minutes * 60000
        return f"{total/1000:.3f}s"

    offset = _HDR_SIZE
    laps = []
    for car_idx in range(22):
        last_lap = struct.unpack_from("<I", buf, offset)[0]; offset += 4
        current_lap = struct.unpack_from("<I", buf, offset)[0]; offset += 4
        sector1_ms = struct.unpack_from("<H", buf, offset)[0]; offset += 2
        sector1_min = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        sector2_ms = struct.unpack_from("<H", buf, offset)[0]; offset += 2
        sector2_min = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        delta_front_ms = struct.unpack_from("<H", buf, offset)[0]; offset += 2
        delta_front_min = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        delta_leader_ms = struct.unpack_from("<H", buf, offset)[0]; offset += 2
        delta_leader_min = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        lap_distance = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        total_distance = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        safety_car_delta = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        car_position = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        current_lap_num = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        pit_status = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        num_pit_stops = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        sector = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        current_lap_invalid = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        penalties = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        total_warnings = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        corner_cutting_warnings = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        num_unserved_drive_through = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        num_unserved_stop_go = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        grid_position = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        driver_status = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        result_status = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        pit_lane_timer_active = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        pit_lane_time = struct.unpack_from("<H", buf, offset)[0]; offset += 2
        pit_stop_timer = struct.unpack_from("<H", buf, offset)[0]; offset += 2
        pit_stop_should_serve_pen = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        speed_trap_fastest_speed = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        speed_trap_fastest_lap = struct.unpack_from("<B", buf, offset)[0]; offset += 1

        laps.append({
            "carIndex": car_idx,
            "lastLapTimeInMS": last_lap,
            "lastLapTimeFormatted": _format_time(0, last_lap),
            "currentLapTimeInMS": current_lap,
            "currentLapTimeFormatted": _format_time(0, current_lap),
            "sector1TimeInMS": sector1_ms + sector1_min * 60000,
            "sector1TimeFormatted": _format_time(sector1_min, sector1_ms),
            "sector2TimeInMS": sector2_ms + sector2_min * 60000,
            "sector2TimeFormatted": _format_time(sector2_min, sector2_ms),
            "deltaToCarInFrontInMS": delta_front_ms + delta_front_min * 60000,
            "deltaToCarInFrontFormatted": _format_delta(delta_front_min, delta_front_ms),
            "deltaToRaceLeaderInMS": delta_leader_ms + delta_leader_min * 60000,
            "deltaToRaceLeaderFormatted": _format_delta(delta_leader_min, delta_leader_ms),
            "lapDistance": lap_distance,
            "totalDistance": total_distance,
            "totalDistanceKm": round(total_distance / 1000, 3),
            "safetyCarDelta": safety_car_delta,
            "carPosition": car_position,
            "currentLapNum": current_lap_num,
            "pitStatus": pit_status,
            "pitStatusName": PIT_STATUS.get(pit_status, f"Unknown ({pit_status})"),
            "numPitStops": num_pit_stops,
            "sector": sector,
            "sectorName": SECTORS.get(sector, f"Unknown ({sector})"),
            "currentLapInvalid": bool(current_lap_invalid),
            "penalties": penalties,
            "warnings": total_warnings,
            "cornerCuttingWarnings": corner_cutting_warnings,
            "numUnservedDriveThroughPens": num_unserved_drive_through,
            "numUnservedStopGoPens": num_unserved_stop_go,
            "gridPosition": grid_position,
            "driverStatus": driver_status,
            "driverStatusName": DRIVER_STATUS.get(driver_status, f"Unknown ({driver_status})"),
            "resultStatus": result_status,
            "resultStatusName": RESULT_STATUS.get(result_status, f"Unknown ({result_status})"),
            "pitLaneTimerActive": bool(pit_lane_timer_active),
            "pitLaneTimeInLaneInMS": pit_lane_time,
            "pitLaneTimeFormatted": f"{pit_lane_time / 1000:.3f}s" if pit_lane_time else "0.000s",
            "pitStopTimerInMS": pit_stop_timer,
            "pitStopTimeFormatted": f"{pit_stop_timer / 1000:.3f}s" if pit_stop_timer else "0.000s",
            "pitStopShouldServePen": bool(pit_stop_should_serve_pen),
            "speedTrapFastestSpeed": speed_trap_fastest_speed,
            "speedTrapFastestLap": speed_trap_fastest_lap if speed_trap_fastest_lap != 255 else None,
        })

    tt_pb = struct.unpack_from("<B", buf, offset)[0]; offset += 1
    tt_rival = struct.unpack_from("<B", buf, offset)[0]; offset += 1

    return {
        "laps": laps,
        "timeTrialPBIndex": tt_pb if tt_pb != 255 else None,
        "timeTrialRivalIndex": tt_rival if tt_rival != 255 else None,
    }
