from clipper import transcript

VTT = """WEBVTT

00:00:01.000 --> 00:00:04.500
Halo semuanya, selamat datang di podcast.

00:00:04.500 --> 00:00:09.000
Hari ini kita bahas soal komisi rebate.
"""

SRT = """1
00:00:01,000 --> 00:00:04,500
Halo semuanya.

2
00:00:04,500 --> 00:00:09,000
Kita bahas rebate.
"""

def test_parse_vtt_reads_timing_and_text():
    segs = transcript.parse(VTT)
    assert len(segs) == 2
    assert segs[0].start == 1.0
    assert segs[0].end == 4.5
    assert segs[0].text == "Halo semuanya, selamat datang di podcast."
    assert segs[1].start == 4.5

def test_parse_srt_uses_comma_decimal():
    segs = transcript.parse(SRT)
    assert len(segs) == 2
    assert segs[0].end == 4.5
    assert segs[1].text == "Kita bahas rebate."

def test_parse_skips_cue_numbers_and_blank_lines():
    segs = transcript.parse(SRT)
    assert all(not s.text.strip().isdigit() for s in segs)
    assert all(s.text for s in segs)

def test_parse_joins_multiline_cue():
    vtt = ("WEBVTT\n\n00:00:00.000 --> 00:00:03.000\n"
           "baris pertama\nbaris kedua\n")
    segs = transcript.parse(vtt)
    assert segs[0].text == "baris pertama baris kedua"
