import struct

_HDR_FMT = "<HBBBBBQfIIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)


def _parse_dataset(buf: memoryview, offset: int):
    values = struct.unpack_from("<BBIIIIIBBBBBB", buf, offset)
    (
        car_idx,
        team_id,
        lap_time,
        sector1,
        sector2,
        sector3,
        traction_control,
        gearbox_assist,
        anti_lock_brakes,
        equal_car_perf,
        custom_setup,
        valid,
    ) = values
    offset += struct.calcsize("<BBIIIIIBBBBBB")
    return {
        "carIndex": car_idx,
        "teamId": team_id,
        "lapTimeInMS": lap_time,
        "sector1TimeInMS": sector1,
        "sector2TimeInMS": sector2,
        "sector3TimeInMS": sector3,
        "tractionControl": traction_control,
        "gearboxAssist": gearbox_assist,
        "antiLockBrakes": anti_lock_brakes,
        "equalCarPerformance": equal_car_perf,
        "customSetup": bool(custom_setup),
        "valid": bool(valid),
    }, offset


def decode_time_trial(buf: memoryview):
    offset = _HDR_SIZE
    player, offset = _parse_dataset(buf, offset)
    personal_best, offset = _parse_dataset(buf, offset)
    rival, offset = _parse_dataset(buf, offset)
    return {
        "playerSessionBestDataSet": player,
        "personalBestDataSet": personal_best,
        "rivalDataSet": rival,
    }
