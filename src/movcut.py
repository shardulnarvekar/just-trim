"""Conservative, lossless, self-contained QuickTime sample copier.

No codec is decoded or encoded. Unknown sample-table layouts are rejected.
All source access is read-only; completed files are published only after verification.
"""
from __future__ import annotations
import bisect
import hashlib
import math
import os
from pathlib import Path
import shutil
import struct
import uuid
from dataclasses import dataclass, field
from fractions import Fraction


class MovieError(Exception):
    pass


class Cancelled(MovieError):
    pass


def u32(b, p=0):
    return struct.unpack_from('>I', b, p)[0]


def box(kind, data):
    return struct.pack('>I4s', len(data) + 8, kind) + data


@dataclass
class Atom:
    kind: bytes
    data: bytes

    def encode(self):
        return box(self.kind, self.data)


def atoms(data):
    result = []
    p = 0
    while p < len(data):
        if p + 8 > len(data):
            raise MovieError('Incomplete MOV atom header.')
        n, kind = struct.unpack_from('>I4s', data, p)
        h = 8
        if n == 1:
            if p + 16 > len(data):
                raise MovieError('Incomplete extended MOV header.')
            n = struct.unpack_from('>Q', data, p + 8)[0]
            h = 16
        if n == 0:
            n = len(data) - p
        if n < h or p + n > len(data):
            raise MovieError('Invalid MOV atom size.')
        result.append(Atom(kind, data[p+h:p+n]))
        p += n
    return result


def one(items, kind):
    found = [a for a in items if a.kind == kind]
    if len(found) != 1:
        raise MovieError(f'Expected one {kind.decode()} atom; this MOV layout is unsupported.')
    return found[0]


def rebuild(items, replacements):
    out = []
    for a in items:
        v = replacements.get(a.kind, a.encode())
        if v is not None:
            out.append(v)
    return b''.join(out)


def runs(values):
    result = []
    for v in values:
        if result and result[-1][1] == v:
            result[-1] = (result[-1][0] + 1, v)
        else:
            result.append((1, v))
    return result


def expand(data, offset=8, signed=False, maximum=5_000_000):
    n = u32(data, offset - 4)
    if len(data) != offset + n * 8:
        raise MovieError('Invalid run-length sample table.')
    out = []
    for count, value in struct.iter_unpack('>Ii' if signed else '>II', data[offset:]):
        if count == 0 or len(out) + count > maximum:
            raise MovieError('Oversized or invalid sample table.')
        out.extend([value] * count)
    return out


def runbox(kind, values, prefix=b'\0\0\0\0', signed=False):
    entries = runs(values)
    return box(kind, prefix + struct.pack('>I', len(entries)) +
               b''.join(struct.pack('>Ii' if signed else '>II', *x) for x in entries))


def header_time(data):
    if data[0] not in (0, 1):
        raise MovieError('Unsupported time-header version.')
    p = 20 if data[0] else 12
    return u32(data, p), struct.unpack_from('>Q' if data[0] else '>I', data, p+4)[0]


def duration_box(a, duration):
    d = bytearray(a.data)
    p = (28 if d[0] else 20) if a.kind == b'tkhd' else (24 if d[0] else 16)
    fmt = '>Q' if d[0] else '>I'
    if duration < 0 or (not d[0] and duration > 0xffffffff):
        raise MovieError('Duration exceeds the supported MOV header range.')
    struct.pack_into(fmt, d, p, duration)
    # Reset movie preview/selection/current-time fields, not creation metadata.
    if a.kind == b'mvhd':
        base = 92 if d[0] else 80
        d[base:base+16] = bytes(16)
    return box(a.kind, d)


@dataclass
class Chunk:
    offset: int
    first: int
    count: int
    description: int


