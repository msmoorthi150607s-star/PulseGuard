#!/usr/bin/env python3
"""
PulseGuard - fetch verbatim excerpts of the two selected external datasets.

Both source archives are multi-GB remote ZIP files hosted on Mendeley Data
(CC BY 4.0). Downloading them whole is impractical for a college project
repository, so this script uses HTTP Range requests to read the ZIP central
directory remotely, then fetches a *compressed prefix* of selected members
and raw-inflates it. The result is a byte-verbatim, contiguous excerpt of the
original member, cut ONLY at a record boundary (no invented data).

What is fetched
---------------
1. KAIST "Ball Bearing Vibration, and Temperature Run-to-Failure Dataset"
   (Mendeley 10.17632/5hcdd3tdvb.6) - 4 hourly CSV logs:
     first 2, last 2 of the 128-hour run (healthy start -> failure end).

2. ZTMF "Vibration, Acoustic, Temperature, and Motor Current Dataset of
   Rotating Machine Under Varying Load Conditions for Fault Diagnosis"
   (Mendeley 10.17632/ztmf3m7h5x.2):
     vibration: 0Nm_Normal.mat + 0Nm_Unbalance_0583mg.mat (raw .mat prefix)
     temp+current: 0Nm_Normal.tdms + 0Nm_Unbalance_0583mg.tdms (raw .tdms prefix)

The excerpts are saved EXACTLY as downloaded/inflated into raw/ - they are
source bytes, never edited. Excel/metadata steps are separate scripts.

Re-running this script re-downloads and overwrites only the raw excerpts.

Usage:  python fetch_external_datasets.py
"""
import struct
import subprocess
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).parent

KAIST_URL = ("https://data.mendeley.com/public-files/datasets/5hcdd3tdvb/"
             "files/0a5cea77-da64-4658-8062-c33f4f68a5e2/file_downloaded")
KAIST_SIZE = 4325053806

ZTMF_BASE = "https://data.mendeley.com/public-files/datasets/ztmf3m7h5x/files"
ZTMF_VIB = f"{ZTMF_BASE}/ee98c5d9-1052-4448-84b2-ed57711b658d/file_downloaded"
ZTMF_VIB_SIZE = 2659778162
ZTMF_TEMP = f"{ZTMF_BASE}/4fe7c7e8-9a77-4bef-b359-d762b6a3a044/file_downloaded"
ZTMF_TEMP_SIZE = 1547790068


def curl_range(url: str, start: int, end: int) -> bytes:
    r = subprocess.run(
        ["curl", "-sL", "--max-time", "300", "-r", f"{start}-{end}", url],
        capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"curl failed rc={r.returncode} for {start}-{end}")
    return r.stdout


def remote_cd(url: str, size: int) -> bytes:
    """Read the remote zip central directory via range requests."""
    tail = curl_range(url, max(0, size - 65536), size - 1)
    e = tail.rfind(b"PK\x05\x06")
    if e < 0:
        raise RuntimeError("EOCD not found")
    _, _, z64_off, _ = struct.unpack("<IIQI", tail[e - 20:e])
    z = tail[z64_off - (size - len(tail)): z64_off - (size - len(tail)) + 56]
    cd_size = struct.unpack("<Q", z[40:48])[0]
    cd_off = struct.unpack("<Q", z[48:56])[0]
    return curl_range(url, cd_off, cd_off + cd_size - 1)


def iter_members(cd: bytes):
    i = 0
    while i < len(cd) and cd[i:i + 4] == b"PK\x01\x02":
        method = struct.unpack("<H", cd[i + 10:i + 12])[0]
        csize = struct.unpack("<I", cd[i + 20:i + 24])[0]
        usize = struct.unpack("<I", cd[i + 24:i + 28])[0]
        nlen = struct.unpack("<H", cd[i + 28:i + 30])[0]
        elen = struct.unpack("<H", cd[i + 30:i + 32])[0]
        clen = struct.unpack("<H", cd[i + 32:i + 34])[0]
        lho = struct.unpack("<I", cd[i + 42:i + 46])[0]
        name = cd[i + 46:i + 46 + nlen].decode("utf-8", "replace")
        ex = cd[i + 46 + nlen: i + 46 + nlen + elen]
        j = 0
        need = []
        if usize == 0xFFFFFFFF:
            need.append("u")
        if csize == 0xFFFFFFFF:
            need.append("c")
        if lho == 0xFFFFFFFF:
            need.append("l")
        while j + 4 <= len(ex):
            hid, hsz = struct.unpack("<HH", ex[j:j + 4])
            if hid == 0x0001:
                k = j + 4
                for tag in need:
                    if tag == "u":
                        usize = struct.unpack("<Q", ex[k:k + 8])[0]; k += 8
                    elif tag == "c":
                        csize = struct.unpack("<Q", ex[k:k + 8])[0]; k += 8
                    elif tag == "l":
                        lho = struct.unpack("<Q", ex[k:k + 8])[0]; k += 8
                break
            j += 4 + hsz
        yield name, method, csize, usize, lho
        i += 46 + nlen + elen + clen


def member_header(url: str, lho: int):
    hdr = curl_range(url, lho, lho + 29)
    if hdr[:4] != b"PK\x03\x04":
        raise RuntimeError(f"bad local header at {lho}: {hdr[:8]!r}")
    nlen = struct.unpack("<H", hdr[26:28])[0]
    elen = struct.unpack("<H", hdr[28:30])[0]
    return hdr[30:30 + nlen].decode("utf-8", "replace"), lho + 30 + nlen + elen


