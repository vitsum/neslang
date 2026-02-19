# NesLang Language Reference

Complete reference for the NesLang programming language — a C-like language that compiles to playable NES ROMs.

## Table of Contents

- [Types](#types)
- [Variables](#variables)
- [Functions](#functions)
- [Operators](#operators)
- [Control Flow](#control-flow)
- [Tile Definitions](#tile-definitions)
- [Built-in Functions](#built-in-functions)
  - [PPU Control](#ppu-control)
  - [Palette](#palette)
  - [Scroll](#scroll)
  - [Timing](#timing)
  - [Sprites](#sprites)
  - [Background](#background)
  - [Input](#input)
  - [Sound](#sound)
  - [Music](#music)
  - [Utility](#utility)
- [Built-in Tiles](#built-in-tiles)
- [Architecture Notes](#architecture-notes)
- [Tips & Patterns](#tips--patterns)

---

## Types

NesLang has a single type: **`byte`** (unsigned 8-bit, 0–255). All variables are stored in the 6502 zero-page (256 bytes max).

```c
byte x = 100;
byte y = 0;
byte[20] enemies;      // array of 20 bytes
const byte SPEED = 3;  // compile-time constant
```

## Variables

```c
byte name = value;      // global or local, initialized (zero-page — fast)
byte name;              // defaults to 0
byte[N] name;           // array of N bytes
const byte NAME = val;  // constant (no RAM used)
ram byte name;          // in RAM ($0300+) — slower but more space
ram byte[N] name;       // large array in RAM
```

**Zero-page** variables (default `byte`) are stored in the 6502 zero-page — fast 2-byte instructions, but limited to ~200 bytes total. Use for frequently accessed variables: counters, coordinates, game state.

**RAM** variables (`ram byte`) are stored at $0300–$07FF — 1280 bytes available. Use for large arrays, lookup tables, level maps, and anything that doesn't need the speed of zero-page.

```c
// Typical usage pattern:
byte x = 100;             // player position — ZP for speed
byte score = 0;           // score — ZP for fast access in loops
ram byte[240] tilemap;    // level data — RAM (too big for ZP!)
ram byte[64] enemy_hp;    // 64 enemies — RAM
```

Array initializers support full expressions, not just number literals:

```c
byte[4] data = { 1, 2, 3, 4 };           // literal values
byte[3] dirs = { 0, SPEED, 0 - SPEED };  // expressions and constants allowed
```

## Functions

```c
func name(byte arg1, byte arg2) {
    // body
    return expr;  // optional, returns via A register
}

func main() {
    // entry point — required
}
```

- Parameters and return values are single bytes
- Functions can call each other (no recursion — stack is limited)
- All functions compile to 6502 `jsr`/`rts`

## Operators

### Binary Operators

Listed from highest to lowest precedence:

| Operator | Description |
|----------|-------------|
| `*` | Multiplication (8-bit, result 0–255) |
| `+` `-` | Addition, subtraction |
| `<` `>` `<=` `>=` | Comparison (unsigned) |
| `==` `!=` | Equality |
| `&` | Bitwise AND |
| `^` | Bitwise XOR |
| `\|` | Bitwise OR |

### Unary Operators

| Operator | Description |
|----------|-------------|
| `~` | Bitwise NOT (flips all 8 bits: `~x` is equivalent to `x ^ 255`) |
| `!` | Logical NOT (`!0` = 1, `!anything_else` = 0) |

**Note:** No unary minus, divide, or shift operators. Use `0 - x` for negation. Use lookup tables or repeated subtraction for division.

```c
byte mask = flags | BTN_A;          // set a bit with OR
byte inverted = ~pad;               // flip all bits
byte not_pressing = !(pad & BTN_A); // 1 if not pressed, 0 if pressed
```

## Control Flow

```c
if (condition) {
    // ...
} else {
    // ...
}

while (condition) {
    // ...
}

while (true) {
    // infinite loop (NES games never exit)
}
```

### Boolean Literals

`true` and `false` are built-in keywords that evaluate to `1` and `0` respectively. They can be used in any expression context, not just loop conditions:

```c
byte alive = true;      // same as byte alive = 1;
byte game_over = false;  // same as byte game_over = 0;
if (alive) { ... }       // any nonzero value is truthy
```

## Tile Definitions

Define 8×8 pixel tiles using visual ASCII art. Each tile uses a 4-character palette:

| Char | Alternate | Color Index | Typical Use |
|------|-----------|-------------|-------------|
| `.` | | 0 | Background / transparent |
| `X` | `1` | 1 | Outline / dark |
| `O` | `2` | 2 | Main color |
| `#` | `3` | 3 | Highlight / skin |

You can use numeric characters `1`, `2`, `3` instead of `X`, `O`, `#` if you prefer. Any unrecognized character defaults to color 0.

```c
tile 1 = "
..XXXX..
.XXXXXX.
XX.XX.XX
XXXXXXXX
XXXXXXXX
XX.XX.XX
.XXXXXX.
..XXXX..
";
```

Tiles 1–15 are reserved for box-drawing characters. Tiles 32–90 contain a built-in ASCII font (space through Z). User tiles should use IDs 16–31 or 91+.

---

## Built-in Functions

### PPU Control

```c
ppu_on()           // Enable rendering (background + sprites + NMI)
ppu_off()          // Disable rendering (safe for bulk PPU writes)
```

**Critical:** All `bg_*` functions write to PPU registers `$2006`/`$2007`. These MUST only be called while the PPU is off (`ppu_off()`) or during the init phase before the first `ppu_on()`. Writing during rendering causes visual glitches.

### Palette

```c
color(index, c0, c1, c2, c3)
```

Sets 4 colors at palette position. NES has 8 palettes (4 BG + 4 sprite):

| Index | Palette |
|-------|---------|
| 0 | BG palette 0 |
| 4 | BG palette 1 |
| 8 | BG palette 2 |
| 12 | BG palette 3 |
| 16 | Sprite palette 0 |
| 20 | Sprite palette 1 |
| 24 | Sprite palette 2 |
| 28 | Sprite palette 3 |

Colors are NES palette indices (0x00–0x3F). See [palette.md](palette.md) for the full color reference.

Common values:

| Code | Color | Code | Color |
|------|-------|------|-------|
| `0x0F` | Black | `0x30` | White |
| `0x16` | Red | `0x2A` | Green |
| `0x12` | Blue | `0x28` | Yellow |
| `0x27` | Orange | `0x21` | Light blue |
| `0x10` | Gray | `0x36` | Skin/peach |

### Scroll

```c
scroll(x, y)       // Set background scroll position
```

Scroll is applied during NMI (vblank), so it's safe to call anywhere in your game loop. Values are stored in zero-page and the NMI handler writes them to `$2005`.

### Timing

```c
vblank()           // Wait for next vertical blank (1/60th second)
```

Call once per frame at the top of your game loop. This synchronizes your game to 60 FPS.

### Sprites

```c
sprite(id, x, y, tile, attr)
hide_sprite(id)
```

- `id`: Sprite slot 0–63 (NES supports 64 hardware sprites)
- `x`, `y`: Screen position in pixels
- `tile`: Tile index from CHR ROM
- `attr`: Sprite attributes
  - `0` = normal
  - `64` = horizontal flip (`0x40`)
  - `128` = vertical flip (`0x80`)
  - `1`, `2`, `3` = palette 1/2/3 (combine with flip: `64 + 1` = hflip + palette 1)

### Background

**All bg functions require PPU to be off!**

```c
bg_addr(x, y)               // Set PPU write address (tile coordinates)
bg_byte(tile)               // Write one tile to current address
bg_fill(tile, count)        // Write tile N times
bg_text(x, y, "STRING")     // Write text (auto uppercase, uses built-in font)
bg_attr(ax, ay, value)      // Set attribute table entry
```

**Attribute table:** Each byte controls palette selection for a 4×4 tile area (32×32 pixels). The 8×8 attribute grid covers the 32×30 tile screen.

```
Bits: [7:6]=bottom-right  [5:4]=bottom-left  [3:2]=top-right  [1:0]=top-left
```

Common values:
- `0x00` = all palette 0
- `0x55` = all palette 1
- `0xAA` = all palette 2
- `0xFF` = all palette 3

### Input

```c
byte pad = gamepad(0);    // Read controller 1 (0) or 2 (1)
```

Button constants (combine with `&`):

```c
BTN_A       BTN_B       BTN_SELECT   BTN_START
BTN_UP      BTN_DOWN    BTN_LEFT     BTN_RIGHT
```

**Edge detection** (single press, not held):

```c
byte pressed = pad & ~old_pad;   // new presses this frame
old_pad = pad;
if (pressed & BTN_A) { /* just pressed */ }
```

### Sound

```c
enable_sound()     // Enable APU (call once at init)
silence()          // Stop all channels

play_note(channel, timer_lo, timer_hi, volume)
noise(period, volume)
```

- `channel`: 0 = pulse 1, 1 = pulse 2
- `timer_lo`/`timer_hi`: Frequency (lower = higher pitch). Common: `0xFD,0x01` ≈ A4
- `volume`: 0–15
- `period`: Noise period 0–15 (0 = highest pitch)

**Predefined sound effects:**

```c
sfx_pickup()       // Ascending chirp
sfx_hit()          // Short noise burst
sfx_jump()         // Quick sweep-up
sfx_explode()      // Long low noise
```

### Music

NesLang can import music from **FamiStudio** (text export format). The compiler parses all 4 APU channels (Pulse 1, Pulse 2, Triangle, Noise), converts note data to NES APU register values, and embeds a music engine + data into the ROM.

#### FamiStudio Export

1. Compose your music in [FamiStudio](https://famistudio.org/)
2. File → Export → **FamiStudio Text** → save as `music.txt`
3. Reference it in your `.nsl` file

#### Usage

```c
// At top level (outside functions):
music "music.txt";

func main() {
    ppu_off();
    // ... setup palettes, draw bg ...
    enable_sound();
    music_init();       // Initialize music engine (once)
    ppu_on();

    while (true) {
        vblank();
        music_tick();   // Advance music by one frame (call every frame!)
        // ... game logic ...
        scroll(0, 0);
    }
}
```

#### How It Works

- `music "file.txt"` — loads FamiStudio text file at compile time
- `music_init()` — sets channel pointers to start of song data
- `music_tick()` — called once per frame (60 Hz), reads next note events and writes APU registers

The music engine handles all 4 NES APU channels (2× pulse, triangle, noise), note overlap truncation, pattern boundary alignment, automatic song looping, and typically adds ~1.5–2 KB ROM overhead.

**Note:** `music_tick()` uses APU channels directly. Don't mix with `play_note()`/`noise()` calls — they'll conflict. Use `sfx_*` functions sparingly, or dedicate Pulse 2 for SFX and leave Pulse 1 for music.

### Utility

```c
byte r = rand();   // Pseudo-random number 0–255 (LFSR)
```

---

## Built-in Tiles

### Box Drawing (tiles 1–15)

```
1=─  2=│  3=┌  4=┐  5=└  6=┘
7=├  8=┤  9=┬  10=┴  11=┼  12=█
13=▶  14=◀  15=(reserved)
```

### ASCII Font (tiles 32–90)

Built-in 8×8 monospace font covering space (32), `!` through `/` (33–47), `0`–`9` (48–57), `:` through `@` (58–64), and `A`–`Z` (65–90). `bg_text()` automatically converts lowercase to uppercase.

---

## Architecture Notes

### Memory Map

| Region | Address | Size | Description |
|--------|---------|------|-------------|
| Zero Page | $00–$FF | 256 B | `byte` variables. ~200 available. Fast 2-byte addressing. |
| OAM Buffer | $0200–$02FF | 256 B | 64 sprites × 4 bytes. Managed by `sprite()`. |
| RAM | $0300–$07FF | 1280 B | `ram byte` variables and large arrays. |
| PRG ROM | $8000–$FFFF | 32 KB | Code space. |
| CHR ROM | $0000–$1FFF | 8 KB | Tile data (256 BG + 256 sprite tiles). |

### NES Limitations

- **Screen:** 256×240 pixels, 32×30 tile grid (8×8 tiles)
- **Colors:** 25 on screen (4 BG palettes × 3 colors + 1 shared BG + 4 sprite palettes × 3 colors)
- **Sprites per scanline:** Max 8 (hardware limit)
- **Background:** No mid-frame PPU writes during rendering!

### Compilation Pipeline

```
.nsl source
    │
    ├─ Lexer → tokens
    ├─ Parser → AST
    ├─ music_converter.py (if `music` directive present)
    │     └─ FamiStudio .txt → ZP vars + engine code + RODATA tables
    └─ CodeGen → .s (6502 assembly)
                  │
                  ├─ ca65 → .o (object)
                  └─ ld65 → .nes (iNES ROM)
```

### Output Format

- iNES mapper 0 (NROM)
- 32KB PRG ROM + 8KB CHR ROM
- Horizontal mirroring
- No battery-backed RAM
- Compatible with all NES emulators

### Auto-Loop Safety Net

If `main()` runs to its end without an explicit infinite loop, the compiler automatically inserts a jump back to the start of `main()`. This prevents the CPU from executing garbage memory. However, you should always write an explicit `while (true) { ... }` loop — the auto-loop is a safety net, not a substitute for proper game loop design.

---

## Tips & Patterns

### Game Loop Template

```c
func main() {
    ppu_off();
    // Set palettes, draw background, etc.
    ppu_on();

    while (true) {
        vblank();
        // Read input
        // Update game state
        // Update sprites
        scroll(0, 0);
    }
}
```

### Screen Transitions

```c
ppu_off();
// Safe to do bulk bg writes here
clear_screen();
draw_new_screen();
ppu_on();
```

### Avoiding PPU Glitches

1. Never call `bg_addr`/`bg_byte`/`bg_text`/`bg_attr` while PPU is on
2. Use sprites for dynamic HUD elements (HP bars, scores)
3. `scroll()` is always safe — it writes to zero-page, NMI applies it
4. Do all background setup in `ppu_off()` blocks

### Unsigned Arithmetic

All values are 0–255. Subtraction wraps: `0 - 1 = 255`. Use this for negation:

```c
byte neg_speed = 0 - speed;    // e.g., 0 - 2 = 254 = -2 in signed
```
