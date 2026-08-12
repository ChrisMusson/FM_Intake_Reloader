"""Cross-platform process memory helpers for Football Manager."""

import ctypes
import ctypes.util
import functools
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.platform import IS_WINDOWS

FM_EXE_PATH_FRAGMENT = "/Football Manager 2024/fm.exe"
SCAN_CHUNK_SIZE = 0x200000
SCAN_WORKER_COUNT = 4  # process_vm_readv saturates well before this; more threads only add contention


class IOVec(ctypes.Structure):
    _fields_ = [("iov_base", ctypes.c_void_p), ("iov_len", ctypes.c_size_t)]


class LinuxFmProcess:
    def __init__(self, pid):
        self.pid = pid
        libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        self._readv = libc.process_vm_readv
        self._readv.argtypes = [ctypes.c_int, ctypes.POINTER(IOVec), ctypes.c_ulong, ctypes.POINTER(IOVec), ctypes.c_ulong, ctypes.c_ulong]
        self._readv.restype = ctypes.c_ssize_t
        self.fm_text_start, self.fm_text_end = self._find_text_range()

    @classmethod
    def open(cls):
        return cls(_find_linux_fm_pid())

    def _find_text_range(self):
        regions = list(self.iter_memory_regions())
        marker_index = next(
            (index for index, (_, _, _, path) in enumerate(regions) if FM_EXE_PATH_FRAGMENT in path or path.endswith("/fm.exe")), None
        )
        if marker_index is None:
            raise RuntimeError("Could not find any fm.exe memory mappings")

        current_end = regions[marker_index][1]
        for start, end, perms, _ in regions[marker_index:]:
            if start > current_end:
                break
            current_end = max(current_end, end)
            if "x" in perms:
                return start, end

        raise RuntimeError("Could not find an executable fm.exe memory range")

    def iter_memory_regions(self):
        with Path(f"/proc/{self.pid}/maps").open() as fh:
            for line in fh:
                parts = line.split(maxsplit=5)
                start_s, end_s = parts[0].split("-")
                perms = parts[1]
                path = parts[5].strip() if len(parts) > 5 else ""
                yield int(start_s, 16), int(end_s, 16), perms, path

    def read_bytes(self, address, size):
        buffer = ctypes.create_string_buffer(size)
        local = IOVec(ctypes.cast(buffer, ctypes.c_void_p), size)
        remote = IOVec(ctypes.c_void_p(address), size)
        bytes_read = self._readv(self.pid, ctypes.byref(local), 1, ctypes.byref(remote), 1, 0)
        if bytes_read != size:
            err = ctypes.get_errno()
            raise OSError(err, f"process_vm_readv returned {bytes_read} bytes, expected {size}")
        return bytes(buffer.raw)

    def read_into(self, pointer, address, size):
        """Read straight into a caller-owned buffer and report success, rather than allocating a fresh one per call."""
        local = IOVec(pointer, size)
        remote = IOVec(ctypes.c_void_p(address), size)
        return self._readv(self.pid, ctypes.byref(local), 1, ctypes.byref(remote), 1, 0) == size


def _find_linux_fm_pid():
    for proc_dir in Path("/proc").iterdir():
        if not proc_dir.name.isdigit():
            continue
        try:
            text = (proc_dir / "maps").read_text()
        except Exception:
            continue
        if FM_EXE_PATH_FRAGMENT in text or text.rstrip().endswith("/fm.exe"):
            return int(proc_dir.name)
    raise RuntimeError("Could not find a live process with Football Manager's fm.exe mapped")


def open_fm_process():
    if IS_WINDOWS:
        import pymem

        return pymem.Pymem("fm.exe")
    return LinuxFmProcess.open()


def get_fm_base_address(process):
    if IS_WINDOWS:
        import pymem.process

        module = pymem.process.module_from_name(process.process_handle, "fm.exe")
        if module is None:
            raise RuntimeError("Could not find fm.exe in the target process module list")
        return int(module.lpBaseOfDll)

    for start, _end, _perms, path in process.iter_memory_regions():
        if FM_EXE_PATH_FRAGMENT in path or path.endswith("/fm.exe"):
            return start

    raise RuntimeError("Could not find a base mapping for fm.exe")


