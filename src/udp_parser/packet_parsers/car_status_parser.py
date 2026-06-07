import os
import struct
import sys

# Add parent directory to path to import constants
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from constants import (
    ANTI_LOCK_BRAKES,
    ERS_DEPLOYMENT_MODES,
    FLAG_COLORS,
    FUEL_MIX,
    MAX_ERS_ENERGY,
    TRACTION_CONTROL,
    TYRE_COMPOUNDS,
    VISUAL_TYRE_COMPOUNDS,
)

_HDR_FMT = "<HBBBBBQfIIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)


def decode_car_status(buf: memoryview):
    """
    Decode F1 25 car status packet with enhanced fuel, ERS, and tyre information.
    """
    offset = _HDR_SIZE
    cars = []

    for car_idx in range(22):
        tractionControl = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        antiLockBrakes = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        fuelMix = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        frontBrakeBias = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        pitLimiterStatus = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        fuelInTank = struct.unpack_from("<f", buf, offset)[0]
        offset += 4
        fuelCapacity = struct.unpack_from("<f", buf, offset)[0]
        offset += 4
        fuelRemainingLaps = struct.unpack_from("<f", buf, offset)[0]
        offset += 4
        maxRPM = struct.unpack_from("<H", buf, offset)[0]
        offset += 2
        idleRPM = struct.unpack_from("<H", buf, offset)[0]
        offset += 2
        maxGears = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        drsAllowed = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        drsActivationDistance = struct.unpack_from("<H", buf, offset)[0]
        offset += 2
        actualTyreCompound = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        visualTyreCompound = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        tyresAgeLaps = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        vehicleFiaFlags = struct.unpack_from("<b", buf, offset)[0]
        offset += 1
        enginePowerICE = struct.unpack_from("<f", buf, offset)[0]
        offset += 4
        enginePowerMGUK = struct.unpack_from("<f", buf, offset)[0]
        offset += 4
        ersStoreEnergy = struct.unpack_from("<f", buf, offset)[0]
        offset += 4
        ersDeployMode = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        ersHarvestedThisLapMGUK = struct.unpack_from("<f", buf, offset)[0]
        offset += 4
        ersHarvestedThisLapMGUH = struct.unpack_from("<f", buf, offset)[0]
        offset += 4
        ersDeployedThisLap = struct.unpack_from("<f", buf, offset)[0]
        offset += 4
        networkPaused = struct.unpack_from("<B", buf, offset)[0]
        offset += 1

        # Calculate fuel percentage
        fuel_percentage = (fuelInTank / fuelCapacity * 100) if fuelCapacity > 0 else 0

        # Calculate ERS percentage
        ers_percentage = (ersStoreEnergy / MAX_ERS_ENERGY * 100) if MAX_ERS_ENERGY > 0 else 0

        # DRS status
        drs_available = drsActivationDistance > 0

        car_data = {
            "carIndex": car_idx,
            "tractionControl": tractionControl,
            "tractionControlName": TRACTION_CONTROL.get(
                tractionControl, f"Unknown ({tractionControl})"
            ),
            "antiLockBrakes": antiLockBrakes,
            "antiLockBrakesName": ANTI_LOCK_BRAKES.get(
                antiLockBrakes, f"Unknown ({antiLockBrakes})"
            ),
            "fuelMix": fuelMix,
            "fuelMixName": FUEL_MIX.get(fuelMix, f"Unknown ({fuelMix})"),
            "frontBrakeBias": frontBrakeBias,
            "pitLimiterStatus": bool(pitLimiterStatus),
            # Fuel information
            "fuelInTank": fuelInTank,
            "fuelCapacity": fuelCapacity,
            "fuelPercentage": round(fuel_percentage, 1),
            "fuelRemainingLaps": fuelRemainingLaps,
            "fuelCritical": fuel_percentage < 10,
            "fuelLow": fuel_percentage < 25,
            # Engine information
            "maxRPM": maxRPM,
            "idleRPM": idleRPM,
            "maxGears": maxGears,
            # DRS information
            "drsAllowed": bool(drsAllowed),
            "drsActivationDistance": drsActivationDistance,
            "drsAvailable": drs_available,
            "drsStatus": "Available"
            if drs_available
            else ("Allowed" if drsAllowed else "Not allowed"),
            # Tyre information
            "actualTyreCompound": actualTyreCompound,
            "actualTyreCompoundName": TYRE_COMPOUNDS.get(
                actualTyreCompound, f"Unknown ({actualTyreCompound})"
            ),
            "visualTyreCompound": visualTyreCompound,
            "visualTyreCompoundName": VISUAL_TYRE_COMPOUNDS.get(
                visualTyreCompound, f"Unknown ({visualTyreCompound})"
            ),
            "tyresAgeLaps": tyresAgeLaps,
            # Flags and ERS
            "vehicleFiaFlags": vehicleFiaFlags,
            "flagColor": FLAG_COLORS.get(vehicleFiaFlags, f"Unknown ({vehicleFiaFlags})"),
            "enginePowerICE": enginePowerICE,
            "enginePowerMGUK": enginePowerMGUK,
            "ersStoreEnergy": ersStoreEnergy,
            "ersPercentage": round(ers_percentage, 1),
            "ersDeployMode": ersDeployMode,
            "ersDeployModeName": ERS_DEPLOYMENT_MODES.get(
                ersDeployMode, f"Unknown ({ersDeployMode})"
            ),
            "ersHarvestedThisLapMGUK": ersHarvestedThisLapMGUK,
            "ersHarvestedThisLapMGUH": ersHarvestedThisLapMGUH,
            "ersDeployedThisLap": ersDeployedThisLap,
            "networkPaused": bool(networkPaused),
            # Warning flags
            "hasYellowFlag": vehicleFiaFlags == 3,
            "hasRedFlag": vehicleFiaFlags == 4,
            "hasBlueFlag": vehicleFiaFlags == 2,
        }
        cars.append(car_data)

    return {"carStatus": cars}