class Track:
    def __init__(self, atom, movie_scale, media_ranges):
        self.atom = atom
        self.children = atoms(atom.data)
        self.tkhd = one(self.children, b'tkhd')
        self.id = u32(self.tkhd.data, 20 if self.tkhd.data[0] else 12)
        self.mdia = atoms(one(self.children, b'mdia').data)
        self.mdhd = one(self.mdia, b'mdhd')
        self.scale, _ = header_time(self.mdhd.data)
        if not self.scale:
            raise MovieError('Invalid media timescale.')
        self.handler = one(self.mdia, b'hdlr').data[8:12]
        self.minf = atoms(one(self.mdia, b'minf').data)
        self.stbl = atoms(one(self.minf, b'stbl').data)
        supported = {b'stsd', b'stts', b'ctts', b'stss', b'stps', b'stsh', b'stsc',
                     b'stsz', b'stco', b'co64', b'sdtp', b'sgpd', b'sbgp', b'csgm',
                     b'free', b'wide'}
        unsupported = {a.kind for a in self.stbl} - supported
        if unsupported or any(a.kind == b'stsh' for a in self.stbl):
            raise MovieError(f'Track {self.id} uses an unsupported sample table: '
                             + ', '.join(x.decode('latin1') for x in unsupported or {b'stsh'})
                             + '. No tracks will be discarded.')
        self.stsd = one(self.stbl, b'stsd')
        descriptions = atoms(self.stsd.data[8:])
        if len(descriptions) != u32(self.stsd.data, 4):
            raise MovieError('Invalid sample descriptions.')
        self.codec = descriptions[0].kind.decode('latin1') if descriptions else '?'
        if self.codec in ('encv', 'enca'):
            raise MovieError('Encrypted video is not supported.')
        for d in descriptions:
            if len(d.data) < 8 or struct.unpack_from('>H', d.data, 6)[0] != 1:
                raise MovieError('External media references are not supported.')
        dinf = atoms(one(self.minf, b'dinf').data)
        dref = one(dinf, b'dref').data
        refs = atoms(dref[8:])
        if len(refs) != 1 or not (u32(refs[0].data) & 1):
            raise MovieError('This MOV references media outside the file.')
        sz = one(self.stbl, b'stsz').data
        fixed, self.count = struct.unpack_from('>II', sz, 4)
        if self.count == 0 or self.count > 5_000_000:
            raise MovieError('Empty, fragmented, or excessively large sample index is unsupported.')
        if (fixed and len(sz) != 12) or (not fixed and len(sz) != 12 + self.count*4):
            raise MovieError('Invalid sample-size table.')
        self.sizes = [fixed]*self.count if fixed else list(struct.unpack('>'+str(self.count)+'I', sz[12:]))
        self.durations = expand(one(self.stbl, b'stts').data)
        if len(self.durations) != self.count or any(x <= 0 for x in self.durations):
            raise MovieError('Invalid sample durations.')
        self.dts = [0]
        for d in self.durations:
            self.dts.append(self.dts[-1] + d)
        ctts = [a for a in self.stbl if a.kind == b'ctts']
        self.ctts = expand(ctts[0].data, signed=ctts[0].data[0] == 1) if ctts else [0]*self.count
        if len(self.ctts) != self.count:
            raise MovieError('Invalid composition-time table.')
        sync = [a for a in self.stbl if a.kind == b'stss']
        self.sync = [x[0]-1 for x in struct.iter_unpack('>I', sync[0].data[8:])] if sync else list(range(self.count))
        if not self.sync or self.sync != sorted(set(self.sync)) or self.sync[0] < 0 or self.sync[-1] >= self.count:
            raise MovieError('Invalid sync sample table.')
        self.media_start = 0
        self.delay = Fraction(0)
        edts = [a for a in self.children if a.kind == b'edts']
        if edts:
            e = one(atoms(edts[0].data), b'elst').data
            if e[0] not in (0, 1):
                raise MovieError('Unsupported edit-list version.')
            fmt = '>Qqhh' if e[0] else '>Iihh'
            edits = list(struct.iter_unpack(fmt, e[8:]))
            if len(edits) != u32(e, 4):
                raise MovieError('Invalid edit list.')
            if edits and edits[0][1] == -1:
                self.delay = Fraction(edits.pop(0)[0], movie_scale)
            if len(edits) != 1 or edits[0][1] < 0 or edits[0][2:] != (1, 0):
                raise MovieError('Slow-motion or multi-edit MOVs need a different workflow; this app will not flatten them.')
            self.media_start = edits[0][1]
        self.shift = self.delay - Fraction(self.media_start, self.scale)
        co = [a for a in self.stbl if a.kind in (b'stco', b'co64')]
        if len(co) != 1:
            raise MovieError('Invalid chunk offset table.')
        offsets = [v[0] for v in struct.iter_unpack('>Q' if co[0].kind == b'co64' else '>I', co[0].data[8:])]
        if len(offsets) != u32(co[0].data, 4):
            raise MovieError('Invalid chunk count.')
        sc = one(self.stbl, b'stsc').data
        entries = list(struct.iter_unpack('>III', sc[8:]))
        if not entries or len(entries) != u32(sc, 4) or entries[0][0] != 1:
            raise MovieError('Invalid sample-to-chunk table.')
        self.chunks = []
        sample = j = 0
        for i, offset in enumerate(offsets, 1):
            while j+1 < len(entries) and entries[j+1][0] <= i:
                j += 1
            _, n, desc = entries[j]
            if not n or sample+n > self.count or desc < 1 or desc > len(descriptions):
                raise MovieError('Invalid chunk sample range.')
            length = sum(self.sizes[sample:sample+n])
            if not any(a <= offset and offset+length <= b for a, b in media_ranges):
                raise MovieError('A sample points outside the movie data.')
            self.chunks.append(Chunk(offset, sample, n, desc))
            sample += n
        if sample != self.count:
            raise MovieError('Chunk table and sample count disagree.')

    def time(self, index):
        return Fraction(self.dts[index] + self.ctts[index], self.scale) + self.shift


