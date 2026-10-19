"""Regression fixtures use synthetic sample bytes; no private recordings required."""
import struct
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from movcut import Atom, Movie, MovieError, atoms, box, compact_slice, one, runbox


def compact(bits, patterns):
    indices = [v for pattern, count in patterns for v in pattern]
    if bits == 4:
        packed = bytes((indices[i] << 4) | (indices[i+1] if i+1 < len(indices) else 0)
                       for i in range(0, len(indices), 2))
    else:
        packed = b''.join(v.to_bytes(bits//8, 'big') for v in indices)
    return Atom(b'csgm', bytes(4) + b'test' + struct.pack('>III', 0, bits, len(patterns))
                + b''.join(struct.pack('>II', len(p), n) for p, n in patterns) + packed)


def decode_compact(a):
    bits, count = struct.unpack_from('>II', a.data, 12)
    pairs = list(struct.iter_unpack('>II', a.data[20:20+8*count]))
    payload = a.data[20+8*count:]
    if bits == 4:
        indices = [value for byte in payload for value in (byte >> 4, byte & 15)]
    else:
        indices = [int.from_bytes(payload[i:i+bits//8], 'big')
                   for i in range(0, len(payload), bits//8)]
    result = []
    for length, samples in pairs:
        pattern, indices = indices[:length], indices[length:]
        result += (pattern * ((samples+length-1)//length))[:samples]
    return result


def fixture(path, brand=b'qt  ', ctts_version=0, cslg_version=0):
    offsets = [0, 20, -10, -10, 0, 0] * 2
    ftyp = box(b'ftyp', brand + bytes(4) + brand)
    media = bytes(range(12))
    mvhd = bytearray(100)
    mdhd = bytearray(24)
    tkhd = bytearray(84)
    struct.pack_into('>II', mvhd, 12, 100, 120)
    struct.pack_into('>II', mdhd, 12, 100, 120)
    struct.pack_into('>I', tkhd, 12, 1)
    struct.pack_into('>I', tkhd, 20, 120)
    summary = box(b'cslg', bytes([cslg_version, 0, 0, 0]) +
                  struct.pack('>5q' if cslg_version else '>5i', 10, -10, 20, 0, 120))
    stbl = box(b'stbl', b''.join([
        box(b'stsd', bytes(4)+struct.pack('>I', 1)+box(b'hvc1', bytes(6)+b'\0\1')),
        runbox(b'stts', [10]*12),
        runbox(b'ctts', offsets, bytes([ctts_version, 0, 0, 0]), signed=True),
        summary,
        box(b'stss', struct.pack('>IIII', 0, 2, 1, 7)),
        box(b'stsz', struct.pack('>III', 0, 1, 12)),
        box(b'stsc', struct.pack('>IIIII', 0, 1, 1, 12, 1)),
        box(b'stco', struct.pack('>III', 0, 1, len(ftyp)+8)),
        compact(4, [([1, 2, 3, 4], 12)]).encode(),
    ]))
    dref = box(b'dref', struct.pack('>II', 0, 1)+box(b'url ', b'\0\0\0\1'))
    minf = box(b'minf', box(b'dinf', dref)+stbl)
    mdia = box(b'mdia', box(b'mdhd', mdhd)+box(b'hdlr', bytes(8)+b'vide'+bytes(12))+minf)
    trak = box(b'trak', box(b'tkhd', tkhd)+mdia)
    path.write_bytes(ftyp+box(b'mdat', media)+box(b'moov', box(b'mvhd', mvhd)+trak))


def add_sparse_track(path, handler=b'meta', delay=0, empty_only=False):
    """A single metadata sample lasting 0.05 s in a 1.2 s video."""
    top = atoms(path.read_bytes())
    tkhd, mdhd = bytearray(84), bytearray(24)
    struct.pack_into('>I', tkhd, 12, 2)
    struct.pack_into('>I', tkhd, 20, 120)
    struct.pack_into('>II', mdhd, 12, 100, 5)
    stbl = box(b'stbl', b''.join([
        box(b'stsd', bytes(4)+struct.pack('>I', 1)+box(b'mebx', bytes(6)+b'\0\1')),
        runbox(b'stts', [5]),
        box(b'stsz', struct.pack('>III', 0, 1, 1)),
        box(b'stsc', struct.pack('>IIIII', 0, 1, 1, 1, 1)),
        box(b'stco', struct.pack('>III', 0, 1, len(top[0].encode())+8)),
    ]))
    dref = box(b'dref', struct.pack('>II', 0, 1)+box(b'url ', b'\0\0\0\1'))
    mdia = box(b'mdia', box(b'mdhd', mdhd)+box(b'hdlr', bytes(8)+handler+bytes(12))
               +box(b'minf', box(b'dinf', dref)+stbl))
    edts = b''
    if delay or empty_only:
        edits = [(120 if empty_only else delay, -1, 1, 0)]
        if not empty_only:
            edits.append((5, 0, 1, 0))
        edts = box(b'edts', box(b'elst', struct.pack('>II', 0, len(edits))
                   +b''.join(struct.pack('>Iihh', *e) for e in edits)))
    trak = box(b'trak', box(b'tkhd', tkhd)+mdia+edts)
    path.write_bytes(b''.join(box(a.kind, a.data+trak) if a.kind == b'moov'
                              else a.encode() for a in top))


class TimingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('JUSTTRIM_TEST_TMP'))
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name)/'source.mov'

    def test_quicktime_version_zero_negative_offsets(self):
        fixture(self.source)
        movie = Movie(self.source)
        self.assertEqual(movie.video.ctts[:6], [0, 20, -10, -10, 0, 0])
        self.assertEqual([float(movie.video.time(i)) for i in range(6)], [0, .3, .1, .2, .4, .5])

    def test_iso_version_zero_stays_unsigned(self):
        fixture(self.source, brand=b'isom')
        self.assertEqual(Movie(self.source).video.ctts[2], (1 << 32)-10)

    def test_version_one_signed_in_iso_and_quicktime(self):
        for brand in (b'qt  ', b'isom'):
            fixture(self.source, brand=brand, ctts_version=1, cslg_version=1)
            self.assertEqual(Movie(self.source).video.ctts[2], -10)

    def test_export_omits_summary_and_keeps_samples_and_group_indices(self):
        for version in (0, 1):
            fixture(self.source, cslg_version=version)
            original = self.source.read_bytes()
            output = Path(self.tmp.name)/f'clip-{version}.mov'
            Movie(self.source).export(.65, 1.1, output)
            clip = Movie(output)
            self.assertEqual(clip.video.count, 6)
            self.assertFalse(any(a.kind == b'cslg' for a in clip.video.stbl))
            self.assertEqual(clip.video.ctts, [0, 20, -10, -10, 0, 0])
            self.assertEqual(decode_compact(one(clip.video.stbl, b'csgm')), [3, 4, 1, 2, 3, 4])
            chunk = clip.video.chunks[0]
            with output.open('rb') as f:
                f.seek(chunk.offset)
                self.assertEqual(f.read(6), bytes(range(6, 12)))
            self.assertEqual(self.source.read_bytes(), original)

    def test_compact_all_ranges_and_widths(self):
        for bits in (4, 8, 16, 32):
            a = compact(bits, [([1, 2, 3, 4], 11), ([5], 2), ([6, 7, 8], 5)])
            expected = [1, 2, 3, 4, 1, 2, 3, 4, 1, 2, 3, 5, 5, 6, 7, 8, 6, 7]
            for start in range(len(expected)):
                for end in range(start+1, len(expected)+1):
                    sliced = atoms(compact_slice(a, start, end, len(expected)))[0]
                    self.assertEqual(decode_compact(sliced), expected[start:end])

    def test_invalid_compact_pattern_rejected(self):
        a = compact(4, [([1, 2, 3], 2)])
        with self.assertRaises(MovieError):
            compact_slice(a, 0, 2, 2)

    def test_compact_implicit_tail_stays_implicit(self):
        a = compact(4, [([1, 2], 3)])
        self.assertEqual(decode_compact(atoms(compact_slice(a, 2, 6, 6))[0]), [1])
        self.assertEqual(decode_compact(atoms(compact_slice(a, 4, 6, 6))[0]), [])

    def test_sparse_metadata_after_end_retained_but_not_presented(self):
        fixture(self.source)
        add_sparse_track(self.source)
        original = self.source.read_bytes()
        output = Path(self.tmp.name)/'sparse.mov'
        Movie(self.source).export(.65, 1.1, output)
        clip = Movie(output)
        metadata = clip.tracks[1]
        self.assertEqual(len(clip.tracks), 2)
        self.assertEqual(metadata.count, 0)
        self.assertEqual(metadata.durations, [])
        self.assertEqual(metadata.chunks, [])
        self.assertFalse(any(a.kind == b'edts' for a in metadata.children))
        self.assertEqual(struct.unpack_from('>I', metadata.tkhd.data, 20)[0], 0)
        self.assertEqual(metadata.stsd.data, Movie(self.source).tracks[1].stsd.data)
        retrim = Path(self.tmp.name)/'retrim.mov'
        clip.export(.1, .5, retrim)
        self.assertEqual(Movie(retrim).tracks[1].count, 0)
        self.assertEqual(self.source.read_bytes(), original)

    def test_sparse_metadata_before_start_retained_but_not_presented(self):
        fixture(self.source)
        add_sparse_track(self.source, delay=100)
        output = Path(self.tmp.name)/'before.mov'
        Movie(self.source).export(.1, .5, output)
        self.assertEqual(Movie(output).tracks[1].count, 0)

    def test_overlapping_metadata_remains_active(self):
        fixture(self.source)
        add_sparse_track(self.source)
        output = Path(self.tmp.name)/'overlap.mov'
        Movie(self.source).export(0, .5, output)
        self.assertEqual(Movie(output).tracks[1].count, 1)

    def test_missing_audio_still_rejected(self):
        fixture(self.source)
        add_sparse_track(self.source, handler=b'soun')
        with self.assertRaisesRegex(MovieError, 'no media'):
            Movie(self.source).plan(.65, 1.1)

    def test_empty_only_audio_not_treated_as_metadata(self):
        fixture(self.source)
        add_sparse_track(self.source, handler=b'soun', empty_only=True)
        with self.assertRaisesRegex(MovieError, 'multi-edit'):
            Movie(self.source)


if __name__ == '__main__':
    unittest.main()
