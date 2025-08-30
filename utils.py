import struct

# ---------------- Helpers for arrays ----------------
def unpack(fmt: str, buf: memoryview, offset: int = 0):
    size = struct.calcsize(fmt)
    return struct.unpack_from(fmt, buf, offset), offset + size

def read_floats(buf: memoryview, offset: int, count: int):
    fmt = "<" + "f"*count
    vals = struct.unpack_from(fmt, buf, offset)
    return list(vals), offset + 4*count

def read_uint8_array(buf: memoryview, offset: int, count: int):
    fmt = "<" + "B"*count
    vals = struct.unpack_from(fmt, buf, offset)
    return list(vals), offset + count

def read_int8_array(buf: memoryview, offset: int, count: int):
    fmt = "<" + "b"*count
    vals = struct.unpack_from(fmt, buf, offset)
    return list(vals), offset + count

def read_uint16_array(buf: memoryview, offset: int, count: int):
    fmt = "<" + "H"*count
    vals = struct.unpack_from(fmt, buf, offset)
    return list(vals), offset + 2*count