def fetch_member_prefix(url: str, lho: int, want_bytes: int) -> bytes:
    """Raw-inflate a compressed prefix; returns verbatim decompressed prefix.

    The returned bytes are a byte-exact prefix of the original member
    (ZIP members are raw-deflate compressed, so inflating a prefix of the
    compressed stream yields the corresponding prefix of the file).
    """
    _, data_start = member_header(url, lho)
    n_fetch = min(int(want_bytes * 0.7) + 64_000, 12_000_000)  # compressed needed
    blob = curl_range(url, data_start, data_start + n_fetch - 1)
    d = zlib.decompressobj(-15)
    out = d.decompress(blob, want_bytes)
    return out


def cut_at_boundary(buf: bytes, delimiter: bytes = b"\n") -> bytes:
    """Trim to the last complete record so the excerpt ends at a boundary."""
    i = buf.rfind(delimiter)
    return buf[:i + 1] if i >= 0 else buf


def save(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(f"  saved {path.name}: {len(data):,} bytes")


def main():
    kaist_dir = HERE / "kaist" / "raw"
    kaist_raw = kaist_dir / "Vibration_Bearing_RuntoFailure.zip"
    kaist_raw.mkdir(parents=True, exist_ok=True)
    (kaist_raw / "README_source_archive.txt").write_text(
        "The complete original archive (4.3 GB, 129 hourly CSVs) is hosted at:\n"
        f"{KAIST_URL}\n"
        "DOI: 10.17632/5hcdd3tdvb.6  (CC BY 4.0)\n\n"
        "This folder contains only byte-verbatim excerpts of selected members,\n"
        "extracted without modification via HTTP range requests.\n",
        encoding="utf-8")

    print("== KAIST: scanning remote central directory ==")
    cd = remote_cd(KAIST_URL, KAIST_SIZE)
    members = {name: (lho, usize) for name, m, cs, usize, lho in iter_members(cd)
               if name.endswith(".csv")}
    names = sorted(members)
    print(f"  {len(names)} CSV members; first={names[0]}, last={names[-1]}")
    picks = ["LogFile_2022-06-20-17-00-31.csv",
             "LogFile_2022-06-20-18-00-31.csv",
             "LogFile_2022-06-25-23-00-31.csv",
             "LogFile_2022-06-26-00-00-31.csv"]
    # The final member filename may shift by a minute; fall back gracefully.
    if picks[2] not in members:
        picks[2] = names[-2]
    if picks[3] not in members:
        picks[3] = names[-1]
    want = 2_000_000  # ~2 MB verbatim prefix per file (~13k rows @ ~150 B/row)
    for p in picks:
        lho, usize = members[p]
        print(f"  fetching {p} (member size {usize:,} B, excerpt {want:,} B)")
        buf = fetch_member_prefix(KAIST_URL, lho, want)
        buf = cut_at_boundary(buf)
        save(kaist_raw / p, buf)

    print("== ZTMF: vibration .mat excerpts ==")
    ztmf_vib_dir = HERE / "ztmf_rotating_machine" / "raw" / "vibration_mat"
    ztmf_vib_dir.mkdir(parents=True, exist_ok=True)
    cdv = remote_cd(ZTMF_VIB, ZTMF_VIB_SIZE)
    vib_members = {name: lho for name, m, cs, us, lho in iter_members(cdv)
                   if name.endswith(".mat")}
    for p in ["0Nm_Normal.mat", "0Nm_Unbalance_0583mg.mat"]:
        lho = vib_members[p]
        print(f"  fetching {p} (verbatim 3 MB member prefix)")
        buf = fetch_member_prefix(ZTMF_VIB, lho, 3_000_000)
        save(ztmf_vib_dir / p, buf)  # binary .mat: saved verbatim, no boundary cut

    print("== ZTMF: temperature/current .tdms excerpts ==")
    ztmf_t_dir = HERE / "ztmf_rotating_machine" / "raw" / "temp_current_tdms"
    ztmf_t_dir.mkdir(parents=True, exist_ok=True)
    cdt = remote_cd(ZTMF_TEMP, ZTMF_TEMP_SIZE)
    t_members = {name: lho for name, m, cs, us, lho in iter_members(cdt)
                 if name.endswith(".tdms")}
    for p in ["0Nm_Normal.tdms", "0Nm_Unbalance_0583mg.tdms"]:
        lho = t_members[p]
        print(f"  fetching {p} (verbatim 3 MB member prefix)")
        buf = fetch_member_prefix(ZTMF_TEMP, lho, 3_000_000)
        save(ztmf_t_dir / p, buf)  # binary .tdms: saved verbatim

    (HERE / "ztmf_rotating_machine" / "raw" / "README_source_archive.txt").write_text(
        "Complete original archives hosted at Mendeley Data, DOI: 10.17632/ztmf3m7h5x.2 (CC BY 4.0)\n"
        f"  vibration.zip ({ZTMF_VIB_SIZE:,} B): {ZTMF_VIB}\n"
        f"  current,temp.zip ({ZTMF_TEMP_SIZE:,} B): {ZTMF_TEMP}\n"
        "  acoustic.zip: present in source (excluded from PulseGuard; acoustic is NOT a PulseGuard feature)\n\n"
        "This folder contains only byte-verbatim excerpts of selected members.\n",
        encoding="utf-8")

    print("DONE - raw excerpts preserved verbatim.")


if __name__ == "__main__":
    sys.exit(main())
