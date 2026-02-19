"""
music_converter.py — Converts FamiStudio text export to NES music data.

v2: Fixed pattern boundary overflow + note overlap truncation.
    All patterns are flattened into absolute timeline first,
    then overlapping durations are truncated.
"""

import re
import math

CPU_FREQ = 1789773
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

def note_to_freq(note_str):
    m = re.match(r'^([A-G]#?)(\d+)$', note_str)
    if not m:
        return 0
    name, octave = m.group(1), int(m.group(2))
    semitone = NOTE_NAMES.index(name)
    midi = (octave + 1) * 12 + semitone
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))

def freq_to_pulse_period(freq):
    if freq <= 0:
        return 0
    period = round(CPU_FREQ / (16.0 * freq)) - 1
    return max(0, min(2047, int(period)))

def freq_to_tri_period(freq):
    if freq <= 0:
        return 0
    period = round(CPU_FREQ / (32.0 * freq)) - 1
    return max(0, min(2047, int(period)))

def noise_note_to_period(note_str):
    m = re.match(r'^([A-G]#?)(\d+)$', note_str)
    if not m:
        return 8
    name, octave = m.group(1), int(m.group(2))
    semitone = NOTE_NAMES.index(name)
    midi = (octave + 1) * 12 + semitone
    period = 15 - max(0, min(15, (midi - 30) * 15 // 50))
    return max(0, min(15, period))


class FamiStudioParser:
    def __init__(self, text):
        self.text = text
        self.channels = {}
        self.tempo_info = {}
        self.pattern_length = 176  # default: 16 rows × 11 ticks
        self.parse()

    def parse(self):
        lines = self.text.split('\n')
        current_channel = None
        current_pattern = None
        channel_type = None

        for line in lines:
            stripped = line.strip()

            m = re.match(r'Song .* PatternLength="(\d+)".*NoteLength="(\d+)"', stripped)
            if m:
                pat_rows = int(m.group(1))
                note_len = int(m.group(2))
                self.pattern_length = pat_rows * note_len
                self.tempo_info['pattern_length'] = self.pattern_length
                self.tempo_info['note_length'] = note_len

            m2 = re.match(r'Song .* NoteLength="(\d+)".*PatternLength="(\d+)"', stripped)
            if m2:
                note_len = int(m2.group(1))
                pat_rows = int(m2.group(2))
                self.pattern_length = pat_rows * note_len
                self.tempo_info['pattern_length'] = self.pattern_length
                self.tempo_info['note_length'] = note_len

            m = re.match(r'Channel Type="(\w+)"', stripped)
            if m:
                channel_type = m.group(1)
                self.channels[channel_type] = {
                    'patterns': {},
                    'order': []
                }
                current_channel = self.channels[channel_type]
                current_pattern = None
                continue

            if current_channel is None:
                continue

            m = re.match(r'Pattern Name="([^"]+)"', stripped)
            if m:
                pat_name = m.group(1)
                current_channel['patterns'][pat_name] = []
                current_pattern = current_channel['patterns'][pat_name]
                continue

            m = re.match(r'Note Time="(\d+)" Value="([^"]+)" Duration="(\d+)"', stripped)
            if m and current_pattern is not None:
                current_pattern.append({
                    'time': int(m.group(1)),
                    'value': m.group(2),
                    'duration': int(m.group(3)),
                })
                continue

            m = re.match(r'PatternInstance Time="(\d+)" Pattern="([^"]+)"', stripped)
            if m and current_channel is not None:
                current_channel['order'].append(m.group(2))
                continue


def flatten_channel(parser, channel_type):
    """Flatten all patterns into one absolute-time note list.
    Truncates notes at pattern boundaries and handles overlaps."""

    ch = parser.channels.get(channel_type)
    if not ch:
        return []

    pat_len = parser.pattern_length
    all_notes = []

    # Step 1: Place all notes with absolute times
    for pat_idx, pat_name in enumerate(ch['order']):
        pattern = ch['patterns'].get(pat_name, [])
        offset = pat_idx * pat_len

        for note in pattern:
            abs_time = offset + note['time']
            dur = note['duration']

            # Truncate at pattern boundary
            max_dur = (offset + pat_len) - abs_time
            if dur > max_dur:
                dur = max_dur
            if dur <= 0:
                continue

            all_notes.append({
                'time': abs_time,
                'value': note['value'],
                'duration': dur,
            })

    # Step 2: Sort by time
    all_notes.sort(key=lambda n: n['time'])

    # Step 3: Truncate overlapping durations
    # Each note's effective duration = min(original_dur, next_note_time - this_time)
    for i in range(len(all_notes) - 1):
        gap = all_notes[i + 1]['time'] - all_notes[i]['time']
        if all_notes[i]['duration'] > gap:
            all_notes[i]['duration'] = gap

    return all_notes


def notes_to_stream(notes, total_ticks, is_triangle=False, is_noise=False):
    """Convert flat note list to event stream.

    Returns list of (duration, byte1, byte2) tuples ready for RODATA.
    Silence events use byte1=0xFF, byte2=0x00.
    """
    stream = []
    pos = 0

    for note in notes:
        t = note['time']
        dur = note['duration']
        val = note['value']

        # Silence gap before this note
        if t > pos:
            gap = t - pos
            stream.append((gap, 0xFF, 0x00))

        # Encode note
        if is_noise:
            period = noise_note_to_period(val)
            vol = 8
            stream.append((dur, period, vol))
        elif is_triangle:
            freq = note_to_freq(val)
            period = freq_to_tri_period(freq)
            lo = period & 0xFF
            hi = period >> 8 & 0x07
            stream.append((dur, lo, hi))
        else:
            freq = note_to_freq(val)
            period = freq_to_pulse_period(freq)
            lo = period & 0xFF
            hi = period >> 8 & 0x07
            vol = 10
            hi_vol = hi | ((vol & 0x0F) << 3)
            stream.append((dur, lo, hi_vol))

        pos = t + dur

    # Silence at end of song
    if pos < total_ticks:
        stream.append((total_ticks - pos, 0xFF, 0x00))

    return stream


def stream_to_bytes(stream):
    """Convert event stream to byte array.
    Per event: [duration, byte1, byte2]. $00 duration = loop marker."""
    result = []
    for dur, b1, b2 in stream:
        # Split long durations into <=254 chunks
        while dur > 0:
            chunk = min(dur, 254)
            dur -= chunk
            result.extend([chunk, b1 & 0xFF, b2 & 0xFF])
    result.append(0)  # End/loop marker
    return result


def generate_music_asm(famistudio_text):
    """Parse FamiStudio text and generate all music data + engine asm.
    Returns (zp_asm, code_asm, rodata_asm)."""

    parser = FamiStudioParser(famistudio_text)
    pat_len = parser.pattern_length

    # Total song length in ticks
    max_pats = 0
    for ch in parser.channels.values():
        max_pats = max(max_pats, len(ch['order']))
    total_ticks = max_pats * pat_len

    # Flatten and convert each channel
    channels = [
        ('Square1',  False, False),
        ('Square2',  False, False),
        ('Triangle', True,  False),
        ('Noise',    False, True),
    ]

    all_bytes = {}
    for ch_name, is_tri, is_noise in channels:
        notes = flatten_channel(parser, ch_name)
        stream = notes_to_stream(notes, total_ticks, is_triangle=is_tri, is_noise=is_noise)
        all_bytes[ch_name] = stream_to_bytes(stream)

    labels = ['__mus_sq1_data', '__mus_sq2_data', '__mus_tri_data', '__mus_noi_data']
    ch_names = ['Square1', 'Square2', 'Triangle', 'Noise']

    # === RODATA ===
    rodata = ['; === Music Data (auto-generated from FamiStudio) ===']
    for label, ch_name in zip(labels, ch_names):
        data = all_bytes[ch_name]
        rodata.append(f'{label}:    ; {len(data)} bytes')
        for i in range(0, len(data), 16):
            chunk = data[i:i+16]
            rodata.append('    .byte ' + ', '.join(f'${b:02X}' for b in chunk))

    rodata.append('')
    rodata.append('__mus_data_lo:')
    rodata.append('    .byte ' + ', '.join(f'<{l}' for l in labels))
    rodata.append('__mus_data_hi:')
    rodata.append('    .byte ' + ', '.join(f'>{l}' for l in labels))

    # === ZEROPAGE ===
    zp = [
        '; === Music engine ZP vars ===',
        '__mus_playing: .res 1',
        '__mus_ptr_lo:  .res 4',
        '__mus_ptr_hi:  .res 4',
        '__mus_ticks:   .res 4',
        '__mus_tmp:     .res 2',
    ]

    # === CODE: Music Engine ===
    code = []
    code.append('; === Music Engine ===')

    # music_init
    code.append('__music_init:')
    code.append('    ldx #3')
    code.append('@init_loop:')
    code.append('    lda __mus_data_lo,x')
    code.append('    sta __mus_ptr_lo,x')
    code.append('    lda __mus_data_hi,x')
    code.append('    sta __mus_ptr_hi,x')
    code.append('    lda #1')
    code.append('    sta __mus_ticks,x')
    code.append('    dex')
    code.append('    bpl @init_loop')
    code.append('    lda #1')
    code.append('    sta __mus_playing')
    code.append('    rts')
    code.append('')

    # music_tick
    code.append('__music_tick:')
    code.append('    lda __mus_playing')
    code.append('    beq @mt_done')
    code.append('    ldx #0')
    code.append('    jsr __mus_tick_ch   ; Square 1')
    code.append('    ldx #1')
    code.append('    jsr __mus_tick_ch   ; Square 2')
    code.append('    ldx #2')
    code.append('    jsr __mus_tick_ch   ; Triangle')
    code.append('    ldx #3')
    code.append('    jsr __mus_tick_ch   ; Noise')
    code.append('@mt_done:')
    code.append('    rts')
    code.append('')

    # Universal channel tick — X = channel index (0-3)
    # Reads 3-byte events: [duration, byte1, byte2]
    code.append('__mus_tick_ch:')
    code.append('    dec __mus_ticks,x')
    code.append('    beq @read_event')
    code.append('    rts')
    code.append('@read_event:')
    code.append('    ; Load pointer')
    code.append('    lda __mus_ptr_lo,x')
    code.append('    sta __mus_tmp')
    code.append('    lda __mus_ptr_hi,x')
    code.append('    sta __mus_tmp+1')
    code.append('    ; Read duration')
    code.append('    ldy #0')
    code.append('    lda (__mus_tmp),y')
    code.append('    bne @not_end')
    code.append('    jmp @loop_song      ; $00 = end marker')
    code.append('@not_end:')
    code.append('    sta __mus_ticks,x')
    code.append('    ; Read byte1')
    code.append('    iny')
    code.append('    lda (__mus_tmp),y')
    code.append('    cmp #$FF')
    code.append('    bne @not_sil')
    code.append('    jmp @silence')
    code.append('@not_sil:')
    code.append('    ; Route to correct channel')
    code.append('    cpx #3')
    code.append('    beq @do_noise')
    code.append('    cpx #2')
    code.append('    beq @do_tri')
    code.append('    ; --- Pulse channel ---')
    code.append('    ; byte1 = timer_lo, byte2 = timer_hi(2:0) | vol(6:3)')
    code.append('    pha                  ; save timer_lo')
    code.append('    iny')
    code.append('    lda (__mus_tmp),y    ; byte2')
    code.append('    pha                  ; save byte2')
    code.append('    lsr a')
    code.append('    lsr a')
    code.append('    lsr a')
    code.append('    and #$0F')
    code.append('    ora #%10110000       ; duty 50%, halt, constant vol')
    code.append('    cpx #0')
    code.append('    bne @pulse1_vol')
    code.append('    sta $4000')
    code.append('    lda #$00')
    code.append('    sta $4001')
    code.append('    jmp @pulse_timer')
    code.append('@pulse1_vol:')
    code.append('    sta $4004')
    code.append('    lda #$00')
    code.append('    sta $4005')
    code.append('@pulse_timer:')
    code.append('    pla                  ; byte2')
    code.append('    and #$07            ; timer high bits')
    code.append('    pha                  ; save timer_hi for $4003/$4007')
    code.append('    pla')
    code.append('    cpx #0')
    code.append('    bne @pulse1_hi')
    code.append('    sta $4003')
    code.append('    pla')
    code.append('    sta $4002')
    code.append('    jmp @advance')
    code.append('@pulse1_hi:')
    code.append('    sta $4007')
    code.append('    pla')
    code.append('    sta $4006')
    code.append('    jmp @advance')
    code.append('')
    code.append('@do_tri:')
    code.append('    ; byte1 = timer_lo, byte2 = timer_hi')
    code.append('    sta $400A            ; timer lo')
    code.append('    iny')
    code.append('    lda (__mus_tmp),y')
    code.append('    and #$07')
    code.append('    ora #%00001000       ; length counter load')
    code.append('    sta $400B')
    code.append('    lda #%11111111       ; linear counter = max, halt off')
    code.append('    sta $4008')
    code.append('    jmp @advance')
    code.append('')
    code.append('@do_noise:')
    code.append('    ; byte1 = period, byte2 = volume')
    code.append('    sta $400E            ; noise period')
    code.append('    iny')
    code.append('    lda (__mus_tmp),y    ; volume')
    code.append('    and #$0F')
    code.append('    ora #%00110000       ; halt, constant vol')
    code.append('    sta $400C')
    code.append('    lda #%00001000       ; length counter load')
    code.append('    sta $400F')
    code.append('    jmp @advance')
    code.append('')
    code.append('@silence:')
    code.append('    ; Silence the channel')
    code.append('    cpx #3')
    code.append('    beq @sil_noise')
    code.append('    cpx #2')
    code.append('    beq @sil_tri')
    code.append('    cpx #0')
    code.append('    bne @sil_p1')
    code.append('    lda #%00110000')
    code.append('    sta $4000')
    code.append('    jmp @advance_sil')
    code.append('@sil_p1:')
    code.append('    lda #%00110000')
    code.append('    sta $4004')
    code.append('    jmp @advance_sil')
    code.append('@sil_tri:')
    code.append('    lda #%10000000       ; halt linear counter')
    code.append('    sta $4008')
    code.append('    jmp @advance_sil')
    code.append('@sil_noise:')
    code.append('    lda #%00110000')
    code.append('    sta $400C')
    code.append('@advance_sil:')
    code.append('    iny                  ; skip byte2')
    code.append('@advance:')
    code.append('    ; Advance pointer by 3 bytes')
    code.append('    lda __mus_ptr_lo,x')
    code.append('    clc')
    code.append('    adc #3')
    code.append('    sta __mus_ptr_lo,x')
    code.append('    lda __mus_ptr_hi,x')
    code.append('    adc #0')
    code.append('    sta __mus_ptr_hi,x')
    code.append('    rts')
    code.append('')
    code.append('@loop_song:')
    code.append('    ; Reset pointer to start')
    code.append('    lda __mus_data_lo,x')
    code.append('    sta __mus_ptr_lo,x')
    code.append('    lda __mus_data_hi,x')
    code.append('    sta __mus_ptr_hi,x')
    code.append('    lda #1')
    code.append('    sta __mus_ticks,x')
    code.append('    rts')

    return '\n'.join(zp), '\n'.join(code), '\n'.join(rodata)


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 music_converter.py <famistudio.txt>")
        sys.exit(1)
    with open(sys.argv[1]) as f:
        text = f.read()

    parser = FamiStudioParser(text)
    pat_len = parser.pattern_length
    print(f"Pattern length: {pat_len} ticks")
    print(f"Channels: {list(parser.channels.keys())}")

    for ch_name in ['Square1', 'Square2', 'Triangle', 'Noise']:
        notes = flatten_channel(parser, ch_name)
        if notes:
            print(f"\n{ch_name}: {len(notes)} notes")
            # Show first 5
            for n in notes[:5]:
                print(f"  t={n['time']:4d} dur={n['duration']:3d} {n['value']}")
            # Show any truncations
            orig_ch = parser.channels.get(ch_name, {})
            total_orig = sum(len(p) for p in orig_ch.get('patterns', {}).values())
            print(f"  ({total_orig} original notes, {len(notes)} after flatten)")

    zp, code, rodata = generate_music_asm(text)
    # Count bytes
    import re
    byte_lines = [l for l in rodata.split('\n') if '.byte' in l]
    total_bytes = sum(l.count(',') + 1 for l in byte_lines)
    print(f"\nTotal music data: ~{total_bytes} bytes in RODATA")
