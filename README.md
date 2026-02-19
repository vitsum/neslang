<p align="center">
  <img src="docs/logo.svg" alt="NesLang" width="480">
</p>

<p align="center">
  <strong>A high-level language that compiles to playable NES ROMs.</strong>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> •
  <a href="docs/language-reference.md">Language Reference</a> •
  <a href="docs/cheatsheet.md">Cheatsheet</a> •
  <a href="#examples">Examples</a> •
  <a href="docs/palette.md">Color Palette</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.6+-blue?logo=python&logoColor=white" alt="Python 3.6+">
  <img src="https://img.shields.io/badge/platform-NES%20%2F%20Famicom%20%2F%20Dendy-e60012" alt="NES">
  <img src="https://img.shields.io/badge/mapper-NROM%20(0)-gray" alt="Mapper 0">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License: MIT">
  <img src="https://img.shields.io/badge/version-0.3.0-orange" alt="v0.3.0">
</p>

---

NesLang is a C-like language designed for creating **Nintendo Entertainment System** games. Write readable, high-level code — get a valid `.nes` ROM you can run in any emulator or flash to real hardware.

```c
// hello.nsl — 12 lines to a working ROM
func main() {
    ppu_off();
    color(0, 0x0F, 0x30, 0x10, 0x00);
    bg_text(10, 14, "HELLO WORLD!");
    ppu_on();
    while (true) { vblank(); scroll(0, 0); }
}
```

```bash
python3 neslang.py hello.nsl -o hello.nes
```

## Why NesLang?

Writing NES games traditionally means wrestling with 6502 assembly, manual memory management, and hardware registers. NesLang gives you:

- **C-like syntax** — `if`/`while`/functions, no assembly required
- **Visual tile editor** — draw sprites as ASCII art directly in your source code
- **Built-in font & box drawing** — text rendering and UI out of the box
- **FamiStudio music** — import music tracks with a single `music "file.txt"` directive
- **One-command build** — `.nsl` → `.nes` in one step
- **Zero dependencies** beyond Python and the cc65 toolchain

## Quick Start

### Prerequisites

- **Python 3.6+**
- **cc65 toolchain** (ca65 assembler + ld65 linker)

```bash
# Ubuntu / Debian
sudo apt install cc65

# macOS
brew install cc65

# Windows — download from https://cc65.github.io/
```

### Build & Run

```bash
# Clone the repo
git clone https://github.com/vitsum/neslang.git
cd neslang

# Compile the hello world example
python3 neslang.py examples/hello.nsl -o hello.nes

# Run in any NES emulator
fceux hello.nes        # or Mesen, Nestopia, etc.
```

## Examples

NesLang ships with 10+ example games ranging from a 14-line hello world to a 1,250-line beat-em-up — all compiling to real `.nes` ROMs.

| Example | Description | Lines | Highlights |
|---------|-------------|:-----:|------------|
| [`hello.nsl`](examples/hello.nsl) | Hello World | 14 | Minimal starting point |
| [`gamepad.nsl`](examples/gamepad.nsl) | Move a sprite with D-pad | 35 | Input handling, sprites |
| [`sound.nsl`](examples/sound.nsl) | Sound effects demo | 33 | APU channels, SFX |
| [`dance.nsl`](examples/dance.nsl) | Dancing sprites + music | 530 | FamiStudio integration, animation |
| [`spacedodge.nsl`](examples/spacedodge.nsl) | Space Dodge — dodge & shoot | 473 | Bullets, enemies, collision |
| [`stacko.nsl`](examples/stacko.nsl) | Falling blocks (Tetris-lite) | 1,006 | RAM board, music, scoring |
| [`norton.nsl`](examples/norton.nsl) | Norton Commander clone + Snake | 826 | Box-drawing UI, file manager TUI |
| [`multigame.nsl`](examples/multigame.nsl) | 4-in-1 game cart | 1,093 | Snake, Pong, Breakout, Dodge |
| [`fighter.nsl`](examples/fighter.nsl) | Street Fury beat-em-up | 1,254 | Multi-sprite characters, boss fights |
| [`asteroids.nsl`](examples/asteroids.nsl) | Classic Asteroids | 1,269 | 16×16 multisprite, rotation, thrust |

Pre-built `.nes` ROMs for all examples are included in the `examples/` folder — try them out immediately in an emulator.


## Language at a Glance

NesLang has a single type — **`byte`** (unsigned 8-bit, 0–255) — and compiles to native 6502 machine code via the ca65/ld65 toolchain.

```c
byte px = 120;                     // zero-page variable (fast)
ram byte[240] tilemap;             // RAM variable (large arrays)
const byte SPEED = 3;              // compile-time constant

tile 16 = "                        // define an 8×8 sprite visually
..XXXX..
.XXXXXX.
XX#XX#XX
X######X
XXXXXXXX
.XXXXXX.
..XXXX..
........
";

func update(byte pad) {
    if (pad & BTN_RIGHT) { px = px + SPEED; }
    sprite(0, px, 100, 16, 0);
}
```

### Key Concepts

**Two memory zones:**  `byte` variables live in the 6502 zero-page (~200 bytes, fast). `ram byte` variables live in general RAM (~1,280 bytes, slightly slower). Use zero-page for hot variables, RAM for large arrays.

**PPU rules:** Background drawing functions (`bg_text`, `bg_addr`, etc.) can only be called while the PPU is off. Sprite and scroll functions are safe to call anytime.

**Music:** Import FamiStudio compositions with `music "file.txt"`, then call `music_init()` once and `music_tick()` every frame.

For the full language spec, see the **[Language Reference](docs/language-reference.md)**. For a quick reminder while coding, see the **[Cheatsheet](docs/cheatsheet.md)**.

## How It Works

```
  .nsl source
      │
      ├── Lexer ─── Tokenization
      ├── Parser ── AST construction
      ├── Music ─── FamiStudio .txt → APU engine (if music directive present)
      └── CodeGen ─ 6502 assembly (.s)
                      │
                      ├── ca65 ── Object file (.o)
                      └── ld65 ── iNES ROM (.nes)
```

The compiler is a single Python file (`neslang.py`, ~1,700 lines) with no external Python dependencies. It generates 6502 assembly, then shells out to ca65/ld65 (from the cc65 suite) to produce the final ROM.

**Output format:** iNES mapper 0 (NROM), 32 KB PRG + 8 KB CHR, horizontal mirroring. Compatible with every NES emulator and flashable to real cartridges.

## Project Structure

```
neslang/
├── neslang.py              # Compiler (lexer, parser, codegen)
├── music_converter.py      # FamiStudio text → NES APU data
├── fontdata.py             # Built-in 8×8 font + box-drawing tiles
├── docs/
│   ├── language-reference.md   # Full language specification
│   ├── cheatsheet.md           # Quick reference card
│   ├── palette.md              # NES color palette guide
│   └── sprites_preview.png     # Example sprite artwork
└── examples/
    ├── hello.nsl               # ... and 10+ example games
    ├── *.nes                   # Pre-built ROMs
    └── music.txt               # Example FamiStudio export
```

## Contributing

Contributions are welcome! Whether it's bug fixes, new built-in functions, example games, or documentation improvements — feel free to open an issue or PR.

If you build something cool with NesLang, consider adding it to the `examples/` folder!

## License

MIT License — see [LICENSE](LICENSE) for details.

NesLang compiler is free to use for any purpose. Generated ROMs are entirely yours. The cc65 toolchain (required dependency) is released under the zlib license.

---

<p align="center">
  <em>Made with ♥ for the NES homebrew community</em>
</p>