@dataclass
class Segment:
    track: Track
    first: int
    stop: int
    media_time: int
    empty_duration: int
    movie_duration: int
    chunks: list = field(default_factory=list)


def compact_slice(a, first, stop, count):
    """Preserve Apple's compact group patterns exactly, only at whole-pattern boundaries.

    No interpretation of proprietary group descriptions or partial patterns.
    """
    d = a.data
    if len(d) < 20 or d[:4] != bytes(4) or u32(d, 8) != 0:
        raise MovieError('Unsupported Apple compact sample grouping.')
    bits, n = u32(d, 12), u32(d, 16)
    if bits not in (4, 8, 16, 32) or len(d) < 20+n*8:
        raise MovieError('Unsupported compact grouping width.')
    pairs = list(struct.iter_unpack('>II', d[20:20+n*8]))
    if sum(c for _, c in pairs) != count:
        raise MovieError('Compact grouping does not cover the track.')
    total_indices = sum(p for p, _ in pairs)
    tail = d[20+n*8:]
    if len(tail) != (total_indices*bits+7)//8:
        raise MovieError('Invalid compact grouping payload.')
    sample = index = 0
    selected = []
    index_first = index_stop = None
    for pattern, samples in pairs:
        if first <= sample and sample+samples <= stop:
            if index_first is None:
                index_first = index
            selected.append((pattern, samples))
            index_stop = index+pattern
        elif sample < stop and sample+samples > first:
            raise MovieError('This cut crosses an Apple compact-group boundary. Choose another keyframe.')
        sample += samples
        index += pattern
    if not selected:
        raise MovieError('Empty Apple sample group.')
    # Bit slicing also handles odd nibble boundaries without changing pattern values.
    values = []
    for i in range(index_first, index_stop):
        bit = i*bits
        if bits == 4:
            values.append((tail[bit//8] >> (4 if bit%8 == 0 else 0)) & 15)
        else:
            values.append(int.from_bytes(tail[bit//8:bit//8+bits//8], 'big'))
    if bits == 4:
        packed = bytes((values[i] << 4) | (values[i+1] if i+1 < len(values) else 0) for i in range(0, len(values), 2))
    else:
        packed = b''.join(v.to_bytes(bits//8, 'big') for v in values)
    return box(a.kind, d[:16] + struct.pack('>I', len(selected)) +
               b''.join(struct.pack('>II', *p) for p in selected) + packed)


class Movie:
    def __init__(self, path):
        self.path = Path(path).resolve()
        stat = self.path.stat()
        self.identity = (stat.st_size, stat.st_mtime_ns)
        self.top = []
        self.media_ranges = []
        with self.path.open('rb') as f:
            p = 0
            while p < stat.st_size:
                f.seek(p)
                raw = f.read(8)
                if len(raw) != 8:
                    raise MovieError('Truncated MOV file.')
                size, kind = struct.unpack('>I4s', raw)
                h = 8
                if size == 1:
                    size = struct.unpack('>Q', f.read(8))[0]
                    h = 16
                if size == 0:
                    size = stat.st_size-p
                if size < h or p+size > stat.st_size:
                    raise MovieError('Invalid MOV file size.')
                if kind == b'mdat':
                    self.media_ranges.append((p+h, p+size))
                elif kind not in (b'free', b'wide', b'skip'):
                    if kind not in (b'ftyp', b'moov'):
                        raise MovieError(f'Unsupported top-level atom {kind!r}; no data will be dropped.')
                    if size > 128*1024*1024:
                        raise MovieError('Movie index is too large.')
                    self.top.append(Atom(kind, f.read(size-h)))
                p += size
        self.moov = atoms(one(self.top, b'moov').data)
        if any(a.kind in (b'mvex', b'cmov') for a in self.moov):
            raise MovieError('Fragmented or compressed movie indexes are unsupported.')
        self.mvhd = one(self.moov, b'mvhd')
        self.scale, ticks = header_time(self.mvhd.data)
        if not self.scale:
            raise MovieError('Invalid movie timescale.')
        self.duration = Fraction(ticks, self.scale)
        self.tracks = [Track(a, self.scale, self.media_ranges) for a in self.moov if a.kind == b'trak']
        videos = [t for t in self.tracks if t.handler == b'vide']
        if len(videos) != 1:
            raise MovieError('This version supports one video track per MOV. Multi-view video is not supported.')
        self.video = videos[0]
        self.keys = [(self.video.time(i), i) for i in self.video.sync
                     if 0 <= self.video.time(i) < self.duration]
        if not self.keys or self.keys != sorted(self.keys):
            raise MovieError('Unsupported video keyframe timeline.')
        self.key_times = [float(t) for t, _ in self.keys]
        self.boundaries = self.key_times + [float(self.duration)]

    def snap(self, start, end):
        if not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end <= float(self.duration)+0.002:
            raise MovieError('Choose an end time after the start, within this video.')
        # Time fields and Qt seek positions have millisecond precision.
        # Re-entering a displayed keyframe must not jump a whole GOP.
        a = max(0, bisect.bisect_right(self.key_times, start+0.000501)-1)
        b = min(len(self.keys), bisect.bisect_left(self.boundaries, end-0.000501))
        if b <= a:
            b = a+1
        return self.keys[a][0], self.keys[b][0] if b < len(self.keys) else self.duration

    def plan(self, start, end):
        start, end = self.snap(float(start), float(end))
        duration = round((end-start)*self.scale)
        segments = []
        for t in self.tracks:
            target = (start-t.shift)*t.scale
            target_end = (end-t.shift)*t.scale
            if t is self.video:
                first = next(i for time, i in self.keys if time == start)
                stop = next((i for time, i in self.keys if time == end), t.count)
            else:
                first = max(0, min(t.count-1, bisect.bisect_right(t.dts, target)-1))
                stop = min(t.count, bisect.bisect_left(t.dts, target_end))
                # Preserve codec pre-roll, including APAC's indexed random access points.
                if t.handler == b'soun':
                    first = max(0, first-2)
                    first = t.sync[max(0, bisect.bisect_right(t.sync, first)-1)]
            if stop <= first or target_end <= 0 or target >= t.dts[-1]:
                raise MovieError(f'Track {t.id} has no media in this range. Export stopped to avoid dropping a track.')
            delay = max(Fraction(0), t.shift-start)
            empty = round(delay*self.scale)
            media_time = max(0, round(target-t.dts[first]))
            seg = Segment(t, first, stop, media_time, empty, duration)
            for c in t.chunks:
                lo, hi = max(c.first, first), min(c.first+c.count, stop)
                if lo < hi:
                    offset = c.offset + sum(t.sizes[c.first:lo])
                    length = sum(t.sizes[lo:hi])
                    seg.chunks.append([offset, length, hi-lo, c.description, 0])
            # Validate all dependent metadata before creating any file.
            self.track_bytes(seg)
            segments.append(seg)
        return start, end, segments

    def track_bytes(self, seg):
        t, lo, hi = seg.track, seg.first, seg.stop
        tables = []
        for a in t.stbl:
            k, d = a.kind, a.data
            if k == b'stts':
                v = runbox(k, t.durations[lo:hi])
            elif k == b'ctts':
                v = runbox(k, t.ctts[lo:hi], d[:4], d[0] == 1)
            elif k in (b'stss', b'stps'):
                indices = [x[0] for x in struct.iter_unpack('>I', d[8:])]
                indices = [i-lo for i in indices if lo < i <= hi]
                v = box(k, d[:4]+struct.pack('>I', len(indices))+b''.join(struct.pack('>I', i) for i in indices))
            elif k == b'stsz':
                sizes = t.sizes[lo:hi]
                fixed = sizes[0] if len(set(sizes)) == 1 and sizes[0] else 0
                v = box(k, bytes(4)+struct.pack('>II', fixed, len(sizes)) +
                        (b'' if fixed else b''.join(struct.pack('>I', i) for i in sizes)))
            elif k == b'stsc':
                entries = []
                for i, c in enumerate(seg.chunks, 1):
                    if not entries or entries[-1][1:] != (c[2], c[3]):
                        entries.append((i, c[2], c[3]))
                v = box(k, bytes(4)+struct.pack('>I', len(entries))+b''.join(struct.pack('>III', *x) for x in entries))
            elif k in (b'stco', b'co64'):
                v = box(b'co64', bytes(4)+struct.pack('>I', len(seg.chunks))+
                        b''.join(struct.pack('>Q', c[4]) for c in seg.chunks))
            elif k == b'sdtp':
                if len(d) != t.count+4:
                    raise MovieError('Invalid sample dependency table.')
                v = box(k, d[:4]+d[4+lo:4+hi])
            elif k == b'sbgp':
                if d[0] not in (0, 1):
                    raise MovieError('Unsupported sample group version.')
                offset = 12 if d[0] == 0 else 16
                values = expand(d, offset)
                if len(values) != t.count:
                    raise MovieError('Sample group does not cover the track.')
                v = runbox(k, values[lo:hi], d[:offset-4])
            elif k == b'csgm':
                v = compact_slice(a, lo, hi, t.count)
            else:
                v = a.encode()
            tables.append(v)
        stbl = box(b'stbl', b''.join(tables))
        minf = box(b'minf', rebuild(t.minf, {b'stbl': stbl}))
        mdhd = duration_box(t.mdhd, t.dts[hi]-t.dts[lo])
        mdia = box(b'mdia', rebuild(t.mdia, {b'mdhd': mdhd, b'minf': minf}))
        entries = []
        if seg.empty_duration:
            entries.append((seg.empty_duration, -1, 1, 0))
        entries.append((seg.movie_duration-seg.empty_duration, seg.media_time, 1, 0))
        elst = box(b'elst', b'\x01\0\0\0'+struct.pack('>I', len(entries))+
                   b''.join(struct.pack('>Qqhh', *e) for e in entries))
        edts = box(b'edts', elst)
        replaced = rebuild(t.children, {b'mdia': mdia, b'tkhd': duration_box(t.tkhd, seg.movie_duration), b'edts': edts})
        if not any(a.kind == b'edts' for a in t.children):
            replaced += edts
        return box(b'trak', replaced)

    def export(self, start, end, destination, progress=lambda p, s: None, cancelled=lambda: False):
        destination = Path(destination).resolve()
        if destination == self.path or destination.exists():
            raise MovieError('Output already exists. Choose a new filename; files are never overwritten.')
        if destination.suffix.lower() != '.mov':
            raise MovieError('Output must use the .mov extension.')
        def check():
            if cancelled():
                raise Cancelled('Export cancelled; the original is unchanged.')
        check()
        st = self.path.stat()
        if (st.st_size, st.st_mtime_ns) != self.identity:
            raise MovieError('The source changed after opening. Reopen it before exporting.')
        start, end, segments = self.plan(start, end)
        length = sum(c[1] for s in segments for c in s.chunks)
        if shutil.disk_usage(destination.parent).free < length + 32*1024*1024:
            raise MovieError('Not enough free space in the output folder.')
        ftyp = next((a.encode() for a in self.top if a.kind == b'ftyp'), box(b'ftyp', b'qt  '+bytes(4)+b'qt  '))
        def movie_bytes():
            it = iter(segments)
            data = []
            for a in self.moov:
                if a.kind == b'mvhd':
                    data.append(duration_box(a, round((end-start)*self.scale)))
                elif a.kind == b'trak':
                    data.append(self.track_bytes(next(it)))
                else:
                    data.append(a.encode())
            return box(b'moov', b''.join(data))
        moov = movie_bytes()
        pos = len(ftyp)+len(moov)+16
        ordered = sorted((c for s in segments for c in s.chunks), key=lambda c:c[0])
        for c in ordered:
            c[4] = pos
            pos += c[1]
        moov2 = movie_bytes()
        if len(moov2) != len(moov):
            raise MovieError('Internal chunk-offset error.')
        temporary = destination.with_name('.'+destination.stem+'.'+uuid.uuid4().hex+'.partial')
        digests = []
        done = 0
        try:
            with self.path.open('rb') as source, temporary.open('xb') as out:
                out.write(ftyp)
                out.write(moov2)
                out.write(struct.pack('>I4sQ', 1, b'mdat', length+16))
                for c in ordered:
                    check()
                    source.seek(c[0])
                    remaining = c[1]
                    digest = hashlib.sha256()
                    while remaining:
                        check()
                        b = source.read(min(4*1024*1024, remaining))
                        if not b:
                            raise MovieError('Source became unreadable during copying.')
                        out.write(b)
                        digest.update(b)
                        remaining -= len(b)
                    digests.append(digest.digest())
                    done += c[1]
                    progress(int(done/max(1,length)*75), 'Copying original samples')
                out.flush()
                os.fsync(out.fileno())
            # Verify the bytes actually written, including every metadata/audio track.
            done = 0
            with temporary.open('rb') as out:
                for c, expected in zip(ordered, digests):
                    check()
                    out.seek(c[4])
                    remaining = c[1]
                    digest = hashlib.sha256()
                    while remaining:
                        check()
                        b = out.read(min(4*1024*1024, remaining))
                        if not b:
                            raise MovieError('Incomplete output file.')
                        digest.update(b)
                        remaining -= len(b)
                    if digest.digest() != expected:
                        raise MovieError('Output verification failed. The incomplete file was removed.')
                    done += c[1]
                    progress(75+int(done/max(1,length)*24), 'Verifying copied bytes')
            verified = Movie(temporary)
            if len(verified.tracks) != len(self.tracks):
                raise MovieError('Track count verification failed.')
            for s, t in zip(segments, verified.tracks):
                if t.stsd.data != s.track.stsd.data or t.count != s.stop-s.first:
                    raise MovieError('Track description verification failed.')
            check()
            st = self.path.stat()
            if (st.st_size, st.st_mtime_ns) != self.identity:
                raise MovieError('The source changed during export.')
            # Windows rename fails if destination exists; never replace an existing clip.
            if os.name == 'nt':
                os.rename(temporary, destination)
            else:
                os.link(temporary, destination)
                temporary.unlink()
            progress(100, 'Verified')
            return {'path': str(destination), 'start': float(start), 'end': float(end),
                    'tracks': len(segments), 'bytes': destination.stat().st_size,
                    'verified': True}
        finally:
            if temporary.exists():
                temporary.unlink()


def format_time(seconds):
    ms = max(0, round(float(seconds)*1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f'{h:02}:{m:02}:{s:02}.{ms:03}'


def parse_time(text):
    try:
        parts = text.strip().split(':')
        if not 1 <= len(parts) <= 3:
            raise ValueError
        nums = [float(x) for x in parts]
        if any(not math.isfinite(x) or x < 0 for x in nums) or any(x >= 60 for x in nums[1:]):
            raise ValueError
        result = 0
        for n in nums:
            result = result*60+n
        return result
    except ValueError:
        raise MovieError('Enter a time as HH:MM:SS.mmm, MM:SS, or seconds.') from None