def get_fm_image_range(process):
    if IS_WINDOWS:
        import pymem.process

        module = pymem.process.module_from_name(process.process_handle, "fm.exe")
        if module is None:
            raise RuntimeError("Could not find fm.exe in the target process module list")

        base_address = int(module.lpBaseOfDll)
        image_size = int(module.SizeOfImage)
        return base_address, base_address + image_size

    return process.fm_text_start, process.fm_text_end


def read_uint(process, address, size=8):
    return int.from_bytes(process.read_bytes(address, size), byteorder="little")


def read_c_string(process, address, size):
    raw = process.read_bytes(address, size).split(b"\x00", 1)[0]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def read_pointer(process, address):
    pointer = read_uint(process, address)
    return pointer or None


def read_chained_value(process, base_address, pointer_offsets, final_offset, *, size):
    current = base_address
    for offset in pointer_offsets:
        current = read_pointer(process, current + offset)
        if current is None:
            return None
    return read_uint(process, current + final_offset, size)


def read_chained_string(process, base_address, pointer_offsets, final_offset, *, size):
    current = base_address
    for offset in pointer_offsets:
        current = read_pointer(process, current + offset)
        if current is None:
            return None
    return read_c_string(process, current + final_offset, size)


def follow_pointer_chain(process, base_address, *offsets):
    current = base_address
    for offset in offsets:
        current = read_uint(process, current + offset)
        if current == 0:
            return None
    return current


class _ScanBuffer:
    """A reusable read target. Searching it in place keeps a full-heap scan from copying every chunk twice."""

    def __init__(self, size):
        self.data = bytearray(size)
        self.pointer = ctypes.cast((ctypes.c_char * size).from_buffer(self.data), ctypes.c_void_p)


_scan_state = threading.local()


def _get_scan_buffer(size):
    buffer = getattr(_scan_state, "buffer", None)
    if buffer is None or len(buffer.data) < size:
        buffer = _scan_state.buffer = _ScanBuffer(size)
    return buffer


def _iter_scan_chunks(process, tail, *, chunk_size, writable, executable, private):
    """Split the matching regions into chunks, each carrying the tail bytes a match at its far edge still needs."""
    for start, end, perms, _path in process.iter_memory_regions():
        if "r" not in perms:
            continue
        if writable is not None and ("w" in perms) != writable:
            continue
        if executable is not None and ("x" in perms) != executable:
            continue
        if private is not None and (perms[3] == "p") != private:
            continue

        address = start
        while address < end:
            size = min(chunk_size, end - address)
            yield address, size, min(tail, end - address - size)
            address += size


def _scan_chunk(process, pattern, window, chunk):
    address, size, tail = chunk
    buffer = _get_scan_buffer(size + tail)
    if not process.read_into(buffer.pointer, address, size + tail):
        return ()

    data = buffer.data
    limit = size + tail
    matches = []
    index = data.find(pattern, 0, limit)
    while index != -1 and index < size:  # a match past `size` belongs to the next chunk, which reads it as its own
        if not window:
            matches.append(address + index)
        elif index + window <= limit:
            matches.append((address + index, bytes(data[index : index + window])))
        index = data.find(pattern, index + 1, limit)

    return matches


def iter_pattern_matches(
    process, pattern, *, window=0, writable=None, executable=None, private=None, chunk_size=SCAN_CHUNK_SIZE, workers=SCAN_WORKER_COUNT
):
    """Yield every address matching `pattern`, or `(address, bytes)` pairs when `window` bytes of context are wanted.

    Asking for a window saves a follow-up read per match: the bytes are already in the scan buffer.
    """
    if IS_WINDOWS:
        for address in process.pattern_scan_all(pattern, return_multiple=True):
            address = int(address)
            yield (address, process.read_bytes(address, window)) if window else address
        return

    tail = max(len(pattern), window) - 1
    chunks = list(_iter_scan_chunks(process, tail, chunk_size=chunk_size, writable=writable, executable=executable, private=private))
    scan_chunk = functools.partial(_scan_chunk, process, pattern, window)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        for matches in executor.map(scan_chunk, chunks):
            yield from matches
