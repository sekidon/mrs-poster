import ctypes
import msvcrt

KERNEL32 = ctypes.windll.kernel32

def force_file_unlock(path):
    """Windows-specific forced file unlock"""
    try:
        handle = KERNEL32.CreateFileW(
            path,
            0x80100000,  # GENERIC_READ | GENERIC_WRITE
            0x00000001,   # FILE_SHARE_READ
            None,
            0x00000003,   # OPEN_EXISTING
            0x00000080,   # FILE_ATTRIBUTE_NORMAL
            None
        )
        if handle != -1:
            KERNEL32.CloseHandle(handle)
            return True
        return False
    except:
        return False