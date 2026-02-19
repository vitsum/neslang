# NES Color Palette Reference

The NES PPU has a fixed palette of 64 colors (some duplicates).
Use these hex values with `color()`.

## Full Palette

```
      x0    x1    x2    x3    x4    x5    x6    x7    x8    x9    xA    xB    xC    xD
 0x | Gray  DkBlu DkBlu DkPur DkMag DkRed DkRed DkBrn DkOlv DkGrn DkGrn DkCyn DkCyn BLACK
 1x | Gray  Blue  Blue  Purpl Mag   Red   OranR Ornge Olive Green Green  Cyan  Cyan  DkGry
 2x | LGry  LBlu  Blue  LPur  Pink  LRed  Ornge Yellw LGrn  Green LGrn  LCyn  LBlu  DkGry
 3x | WHITE LBlu  LBlu  Lav   Pink  Pink  Peach LYel  LGrn  LGrn  Aqua  LCyn  LBlu  LGry
```

## Most Useful Colors

### Grayscale
| Code | Color |
|------|-------|
| `0x0F` | **Black** (use as BG) |
| `0x00` | Dark gray |
| `0x10` | Medium gray |
| `0x20` | Light gray |
| `0x30` | **White** |

### Reds & Warm
| Code | Color |
|------|-------|
| `0x06` | Dark red |
| `0x16` | **Red** |
| `0x26` | Light red / salmon |
| `0x36` | Peach / skin |
| `0x07` | Dark brown |
| `0x17` | Orange-red |
| `0x27` | **Orange** |
| `0x37` | Light yellow |
| `0x08` | Dark olive |
| `0x18` | Olive |
| `0x28` | **Yellow** |
| `0x38` | Light yellow |

### Blues
| Code | Color |
|------|-------|
| `0x01` | Dark blue (navy) |
| `0x02` | **Dark blue** |
| `0x11` | Medium blue |
| `0x12` | **Blue** |
| `0x21` | **Light blue** |
| `0x22` | Bright blue |
| `0x31` | Pale blue |
| `0x32` | Light blue |

### Greens
| Code | Color |
|------|-------|
| `0x09` | Dark green |
| `0x0A` | Dark green |
| `0x19` | Green |
| `0x1A` | Green |
| `0x2A` | **Bright green** |
| `0x29` | Yellow-green |
| `0x3A` | Pale green |

### Cyans & Purples
| Code | Color |
|------|-------|
| `0x0C` | Dark cyan |
| `0x1C` | Cyan |
| `0x2C` | **Light cyan** |
| `0x03` | Dark purple |
| `0x13` | Purple |
| `0x14` | Magenta |
| `0x24` | Pink |
| `0x34` | Light pink |

## Palette Design Tips

- First color in each BG palette is shared (universal background)
- Use `0x0F` (black) as universal background for night scenes
- Use `0x21` or `0x11` for sky/water
- Skin tones: `0x36` (light) or `0x27` (tanned)
- Use `0x10` (gray) for shadows and depth
- Keep outline colors darker than fill colors for readable sprites
