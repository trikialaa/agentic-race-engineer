
import struct

_HDR_FMT = "<HBBBBQfIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)

def decode_car_status(buf: memoryview):
    offset = _HDR_SIZE
    cars = []
    for _ in range(22):
        tractionControl = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        antiLockBrakes = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        fuelMix = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        frontBrakeBias = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        pitLimiterStatus = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        fuelInTank = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        fuelCapacity = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        fuelRemainingLaps = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        maxRPM = struct.unpack_from("<H", buf, offset)[0]; offset += 2
        idleRPM = struct.unpack_from("<H", buf, offset)[0]; offset += 2
        maxGears = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        drsAllowed = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        drsActivationDistance = struct.unpack_from("<H", buf, offset)[0]; offset += 2
        actualTyreCompound = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        visualTyreCompound = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        tyresAgeLaps = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        vehicleFiaFlags = struct.unpack_from("<b", buf, offset)[0]; offset += 1
        ersStoreEnergy = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        ersDeployMode = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        ersHarvestedThisLapMGUK = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        ersHarvestedThisLapMGUH = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        ersDeployedThisLap = struct.unpack_from("<f", buf, offset)[0]; offset += 4
        networkPaused = struct.unpack_from("<B", buf, offset)[0]; offset += 1
        cars.append({
            "tractionControl": tractionControl, "antiLockBrakes": antiLockBrakes, "fuelMix": fuelMix,
            "frontBrakeBias": frontBrakeBias, "pitLimiterStatus": pitLimiterStatus,
            "fuelInTank": fuelInTank, "fuelCapacity": fuelCapacity, "fuelRemainingLaps": fuelRemainingLaps,
            "maxRPM": maxRPM, "idleRPM": idleRPM, "maxGears": maxGears, "drsAllowed": drsAllowed,
            "drsActivationDistance": drsActivationDistance, "actualTyreCompound": actualTyreCompound,
            "visualTyreCompound": visualTyreCompound, "tyresAgeLaps": tyresAgeLaps, "vehicleFiaFlags": vehicleFiaFlags,
            "ersStoreEnergy": ersStoreEnergy, "ersDeployMode": ersDeployMode,
            "ersHarvestedThisLapMGUK": ersHarvestedThisLapMGUK, "ersHarvestedThisLapMGUH": ersHarvestedThisLapMGUH,
            "ersDeployedThisLap": ersDeployedThisLap, "networkPaused": networkPaused
        })
    return {"carStatus": cars}