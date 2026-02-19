# NesLang Cheatsheet

## Compile
```bash
python3 neslang.py game.nsl -o game.nes
```

## Variables
```c
byte x = 10;           // zero-page (fast, ~200 bytes)
byte[20] arr;          // ZP array
const byte N = 5;      // constant
ram byte y = 0;        // RAM $0300+ (slower, 1280 bytes)
ram byte[200] map;     // large arrays go here!
```

## Tile (8x8 pixels)
```c
tile 16 = "            // .=transparent X=color1 O=color2 #=color3
..XXXX..
.XXXXXX.
XX#XX#XX
X######X
XXXXXXXX
.XXXXXX.
..XXXX..
........
";
```

## Palette
```c
color(0, bg, c1, c2, c3);     // BG palette 0
color(4, bg, c1, c2, c3);     // BG palette 1
color(16, bg, c1, c2, c3);    // Sprite palette 0
// bg is shared across all BG palettes
// 0x0F=black 0x30=white 0x16=red 0x12=blue 0x2A=green 0x28=yellow
```

## PPU
```c
ppu_off();      // must be off for bg_* writes
ppu_on();       // enable rendering
vblank();       // wait for frame
scroll(0, 0);   // set scroll (safe anytime)
```

## Background (PPU must be off!)
```c
bg_addr(x, y);              // set write pos (0-31, 0-29)
bg_byte(tile_id);           // write tile
bg_text(x, y, "TEXT");      // write string
bg_fill(tile, count);       // fill N tiles
bg_attr(ax, ay, val);       // set palette area (0-7, 0-7)
// attr vals: 0x00=pal0  0x55=pal1  0xAA=pal2  0xFF=pal3
```

## Sprites (safe anytime)
```c
sprite(id, x, y, tile, attr);  // id=0-63, attr: 0=normal 64=hflip
hide_sprite(id);
```

## Input
```c
byte pad = gamepad(0);                // read controller
byte pressed = pad & (old_pad ^ 255); // edge detect
old_pad = pad;
// BTN_A BTN_B BTN_UP BTN_DOWN BTN_LEFT BTN_RIGHT BTN_START BTN_SELECT
```

## Sound
```c
enable_sound();
sfx_pickup();    sfx_hit();    sfx_jump();    sfx_explode();
silence();
play_note(channel, timer_lo, timer_hi, volume);  // ch 0-1, vol 0-15
noise(period, volume);                            // period 0-15
```

## Music (FamiStudio)
```c
// Top level — load FamiStudio text export:
music "music.txt";

// In main() after enable_sound():
music_init();       // once

// In game loop (every frame):
music_tick();       // advances all 4 APU channels
```
Export from FamiStudio: File → Export → FamiStudio Text.
Don't mix music_tick() with play_note()/noise() — they share APU channels.

## Game Loop Pattern
```c
func main() {
    ppu_off();
    color(0, 0x0F, 0x30, 0x10, 0x00);
    // draw background here
    ppu_on();
    while (true) {
        vblank();
        byte pad = gamepad(0);
        // update game state
        // update sprites
        scroll(0, 0);
    }
}
```

## Key Rules
1. bg_* only when PPU is off
2. sprite() safe anytime
3. scroll() safe anytime (applied in NMI)
4. vblank() once per frame
5. All values are unsigned 0-255
6. Multiply with `*` (8-bit, result 0-255). No divide — use loops
7. ~200 bytes zero-page for `byte` variables
8. ~1280 bytes RAM for `ram byte` variables
9. Use `ram` for large arrays (>16 bytes)
