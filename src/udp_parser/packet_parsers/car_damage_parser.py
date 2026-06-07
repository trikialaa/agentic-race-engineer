import struct

_HDR_FMT = "<HBBBBBQfIIBB"
_HDR_SIZE = struct.calcsize(_HDR_FMT)


def decode_car_damage(buf: memoryview):
    offset = _HDR_SIZE
    cars = []
    for _ in range(22):
        tyresWear = list(struct.unpack_from("<ffff", buf, offset))
        offset += 16
        tyresDamage = list(struct.unpack_from("<BBBB", buf, offset))
        offset += 4
        brakesDamage = list(struct.unpack_from("<BBBB", buf, offset))
        offset += 4
        tyreBlisters = list(struct.unpack_from("<BBBB", buf, offset))
        offset += 4
        frontLeftWingDamage = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        frontRightWingDamage = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        rearWingDamage = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        floorDamage = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        diffuserDamage = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        sidepodDamage = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        drsFault = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        ersFault = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        gearBoxDamage = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        engineDamage = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        engineMGUHWear = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        engineESWear = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        engineCEWear = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        engineICEWear = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        engineMGUKWear = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        engineTCWear = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        engineBlown = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        engineSeized = struct.unpack_from("<B", buf, offset)[0]
        offset += 1
        cars.append(
            {
                "tyresWear": tyresWear,
                "tyresDamage": tyresDamage,
                "brakesDamage": brakesDamage,
                "tyreBlisters": tyreBlisters,
                "frontLeftWingDamage": frontLeftWingDamage,
                "frontRightWingDamage": frontRightWingDamage,
                "rearWingDamage": rearWingDamage,
                "floorDamage": floorDamage,
                "diffuserDamage": diffuserDamage,
                "sidepodDamage": sidepodDamage,
                "drsFault": drsFault,
                "ersFault": ersFault,
                "gearBoxDamage": gearBoxDamage,
                "engineDamage": engineDamage,
                "engineMGUHWear": engineMGUHWear,
                "engineESWear": engineESWear,
                "engineCEWear": engineCEWear,
                "engineICEWear": engineICEWear,
                "engineMGUKWear": engineMGUKWear,
                "engineTCWear": engineTCWear,
                "engineBlown": engineBlown,
                "engineSeized": engineSeized,
            }
        )
    return {"carDamage": cars}
