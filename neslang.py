#!/usr/bin/env python3
"""
NesLang — простой язык похожий на C# для создания NES-игр.
Компилирует .nsl файлы в .nes ROM через ca65/ld65.

Использование: python3 neslang.py game.nsl [-o game.nes]
"""

import sys, os, subprocess, tempfile
from fontdata import FONT_8X8, BOX_TILES
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict

# ======================== TOKENS ========================
class TT(Enum):
    NUMBER=auto(); IDENT=auto(); STRING=auto()
    BYTE=auto(); CONST=auto(); FUNC=auto(); IF=auto(); ELSE=auto()
    WHILE=auto(); RETURN=auto(); TRUE=auto(); FALSE=auto(); TILE=auto(); MUSIC=auto(); RAM=auto()
    PLUS=auto(); MINUS=auto(); STAR=auto(); AMP=auto(); PIPE=auto(); CARET=auto()
    TILDE=auto(); BANG=auto(); EQ=auto(); NEQ=auto()
    LT=auto(); GT=auto(); LTE=auto(); GTE=auto(); ASSIGN=auto()
    LPAREN=auto(); RPAREN=auto(); LBRACE=auto(); RBRACE=auto()
    LBRACKET=auto(); RBRACKET=auto(); SEMI=auto(); COMMA=auto()
    EOF=auto()

KEYWORDS = {
    'byte':TT.BYTE,'const':TT.CONST,'func':TT.FUNC,
    'if':TT.IF,'else':TT.ELSE,'while':TT.WHILE,
    'return':TT.RETURN,'true':TT.TRUE,'false':TT.FALSE,
    'tile':TT.TILE,'music':TT.MUSIC,'ram':TT.RAM,
}

@dataclass
class Token:
    type: TT; value: Any; line: int; col: int

# ======================== LEXER ========================
class LexError(Exception): pass

class Lexer:
    def __init__(self, src):
        self.src = src; self.pos = 0; self.line = 1; self.col = 1

    def error(self, msg): raise LexError(f"Строка {self.line}: {msg}")
    def peek(self): return self.src[self.pos] if self.pos < len(self.src) else '\0'
    def advance(self):
        ch = self.src[self.pos]; self.pos += 1
        if ch == '\n': self.line += 1; self.col = 1
        else: self.col += 1
        return ch

    def skip_ws(self):
        while self.pos < len(self.src):
            if self.src[self.pos] in ' \t\r\n':
                self.advance()
            elif self.pos+1 < len(self.src) and self.src[self.pos:self.pos+2] == '//':
                while self.pos < len(self.src) and self.src[self.pos] != '\n':
                    self.advance()
            else:
                break

    def read_number(self):
        ln, cl = self.line, self.col; s = ''
        if self.peek() == '0' and self.pos+1 < len(self.src) and self.src[self.pos+1] in 'xX':
            s += self.advance(); s += self.advance()
            while self.pos < len(self.src) and self.src[self.pos] in '0123456789abcdefABCDEF':
                s += self.advance()
            return Token(TT.NUMBER, int(s, 16), ln, cl)
        while self.pos < len(self.src) and self.src[self.pos].isdigit():
            s += self.advance()
        return Token(TT.NUMBER, int(s), ln, cl)

    def read_ident(self):
        ln, cl = self.line, self.col; s = ''
        while self.pos < len(self.src) and (self.src[self.pos].isalnum() or self.src[self.pos] == '_'):
            s += self.advance()
        tt = KEYWORDS.get(s, TT.IDENT)
        return Token(tt, s, ln, cl)

    def read_string(self):
        ln, cl = self.line, self.col
        self.advance()  # skip opening "
        s = ''
        while self.pos < len(self.src) and self.src[self.pos] != '"':
            s += self.advance()
        if self.pos >= len(self.src):
            self.error("Незакрытая строка")
        self.advance()  # skip closing "
        return Token(TT.STRING, s, ln, cl)

    def tokenize(self):
        toks = []
        SIMPLE = {
            '+':TT.PLUS,'-':TT.MINUS,'*':TT.STAR,'&':TT.AMP,'|':TT.PIPE,'^':TT.CARET,
            '~':TT.TILDE,'(':TT.LPAREN,')':TT.RPAREN,'{':TT.LBRACE,
            '}':TT.RBRACE,'[':TT.LBRACKET,']':TT.RBRACKET,';':TT.SEMI,',':TT.COMMA,
        }
        while True:
            self.skip_ws()
            if self.pos >= len(self.src): break
            ch = self.peek(); ln, cl = self.line, self.col
            if ch.isdigit():
                toks.append(self.read_number())
            elif ch.isalpha() or ch == '_':
                toks.append(self.read_ident())
            elif ch == '"':
                toks.append(self.read_string())
            elif ch in SIMPLE:
                self.advance(); toks.append(Token(SIMPLE[ch], ch, ln, cl))
            elif ch == '=':
                self.advance()
                if self.peek() == '=': self.advance(); toks.append(Token(TT.EQ,'==',ln,cl))
                else: toks.append(Token(TT.ASSIGN,'=',ln,cl))
            elif ch == '!':
                self.advance()
                if self.peek() == '=': self.advance(); toks.append(Token(TT.NEQ,'!=',ln,cl))
                else: toks.append(Token(TT.BANG,'!',ln,cl))
            elif ch == '<':
                self.advance()
                if self.peek() == '=': self.advance(); toks.append(Token(TT.LTE,'<=',ln,cl))
                else: toks.append(Token(TT.LT,'<',ln,cl))
            elif ch == '>':
                self.advance()
                if self.peek() == '=': self.advance(); toks.append(Token(TT.GTE,'>=',ln,cl))
                else: toks.append(Token(TT.GT,'>',ln,cl))
            else:
                self.error(f"Неожиданный символ: '{ch}'")
        toks.append(Token(TT.EOF, None, self.line, self.col))
        return toks

# ======================== AST NODES ========================
@dataclass
class Num:
    value: int
@dataclass
class Bool:
    value: bool
@dataclass
class Ident:
    name: str
@dataclass
class ArrayAccess:
    name: str; index: Any
@dataclass
class BinOp:
    op: str; left: Any; right: Any
@dataclass
class UnaryOp:
    op: str; operand: Any
@dataclass
class Call:
    name: str; args: list
@dataclass
class VarDecl:
    name: str; init: Any; ram: bool = False  # init can be None
@dataclass
class ConstDecl:
    name: str; value: int
@dataclass
class ArrayDecl:
    name: str; size: int; values: list; const: bool = False; ram: bool = False
@dataclass
class FuncDecl:
    name: str; params: list; body: list  # params = [(name, type_str)]
@dataclass
class Assign:
    name: str; value: Any
@dataclass
class ArrayAssign:
    name: str; index: Any; value: Any
@dataclass
class IfStmt:
    cond: Any; body: list; else_body: list  # else_body can be []
@dataclass
class WhileStmt:
    cond: Any; body: list
@dataclass
class ReturnStmt:
    value: Any  # can be None
@dataclass
class ExprStmt:
    expr: Any
@dataclass
class TileDecl:
    id: int; rows: list
@dataclass
class MusicDecl:
    filename: str
@dataclass
class StringLit:
    value: str  # rows = list of 8 strings, each 8 chars of .XO#

# ======================== PARSER ========================
class ParseError(Exception): pass

class Parser:
    def __init__(self, tokens):
        self.tokens = tokens; self.pos = 0

    def error(self, msg):
        t = self.cur()
        raise ParseError(f"Строка {t.line}: {msg} (получено '{t.value}')")

    def cur(self): return self.tokens[self.pos]
    def peek(self, tt): return self.cur().type == tt
    def at_end(self): return self.cur().type == TT.EOF

    def eat(self, tt):
        if self.cur().type != tt:
            self.error(f"Ожидался {tt.name}")
        t = self.cur(); self.pos += 1; return t

    def match(self, tt):
        if self.cur().type == tt:
            t = self.cur(); self.pos += 1; return t
        return None

    # ---- Top level ----
    def parse(self):
        decls = []
        while not self.at_end():
            decls.append(self.declaration())
        return decls

    def declaration(self):
        if self.peek(TT.FUNC): return self.func_decl()
        if self.peek(TT.CONST): return self.const_decl()
        if self.peek(TT.BYTE): return self.var_or_array_decl()
        if self.peek(TT.RAM): return self.ram_var_decl()
        if self.peek(TT.TILE): return self.tile_decl()
        if self.peek(TT.MUSIC): return self.music_decl()
        self.error("Ожидалось объявление (byte, const, func, tile, music, ram)")

    def const_decl(self):
        self.eat(TT.CONST); self.eat(TT.BYTE)
        name = self.eat(TT.IDENT).value
        self.eat(TT.ASSIGN)
        val = self.eat(TT.NUMBER).value
        self.eat(TT.SEMI)
        return ConstDecl(name, val)

    def tile_decl(self):
        self.eat(TT.TILE)
        tile_id = self.eat(TT.NUMBER).value
        self.eat(TT.ASSIGN)
        raw = self.eat(TT.STRING).value
        self.eat(TT.SEMI)
        # Parse rows from string
        lines = [l.strip() for l in raw.strip().split('\n') if l.strip()]
        if len(lines) != 8:
            self.error(f"Тайл должен содержать 8 строк, получено {len(lines)}")
        for i, line in enumerate(lines):
            if len(line) != 8:
                self.error(f"Строка {i+1} тайла должна быть 8 символов, получено {len(line)}")
        return TileDecl(tile_id, lines)

    def music_decl(self):
        self.eat(TT.MUSIC)
        filename = self.eat(TT.STRING).value
        self.eat(TT.SEMI)
        return MusicDecl(filename)

    def ram_var_decl(self, allow_local=False):
        self.eat(TT.RAM)
        return self.var_or_array_decl(allow_local=allow_local, is_ram=True)

    def var_or_array_decl(self, allow_local=False, is_ram=False):
        self.eat(TT.BYTE)
        if self.peek(TT.LBRACKET):
            self.eat(TT.LBRACKET)
            size = self.eat(TT.NUMBER).value
            self.eat(TT.RBRACKET)
            name = self.eat(TT.IDENT).value
            vals = []
            if self.match(TT.ASSIGN):
                self.eat(TT.LBRACE)
                vals.append(self.expression())
                while self.match(TT.COMMA):
                    vals.append(self.expression())
                self.eat(TT.RBRACE)
            self.eat(TT.SEMI)
            return ArrayDecl(name, size, vals, ram=is_ram)
        name = self.eat(TT.IDENT).value
        init = None
        if self.match(TT.ASSIGN):
            init = self.expression()
        self.eat(TT.SEMI)
        return VarDecl(name, init, ram=is_ram)

    def func_decl(self):
        self.eat(TT.FUNC)
        name = self.eat(TT.IDENT).value
        self.eat(TT.LPAREN)
        params = []
        if not self.peek(TT.RPAREN):
            self.eat(TT.BYTE)
            pname = self.eat(TT.IDENT).value
            params.append(pname)
            while self.match(TT.COMMA):
                self.eat(TT.BYTE)
                pname = self.eat(TT.IDENT).value
                params.append(pname)
        self.eat(TT.RPAREN)
        body = self.block()
        return FuncDecl(name, params, body)

    def block(self):
        self.eat(TT.LBRACE)
        stmts = []
        while not self.peek(TT.RBRACE):
            stmts.append(self.statement())
        self.eat(TT.RBRACE)
        return stmts

    def statement(self):
        if self.peek(TT.RAM): return self.ram_var_decl(allow_local=True)
        if self.peek(TT.BYTE): return self.var_or_array_decl(allow_local=True)
        if self.peek(TT.IF): return self.if_stmt()
        if self.peek(TT.WHILE): return self.while_stmt()
        if self.peek(TT.RETURN): return self.return_stmt()
        # Assignment or expression statement
        if self.peek(TT.IDENT) and self.pos+1 < len(self.tokens):
            next_t = self.tokens[self.pos+1]
            if next_t.type == TT.ASSIGN:
                name = self.eat(TT.IDENT).value
                self.eat(TT.ASSIGN)
                val = self.expression()
                self.eat(TT.SEMI)
                return Assign(name, val)
            if next_t.type == TT.LBRACKET:
                name = self.eat(TT.IDENT).value
                self.eat(TT.LBRACKET)
                idx = self.expression()
                self.eat(TT.RBRACKET)
                self.eat(TT.ASSIGN)
                val = self.expression()
                self.eat(TT.SEMI)
                return ArrayAssign(name, idx, val)
        expr = self.expression()
        self.eat(TT.SEMI)
        return ExprStmt(expr)

    def if_stmt(self):
        self.eat(TT.IF); self.eat(TT.LPAREN)
        cond = self.expression()
        self.eat(TT.RPAREN)
        body = self.block()
        else_body = []
        if self.match(TT.ELSE):
            else_body = self.block()
        return IfStmt(cond, body, else_body)

    def while_stmt(self):
        self.eat(TT.WHILE); self.eat(TT.LPAREN)
        cond = self.expression()
        self.eat(TT.RPAREN)
        body = self.block()
        return WhileStmt(cond, body)

    def return_stmt(self):
        self.eat(TT.RETURN)
        val = None
        if not self.peek(TT.SEMI):
            val = self.expression()
        self.eat(TT.SEMI)
        return ReturnStmt(val)

    # ---- Expressions (precedence climbing) ----
    def expression(self):  return self.or_expr()

    def or_expr(self):
        left = self.xor_expr()
        while self.match(TT.PIPE):
            left = BinOp('|', left, self.xor_expr())
        return left

    def xor_expr(self):
        left = self.and_expr()
        while self.match(TT.CARET):
            left = BinOp('^', left, self.and_expr())
        return left

    def and_expr(self):
        left = self.cmp_expr()
        while self.match(TT.AMP):
            left = BinOp('&', left, self.cmp_expr())
        return left

    def cmp_expr(self):
        left = self.add_expr()
        for tt, op in [(TT.EQ,'=='),(TT.NEQ,'!='),(TT.LT,'<'),(TT.GT,'>'),(TT.LTE,'<='),(TT.GTE,'>=')]:
            if self.match(tt):
                return BinOp(op, left, self.add_expr())
        return left

    def add_expr(self):
        left = self.mul_expr()
        while True:
            if self.match(TT.PLUS): left = BinOp('+', left, self.mul_expr())
            elif self.match(TT.MINUS): left = BinOp('-', left, self.mul_expr())
            else: break
        return left

    def mul_expr(self):
        left = self.unary()
        while self.match(TT.STAR):
            left = BinOp('*', left, self.unary())
        return left

    def unary(self):
        if self.match(TT.BANG): return UnaryOp('!', self.unary())
        if self.match(TT.TILDE): return UnaryOp('~', self.unary())
        return self.primary()

    def primary(self):
        if self.match(TT.TRUE): return Num(1)
        if self.match(TT.FALSE): return Num(0)
        t = self.match(TT.STRING)
        if t: return StringLit(t.value)
        t = self.match(TT.NUMBER)
        if t: return Num(t.value)
        if self.peek(TT.IDENT):
            name = self.eat(TT.IDENT).value
            if self.match(TT.LPAREN):  # function call
                args = []
                if not self.peek(TT.RPAREN):
                    args.append(self.expression())
                    while self.match(TT.COMMA):
                        args.append(self.expression())
                self.eat(TT.RPAREN)
                return Call(name, args)
            if self.match(TT.LBRACKET):  # array access
                idx = self.expression()
                self.eat(TT.RBRACKET)
                return ArrayAccess(name, idx)
            return Ident(name)
        if self.match(TT.LPAREN):
            expr = self.expression()
            self.eat(TT.RPAREN)
            return expr
        self.error("Ожидалось выражение")

# ======================== BUILT-IN CONSTANTS ========================
BUILTINS_CONST = {
    'BTN_A': 0x80, 'BTN_B': 0x40, 'BTN_SELECT': 0x20, 'BTN_START': 0x10,
    'BTN_UP': 0x08, 'BTN_DOWN': 0x04, 'BTN_LEFT': 0x02, 'BTN_RIGHT': 0x01,
}

BUILTIN_FUNCS = {
    'vblank', 'gamepad', 'sprite', 'hide_sprite',
    'ppu_on', 'ppu_off', 'color', 'scroll', 'play_note', 'noise',
    'set_tile', 'rand', 'enable_sound', 'silence',
    'bg_addr', 'bg_byte', 'bg_fill', 'bg_text', 'bg_attr',
    'sfx_pickup', 'sfx_hit', 'sfx_jump', 'sfx_explode',
    'music_init', 'music_tick',
}

# ======================== CODE GENERATOR ========================
class CodeGenError(Exception): pass

class CodeGen:
    def __init__(self, ast, source_path=None):
        self._source_path = source_path
        self.ast = ast
        self.lines = []         # output asm lines
        self.zp_vars = {}       # name -> zp_label
        self.zp_sizes = {}      # name -> size (bytes)
        self.zp_next = 0x20     # first free ZP address
        self.constants = {}     # name -> value
        self.constants.update(BUILTINS_CONST)
        self.arrays = {}        # name -> (label, size, is_const)
        self.ram_vars = {}      # name -> ram_label (BSS segment)
        self.ram_sizes = {}     # name -> size in bytes
        self.ram_next = 0       # offset counter for error reporting
        self.funcs = {}         # name -> FuncDecl
        self.tiles = {}         # id -> TileDecl
        self.label_cnt = 0
        self.rodata = []        # rodata lines
        self.music_data = None  # (zp_asm, code_asm, rodata_asm) from converter
        self.func_params = {}   # func_name -> [param_names]
        self.current_func = None

    def label(self, prefix='L'):
        self.label_cnt += 1
        return f"__{prefix}_{self.label_cnt}"

    def emit(self, s): self.lines.append(s)
    def emit_ro(self, s): self.rodata.append(s)

    def error(self, msg): raise CodeGenError(msg)

    def is_simple(self, node):
        return isinstance(node, (Num, Ident, Bool))

    def resolve(self, name):
        """Resolve a name to its asm representation"""
        if name in self.constants:
            return f"#{self.constants[name]}"
        if name in self.zp_vars:
            return self.zp_vars[name]
        if name in self.arrays:
            return self.arrays[name][0]
        self.error(f"Неизвестная переменная: {name}")

    def alloc_zp(self, name, count=1):
        if name in self.zp_vars or name in self.constants:
            self.error(f"Переменная '{name}' уже объявлена")
        lbl = f"_v_{name}"
        self.zp_vars[name] = lbl
        self.zp_sizes[name] = count
        self.zp_next += count
        return lbl

    def alloc_ram(self, name, count=1):
        if name in self.zp_vars or name in self.ram_vars or name in self.constants:
            self.error(f"Переменная '{name}' уже объявлена")
        lbl = f"_ram_{name}"
        self.ram_vars[name] = lbl
        self.ram_sizes[name] = count
        self.ram_next += count
        if self.ram_next > 0x500:  # $0300-$07FF = 1280 bytes
            self.error(f"Превышен лимит RAM (1280 байт). Используйте меньше ram-переменных.")
        return lbl

    # ---- Generate everything ----
    def generate(self):
        # First pass: collect declarations
        for node in self.ast:
            if isinstance(node, ConstDecl):
                self.constants[node.name] = node.value
            elif isinstance(node, FuncDecl):
                self.funcs[node.name] = node
                self.func_params[node.name] = node.params
            elif isinstance(node, VarDecl):
                if node.ram:
                    self.alloc_ram(node.name)
                else:
                    self.alloc_zp(node.name)
            elif isinstance(node, ArrayDecl):
                lbl = f"_arr_{node.name}"
                self.arrays[node.name] = (lbl, node.size, node.const)
                if not node.const:
                    if node.ram:
                        self.alloc_ram(node.name, node.size)
                    else:
                        self.alloc_zp(node.name, node.size)
            elif isinstance(node, TileDecl):
                self.tiles[node.id] = node
            elif isinstance(node, MusicDecl):
                self._load_music(node.filename)

        # Allocate ZP for function params
        for fname, params in self.func_params.items():
            for p in params:
                key = f"{fname}__{p}"
                if key not in self.zp_vars:
                    self.alloc_zp(key)

        # Temp vars for expression evaluation
        self.alloc_zp('__tmp0')
        self.alloc_zp('__tmp1')

        # Generate assembly
        self.emit_header()
        self.emit_zp_segment()
        self.emit_bss_segment()
        self.emit_code_segment()
        self.emit_rodata_segment()
        self.emit_vectors()
        self.emit_chr()

        return '\n'.join(self.lines)

    def _load_music(self, filename):
        """Load and convert FamiStudio music file."""
        import os
        from music_converter import generate_music_asm
        # Resolve filename relative to source file
        if not os.path.isabs(filename):
            base = os.path.dirname(os.path.abspath(self._source_path or ''))
            filepath = os.path.join(base, filename)
        else:
            filepath = filename
        with open(filepath, 'r') as f:
            text = f.read()
        self.music_data = generate_music_asm(text)

    def emit_header(self):
        self.emit('; === Generated by NesLang Compiler ===')
        self.emit('.segment "HEADER"')
        self.emit('    .byte "NES", $1A')
        self.emit('    .byte 2            ; 32KB PRG')
        self.emit('    .byte 1            ; 8KB CHR')
        self.emit('    .byte $01          ; mapper 0, vert mirror')
        self.emit('    .byte 0,0,0,0,0,0,0,0,0')
        self.emit('')

    def emit_zp_segment(self):
        self.emit('.segment "ZEROPAGE"')
        # System vars
        self.emit('__nmi_flag:  .res 1')
        self.emit('__pad1:      .res 1')
        self.emit('__pad2:      .res 1')
        self.emit('__scroll_x:  .res 1')
        self.emit('__scroll_y:  .res 1')
        self.emit('__rand_seed: .res 2')
        self.emit('__tmp0:      .res 1')
        self.emit('__tmp1:      .res 1')
        # Remove __tmp from user vars since we declared them manually
        if '__tmp0' in self.zp_vars: del self.zp_vars['__tmp0']
        if '__tmp1' in self.zp_vars: del self.zp_vars['__tmp1']
        # User vars
        for name, lbl in self.zp_vars.items():
            sz = self.zp_sizes.get(name, 1)
            self.emit(f'{lbl}: .res {sz}')
        # Music engine ZP vars
        if self.music_data:
            self.emit('')
            for line in self.music_data[0].split('\n'):
                self.emit(line)
            self.emit('')
        # Array vars in ZP
        for name, (lbl, size, is_const) in self.arrays.items():
            if not is_const:
                # Already allocated via alloc_zp, but we need to declare in ZP
                pass
        self.emit('')

    def emit_bss_segment(self):
        self.emit('.segment "BSS"')
        for name, lbl in self.ram_vars.items():
            sz = self.ram_sizes.get(name, 1)
            self.emit(f'{lbl}: .res {sz}')
        self.emit('')

    def emit_code_segment(self):
        self.emit('.segment "CODE"')
        self.emit('')
        self.emit_runtime()
        self.emit('')

        # Music engine code
        if self.music_data:
            self.emit('')
            for line in self.music_data[1].split('\n'):
                self.emit(line)
            self.emit('')

        # Generate user functions
        for name, func in self.funcs.items():
            if name == 'main':
                continue
            self.gen_func(func)

        # Generate main
        if 'main' not in self.funcs:
            self.error("Не найдена функция main()")
        self.gen_main(self.funcs['main'])

    def emit_runtime(self):
        self.emit('; === NES Runtime ===')
        self.emit('reset:')
        self.emit('    sei')
        self.emit('    cld')
        self.emit('    ldx #$40')
        self.emit('    stx $4017')
        self.emit('    ldx #$FF')
        self.emit('    txs')
        self.emit('    lda #0')
        self.emit('    sta $2000')
        self.emit('    sta $2001')
        self.emit('    sta $4010')
        self.emit('    sta $4015       ; disable all sound channels at boot')
        self.emit('@vb1:')
        self.emit('    bit $2002')
        self.emit('    bpl @vb1')
        self.emit('    ldx #0')
        self.emit('    lda #0')
        self.emit('@clr:')
        self.emit('    sta $000,x')
        self.emit('    sta $100,x')
        self.emit('    sta $200,x')
        self.emit('    sta $300,x')
        self.emit('    sta $400,x')
        self.emit('    sta $500,x')
        self.emit('    sta $600,x')
        self.emit('    sta $700,x')
        self.emit('    inx')
        self.emit('    bne @clr')
        # Init sprites to offscreen
        self.emit('    lda #$FF')
        self.emit('    ldx #0')
        self.emit('@clr_oam:')
        self.emit('    sta $0200,x')
        self.emit('    inx')
        self.emit('    bne @clr_oam')
        self.emit('@vb2:')
        self.emit('    bit $2002')
        self.emit('    bpl @vb2')
        # Init random seed
        self.emit('    lda #$A7')
        self.emit('    sta __rand_seed')
        self.emit('    lda #$3B')
        self.emit('    sta __rand_seed+1')
        # Init global vars (ZP and RAM)
        for node in self.ast:
            if isinstance(node, VarDecl) and node.init is not None:
                if isinstance(node.init, Num):
                    self.emit(f'    lda #{node.init.value}')
                    if node.ram:
                        self.emit(f'    sta {self.ram_vars[node.name]}')
                    else:
                        self.emit(f'    sta {self.zp_vars[node.name]}')
            if isinstance(node, ArrayDecl) and node.values and not node.const:
                for i, v in enumerate(node.values):
                    if isinstance(v, Num):
                        self.emit(f'    lda #{v.value}')
                        if node.ram:
                            self.emit(f'    sta {self.ram_vars[node.name]}+{i}')
                        else:
                            self.emit(f'    sta {self.zp_vars[node.name]}+{i}')
        self.emit('    jmp _user_main')
        self.emit('')

        # NMI handler
        self.emit('nmi:')
        self.emit('    pha')
        self.emit('    txa')
        self.emit('    pha')
        self.emit('    tya')
        self.emit('    pha')
        # OAM DMA
        self.emit('    lda #$00')
        self.emit('    sta $2003')
        self.emit('    lda #$02')
        self.emit('    sta $4014')
        # Reset scroll after DMA (critical!)')
        self.emit('    lda #%10000000')
        self.emit('    sta $2000')
        self.emit('    bit $2002')
        self.emit('    lda __scroll_x')
        self.emit('    sta $2005')
        self.emit('    lda __scroll_y')
        self.emit('    sta $2005')
        # Read controllers
        self.emit('    jsr __read_pads')
        # Set NMI flag
        self.emit('    lda #1')
        self.emit('    sta __nmi_flag')
        self.emit('    pla')
        self.emit('    tay')
        self.emit('    pla')
        self.emit('    tax')
        self.emit('    pla')
        self.emit('    rti')
        self.emit('')

        # IRQ
        self.emit('irq:')
        self.emit('    rti')
        self.emit('')

        # Read controllers
        self.emit('__read_pads:')
        self.emit('    lda #1')
        self.emit('    sta $4016')
        self.emit('    lda #0')
        self.emit('    sta $4016')
        self.emit('    ldx #8')
        self.emit('    lda #0')
        self.emit('    sta __pad1')
        self.emit('@rd1:')
        self.emit('    lda $4016')
        self.emit('    lsr a')
        self.emit('    rol __pad1')
        self.emit('    dex')
        self.emit('    bne @rd1')
        self.emit('    ldx #8')
        self.emit('    lda #0')
        self.emit('    sta __pad2')
        self.emit('@rd2:')
        self.emit('    lda $4017')
        self.emit('    lsr a')
        self.emit('    rol __pad2')
        self.emit('    dex')
        self.emit('    bne @rd2')
        self.emit('    rts')
        self.emit('')

        # vblank wait
        self.emit('__vblank_wait:')
        self.emit('    lda #0')
        self.emit('    sta __nmi_flag')
        self.emit('@wait:')
        self.emit('    lda __nmi_flag')
        self.emit('    beq @wait')
        self.emit('    rts')
        self.emit('')

        # set_sprite: X=id*4, A=Y, then store
        self.emit('__set_sprite:')
        self.emit('    ; params: __tmp_spr_id, __tmp_spr_x, __tmp_spr_y, __tmp_spr_tile, __tmp_spr_attr')
        self.emit('    lda __tmp_spr_id')
        self.emit('    asl a')
        self.emit('    asl a')
        self.emit('    tax')
        self.emit('    lda __tmp_spr_y')
        self.emit('    sta $0200,x')
        self.emit('    lda __tmp_spr_tile')
        self.emit('    sta $0201,x')
        self.emit('    lda __tmp_spr_attr')
        self.emit('    sta $0202,x')
        self.emit('    lda __tmp_spr_x')
        self.emit('    sta $0203,x')
        self.emit('    rts')
        self.emit('')

        # Random number generator (8-bit LFSR)
        self.emit('__rand:')
        self.emit('    lda __rand_seed')
        self.emit('    asl a')
        self.emit('    rol __rand_seed+1')
        self.emit('    bcc @no_eor')
        self.emit('    eor #$2D')
        self.emit('@no_eor:')
        self.emit('    sta __rand_seed')
        self.emit('    rts')
        self.emit('')

        # 8-bit unsigned multiply: __tmp0 * __tmp1 -> A (low byte)
        self.emit('__mul8:')
        self.emit('    lda #0')
        self.emit('    ldx #8')
        self.emit('@mul_loop:')
        self.emit('    lsr __tmp1')
        self.emit('    bcc @mul_skip')
        self.emit('    clc')
        self.emit('    adc __tmp0')
        self.emit('@mul_skip:')
        self.emit('    asl __tmp0')
        self.emit('    dex')
        self.emit('    bne @mul_loop')
        self.emit('    rts')
        self.emit('')


        # BG helper ZP vars
        self.emit('.segment "ZEROPAGE"')
        self.emit('__bg_x:    .res 1')
        self.emit('__bg_y:    .res 1')
        self.emit('__bg_hi:   .res 1')
        self.emit('__bg_lo:   .res 1')
        self.emit('.segment "CODE"')
        self.emit('')
        
        # bg_addr subroutine: set PPU address from __bg_x, __bg_y
        self.emit('__bg_addr_sub:')
        self.emit('    bit $2002')
        self.emit('    lda __bg_y')
        self.emit('    lsr a')
        self.emit('    lsr a')
        self.emit('    lsr a')
        self.emit('    clc')
        self.emit('    adc #$20')
        self.emit('    sta $2006')
        self.emit('    lda __bg_y')
        self.emit('    and #$07')
        self.emit('    asl a')
        self.emit('    asl a')
        self.emit('    asl a')
        self.emit('    asl a')
        self.emit('    asl a')
        self.emit('    ora __bg_x')
        self.emit('    sta $2006')
        self.emit('    rts')
        self.emit('')
        # Extra ZP for sprite params
        self.emit('.segment "ZEROPAGE"')
        self.emit('__tmp_spr_id:   .res 1')
        self.emit('__tmp_spr_x:    .res 1')
        self.emit('__tmp_spr_y:    .res 1')
        self.emit('__tmp_spr_tile: .res 1')
        self.emit('__tmp_spr_attr: .res 1')
        self.emit('.segment "CODE"')
        self.emit('')

    def gen_func(self, func):
        self.current_func = func.name
        self.emit(f'_func_{func.name}:')
        for stmt in func.body:
            self.gen_stmt(stmt)
        self.emit('    rts')
        self.emit('')
        self.current_func = None

    def gen_main(self, func):
        self.current_func = 'main'
        self.emit('_user_main:')
        for stmt in func.body:
            self.gen_stmt(stmt)
        self.emit('    jmp _user_main  ; loop forever if main ends')
        self.emit('')
        self.current_func = None

    # ---- Statement generation ----
    def gen_stmt(self, node):
        if isinstance(node, VarDecl):
            if node.ram:
                if node.name not in self.ram_vars:
                    self.alloc_ram(node.name)
                    self.emit(f'.segment "BSS"')
                    self.emit(f'{self.ram_vars[node.name]}: .res 1')
                    self.emit(f'.segment "CODE"')
                if node.init is not None:
                    self.gen_expr(node.init)
                    self.emit(f'    sta {self.ram_vars[node.name]}')
            else:
                if node.name not in self.zp_vars:
                    self.alloc_zp(node.name)
                    self.emit(f'.segment "ZEROPAGE"')
                    self.emit(f'{self.zp_vars[node.name]}: .res 1')
                    self.emit(f'.segment "CODE"')
                if node.init is not None:
                    self.gen_expr(node.init)
                    self.emit(f'    sta {self.zp_vars[node.name]}')
        elif isinstance(node, ArrayDecl):
            if node.ram and not node.const:
                if node.name not in self.ram_vars:
                    self.alloc_ram(node.name, node.size)
                    self.emit(f'.segment "BSS"')
                    self.emit(f'{self.ram_vars[node.name]}: .res {node.size}')
                    self.emit(f'.segment "CODE"')
                if node.values:
                    for i, v in enumerate(node.values):
                        self.gen_expr(v)
                        self.emit(f'    sta {self.ram_vars[node.name]}+{i}')
            elif not node.const:
                if node.name not in self.zp_vars:
                    self.alloc_zp(node.name, node.size)
                    self.emit(f'.segment "ZEROPAGE"')
                    self.emit(f'{self.zp_vars[node.name]}: .res {node.size}')
                    self.emit(f'.segment "CODE"')
                if node.values:
                    for i, v in enumerate(node.values):
                        self.gen_expr(v)
                        self.emit(f'    sta {self.zp_vars[node.name]}+{i}')
        elif isinstance(node, Assign):
            self.gen_expr(node.value)
            var = self.resolve_var(node.name)
            self.emit(f'    sta {var}')
        elif isinstance(node, ArrayAssign):
            self.gen_expr(node.index)
            self.emit('    pha')
            self.gen_expr(node.value)
            self.emit('    sta __tmp1')
            self.emit('    pla')
            self.emit('    tax')
            self.emit('    lda __tmp1')
            arr_label = self.resolve_arr(node.name)
            self.emit(f'    sta {arr_label},x')
        elif isinstance(node, IfStmt):
            self.gen_if(node)
        elif isinstance(node, WhileStmt):
            self.gen_while(node)
        elif isinstance(node, ReturnStmt):
            if node.value is not None:
                self.gen_expr(node.value)
            self.emit('    rts')
        elif isinstance(node, ExprStmt):
            self.gen_expr(node.expr)

    def resolve_var(self, name):
        if name in self.zp_vars:
            return self.zp_vars[name]
        if name in self.ram_vars:
            return self.ram_vars[name]
        # Check if it's a function param
        if self.current_func:
            key = f"{self.current_func}__{name}"
            if key in self.zp_vars:
                return self.zp_vars[key]
        self.error(f"Неизвестная переменная: {name}")

    def resolve_arr(self, name):
        if name in self.zp_vars:
            return self.zp_vars[name]
        if name in self.ram_vars:
            return self.ram_vars[name]
        if name in self.arrays:
            return self.arrays[name][0]
        self.error(f"Неизвестный массив: {name}")

    def gen_if(self, node):
        else_lbl = self.label('else')
        end_lbl = self.label('endif')

        if node.else_body:
            self.gen_condition(node.cond, else_lbl)
            for s in node.body:
                self.gen_stmt(s)
            self.emit(f'    jmp {end_lbl}')
            self.emit(f'{else_lbl}:')
            for s in node.else_body:
                self.gen_stmt(s)
            self.emit(f'{end_lbl}:')
        else:
            self.gen_condition(node.cond, end_lbl)
            for s in node.body:
                self.gen_stmt(s)
            self.emit(f'{end_lbl}:')

    def gen_while(self, node):
        loop_lbl = self.label('loop')
        end_lbl = self.label('endloop')
        self.emit(f'{loop_lbl}:')
        self.gen_condition(node.cond, end_lbl)
        for s in node.body:
            self.gen_stmt(s)
        self.emit(f'    jmp {loop_lbl}')
        self.emit(f'{end_lbl}:')

    def emit_far_branch(self, branch_if_true, skip_label):
        """Emit inverted short branch over a JMP for safe far jumps.
        branch_if_true = asm branch mnemonic for the TRUE case (don't skip).
        We branch over the JMP if condition is TRUE, otherwise fall through to JMP."""
        ok = self.label('br')
        self.emit(f'    {branch_if_true} {ok}')
        self.emit(f'    jmp {skip_label}')
        self.emit(f'{ok}:')

    def gen_condition(self, node, skip_label):
        """Generate code that jumps to skip_label if condition is FALSE"""
        if isinstance(node, BinOp) and node.op in ('==','!=','<','>','<=','>='):
            self.gen_expr(node.left)
            if self.is_simple(node.right):
                operand = self.simple_operand(node.right)
                self.emit(f'    cmp {operand}')
            else:
                self.emit('    pha')
                self.gen_expr(node.right)
                self.emit('    sta __tmp0')
                self.emit('    pla')
                self.emit('    cmp __tmp0')
            # Branch: skip_label = jump here if condition FALSE
            # We invert the condition: branch over JMP if TRUE, JMP if FALSE
            if node.op == '==':
                self.emit_far_branch('beq', skip_label)  # skip if NOT equal
            elif node.op == '!=':
                self.emit_far_branch('bne', skip_label)  # skip if equal
            elif node.op == '<':
                self.emit_far_branch('bcc', skip_label)  # skip if >= (carry set)
            elif node.op == '>=':
                self.emit_far_branch('bcs', skip_label)  # skip if < (carry clear)
            elif node.op == '>':
                # a > b: TRUE if C=1 and Z=0
                # FALSE if C=0 (a<b) or Z=1 (a==b)
                ok_lbl = self.label('gt')
                end_lbl = self.label('gtok')
                self.emit(f'    beq {ok_lbl}')    # a == b -> FALSE
                self.emit(f'    bcs {end_lbl}')   # a > b -> TRUE (skip JMP)
                self.emit(f'{ok_lbl}:')
                self.emit(f'    jmp {skip_label}') # FALSE
                self.emit(f'{end_lbl}:')
            elif node.op == '<=':
                # a <= b: TRUE if C=0 OR Z=1
                ok_lbl = self.label('le')
                self.emit(f'    bcc {ok_lbl}')    # a < b -> TRUE
                self.emit(f'    beq {ok_lbl}')    # a == b -> TRUE
                self.emit(f'    jmp {skip_label}') # a > b -> FALSE
                self.emit(f'{ok_lbl}:')
        elif isinstance(node, Num):
            if node.value == 0:
                self.emit(f'    jmp {skip_label}')
        elif isinstance(node, BinOp) and node.op == '&':
            self.gen_expr(node.left)
            if self.is_simple(node.right):
                operand = self.simple_operand(node.right)
                self.emit(f'    and {operand}')
            else:
                self.emit('    pha')
                self.gen_expr(node.right)
                self.emit('    sta __tmp0')
                self.emit('    pla')
                self.emit('    and __tmp0')
            self.emit_far_branch('bne', skip_label)  # skip if result == 0
        else:
            self.gen_expr(node)
            self.emit(f'    cmp #0')
            self.emit_far_branch('bne', skip_label)  # skip if A == 0

    def simple_operand(self, node):
        if isinstance(node, Num):
            return f'#{node.value}'
        if isinstance(node, Ident):
            if node.name in self.constants:
                return f'#{self.constants[node.name]}'
            return self.resolve_var(node.name)
        self.error("Не простой операнд")

    # ---- Expression generation (result in A) ----
    def gen_expr(self, node):
        if isinstance(node, Num):
            self.emit(f'    lda #{node.value & 0xFF}')
        elif isinstance(node, Ident):
            if node.name in self.constants:
                self.emit(f'    lda #{self.constants[node.name]}')
            else:
                var = self.resolve_var(node.name)
                self.emit(f'    lda {var}')
        elif isinstance(node, ArrayAccess):
            self.gen_expr(node.index)
            self.emit('    tax')
            arr = self.resolve_arr(node.name)
            self.emit(f'    lda {arr},x')
        elif isinstance(node, BinOp):
            self.gen_binop(node)
        elif isinstance(node, UnaryOp):
            self.gen_expr(node.operand)
            if node.op == '~':
                self.emit('    eor #$FF')
            elif node.op == '!':
                # logical not: if A==0 -> A=1, else A=0
                lbl_z = self.label('notz')
                lbl_e = self.label('note')
                self.emit(f'    cmp #0')
                self.emit(f'    bne {lbl_z}')
                self.emit(f'    lda #1')
                self.emit(f'    jmp {lbl_e}')
                self.emit(f'{lbl_z}:')
                self.emit(f'    lda #0')
                self.emit(f'{lbl_e}:')
        elif isinstance(node, Call):
            self.gen_call(node)
        else:
            self.error(f"Неизвестный узел выражения: {type(node)}")

    def gen_binop(self, node):
        op = node.op
        # Multiplication uses __mul8 subroutine
        if op == '*':
            self.gen_expr(node.left)
            self.emit('    sta __tmp0')
            self.gen_expr(node.right)
            self.emit('    sta __tmp1')
            self.emit('    jsr __mul8')
            return
        if self.is_simple(node.right):
            self.gen_expr(node.left)
            operand = self.simple_operand(node.right)
            if op == '+':   self.emit('    clc'); self.emit(f'    adc {operand}')
            elif op == '-': self.emit('    sec'); self.emit(f'    sbc {operand}')
            elif op == '&': self.emit(f'    and {operand}')
            elif op == '|': self.emit(f'    ora {operand}')
            elif op == '^': self.emit(f'    eor {operand}')
            elif op in ('==','!=','<','>','<=','>='):
                self.gen_comparison_to_value(op, operand)
        else:
            self.gen_expr(node.left)
            self.emit('    pha')
            self.gen_expr(node.right)
            self.emit('    sta __tmp0')
            self.emit('    pla')
            if op == '+':   self.emit('    clc'); self.emit('    adc __tmp0')
            elif op == '-': self.emit('    sec'); self.emit('    sbc __tmp0')
            elif op == '&': self.emit('    and __tmp0')
            elif op == '|': self.emit('    ora __tmp0')
            elif op == '^': self.emit('    eor __tmp0')
            elif op in ('==','!=','<','>','<=','>='):
                self.gen_comparison_to_value(op, '__tmp0')

    def gen_comparison_to_value(self, op, operand):
        """After LDA left, compare with operand and set A to 0 or 1"""
        lbl_t = self.label('cmpt')
        lbl_e = self.label('cmpe')
        self.emit(f'    cmp {operand}')
        if op == '==':
            self.emit(f'    beq {lbl_t}')
        elif op == '!=':
            self.emit(f'    bne {lbl_t}')
        elif op == '<':
            self.emit(f'    bcc {lbl_t}')
        elif op == '>=':
            self.emit(f'    bcs {lbl_t}')
        elif op == '>':
            self.emit(f'    beq {lbl_e}')
            self.emit(f'    bcs {lbl_t}')
        elif op == '<=':
            self.emit(f'    beq {lbl_t}')
            self.emit(f'    bcc {lbl_t}')
        # false path
        self.emit(f'    lda #0')
        self.emit(f'    jmp {lbl_e}')
        self.emit(f'{lbl_t}:')
        self.emit(f'    lda #1')
        self.emit(f'{lbl_e}:')

    def gen_call(self, node):
        name = node.name
        args = node.args

        if name == 'vblank':
            self.emit('    jsr __vblank_wait')
        elif name == 'gamepad':
            port = args[0] if args else Num(0)
            if isinstance(port, Num) and port.value == 0:
                self.emit('    lda __pad1')
            elif isinstance(port, Num) and port.value == 1:
                self.emit('    lda __pad2')
            else:
                self.gen_expr(port)
                lbl = self.label('gp')
                self.emit('    cmp #0')
                self.emit(f'    bne {lbl}')
                self.emit('    lda __pad1')
                lbl2 = self.label('gpd')
                self.emit(f'    jmp {lbl2}')
                self.emit(f'{lbl}:')
                self.emit('    lda __pad2')
                self.emit(f'{lbl2}:')
        elif name == 'sprite':
            if len(args) != 5:
                self.error("sprite() принимает 5 аргументов: id, x, y, tile, attr")
            self.gen_expr(args[0]); self.emit('    sta __tmp_spr_id')
            self.gen_expr(args[1]); self.emit('    sta __tmp_spr_x')
            self.gen_expr(args[2]); self.emit('    sta __tmp_spr_y')
            self.gen_expr(args[3]); self.emit('    sta __tmp_spr_tile')
            self.gen_expr(args[4]); self.emit('    sta __tmp_spr_attr')
            self.emit('    jsr __set_sprite')
        elif name == 'hide_sprite':
            self.gen_expr(args[0])
            self.emit('    asl a')
            self.emit('    asl a')
            self.emit('    tax')
            self.emit('    lda #$FF')
            self.emit('    sta $0200,x')
        elif name == 'ppu_on':
            self.emit('    lda #0')
            self.emit('    sta __scroll_x')
            self.emit('    sta __scroll_y')
            self.emit('    lda #%10000000  ; NMI on, bg+spr at $0000')
            self.emit('    sta $2000')
            self.emit('    lda #%00011110  ; show bg+sprites')
            self.emit('    sta $2001')
            self.emit('    ; reset scroll')
            self.emit('    bit $2002')
            self.emit('    lda #0')
            self.emit('    sta $2005')
            self.emit('    sta $2005')
        elif name == 'ppu_off':
            self.emit('    lda #%00000000')
            self.emit('    sta $2000')
            self.emit('    sta $2001')
        elif name == 'color':
            if len(args) != 5:
                self.error("color() принимает 5 аргументов: index, c0, c1, c2, c3")
            # Write palette during safe time
            self.emit('    bit $2002')
            self.emit('    lda #$3F')
            self.emit('    sta $2006')
            self.gen_expr(args[0])
            self.emit('    sta $2006')
            for i in range(1, 5):
                self.gen_expr(args[i])
                self.emit('    sta $2007')
            # Reset scroll
            self.emit('    bit $2002')
            self.emit('    lda #0')
            self.emit('    sta $2005')
            self.emit('    sta $2005')
        elif name == 'scroll':
            self.gen_expr(args[0])
            self.emit('    sta __scroll_x')
            self.gen_expr(args[1])
            self.emit('    sta __scroll_y')
        elif name == 'play_note':
            # play_note(channel, timer_lo, timer_hi, volume)
            if len(args) != 4:
                self.error("play_note() принимает 4 аргумента: channel, lo, hi, vol")
            self.gen_expr(args[0])
            self.emit('    asl a')
            self.emit('    asl a')
            self.emit('    tax')
            self.gen_expr(args[3])
            self.emit('    and #$0F')
            self.emit('    ora #%10010000  ; duty 50%, length counter ON, constant vol')
            self.emit('    sta $4000,x')
            self.emit('    lda #0')
            self.emit('    sta $4001,x')
            self.gen_expr(args[1])
            self.emit('    sta $4002,x')
            self.gen_expr(args[2])
            self.emit('    and #$07       ; keep timer high bits only')
            self.emit('    sta $4003,x    ; length index 0 = 10 frames')
        elif name == 'noise':
            # noise(period, volume)
            if len(args) < 2:
                self.error("noise() принимает минимум 2 аргумента: period, volume")
            self.gen_expr(args[1])
            self.emit('    and #$0F')
            self.emit('    ora #%00010000  ; constant vol, length counter ON')
            self.emit('    sta $400C')
            self.gen_expr(args[0])
            self.emit('    sta $400E')
            self.emit('    lda #%00000000  ; length index 0 = 10 frames')
            self.emit('    sta $400F')
        elif name == 'rand':
            self.emit('    jsr __rand')
        elif name == 'enable_sound':
            self.emit('    lda #$0F')
            self.emit('    sta $4015')
            # Silence all channels so they don\'t whine')
            self.emit('    lda #%00110000  ; vol=0, constant, halt')
            self.emit('    sta $4000       ; pulse 1 silent')
            self.emit('    sta $4004       ; pulse 2 silent')
            self.emit('    sta $400C       ; noise silent')
            self.emit('    lda #$00')
            self.emit('    sta $4008       ; triangle silent')
            self.emit('    lda #$00')
            self.emit('    sta $4001       ; no sweep')
            self.emit('    sta $4005       ; no sweep')
        elif name == 'bg_addr':
            # bg_addr(x, y) - set PPU address for background write
            if len(args) != 2:
                self.error("bg_addr() принимает 2 аргумента: x, y")
            self.gen_expr(args[0])
            self.emit('    sta __bg_x')
            self.gen_expr(args[1])
            self.emit('    sta __bg_y')
            self.emit('    jsr __bg_addr_sub')
        elif name == 'bg_byte':
            # bg_byte(tile) - write one byte to PPU $2007
            self.gen_expr(args[0])
            self.emit('    sta $2007')
        elif name == 'bg_fill':
            # bg_fill(tile, count) - write tile N times to PPU
            if len(args) != 2:
                self.error("bg_fill() принимает 2 аргумента: tile, count")
            self.gen_expr(args[1])
            self.emit('    tax')
            self.gen_expr(args[0])
            self.emit('    sta __tmp0')
            lbl = self.label('bgf')
            self.emit(f'{lbl}:')
            self.emit('    lda __tmp0')
            self.emit('    sta $2007')
            self.emit('    dex')
            self.emit(f'    bne {lbl}')
        elif name == 'bg_text':
            # bg_text(x, y, "string") - write string to background
            if len(args) != 3:
                self.error("bg_text() принимает 3 аргумента: x, y, \"строка\"")
            self.gen_expr(args[0])
            self.emit('    sta __bg_x')
            self.gen_expr(args[1])
            self.emit('    sta __bg_y')
            self.emit('    jsr __bg_addr_sub')
            # The third arg should be a StringLit
            if isinstance(args[2], StringLit):
                for ch in args[2].value:
                    code = ord(ch) if 32 <= ord(ch) <= 90 else 32
                    # Support lowercase by converting to upper
                    if 97 <= ord(ch) <= 122:
                        code = ord(ch) - 32
                    self.emit(f'    lda #${code:02X}  ; \'{ch}\'')
                    self.emit('    sta $2007')
            else:
                self.error("bg_text() третий аргумент должен быть строкой")
        elif name == 'bg_attr':
            # bg_attr(ax, ay, value) - write to attribute table
            # Attr table at $23C0, each byte covers 4x4 tiles
            # addr = $23C0 + ay*8 + ax
            if len(args) != 3:
                self.error("bg_attr() принимает 3 аргумента: ax, ay, value")
            self.emit('    bit $2002')
            self.emit('    lda #$23')
            self.emit('    sta $2006')
            # Calculate $C0 + ay*8 + ax
            self.gen_expr(args[1])
            self.emit('    asl a')
            self.emit('    asl a')
            self.emit('    asl a')
            self.emit('    sta __tmp0')
            self.gen_expr(args[0])
            self.emit('    clc')
            self.emit('    adc __tmp0')
            self.emit('    clc')
            self.emit('    adc #$C0')
            self.emit('    sta $2006')
            self.gen_expr(args[2])
            self.emit('    sta $2007')
        elif name == 'silence':
            self.emit('    lda #%00110000')
            self.emit('    sta $4000')
            self.emit('    sta $4004')
            self.emit('    sta $400C')
            self.emit('    lda #$00')
            self.emit('    sta $4008')
        elif name == 'sfx_pickup':
            # Short ascending chirp on pulse 1
            self.emit('    lda #%10010111  ; duty 50%, vol 7')
            self.emit('    sta $4000')
            self.emit('    lda #%10001110  ; sweep: enable, period 0, shift 6, up')
            self.emit('    sta $4001')
            self.emit('    lda #$80       ; timer = ~$080 (mid pitch)')
            self.emit('    sta $4002')
            self.emit('    lda #$00       ; timer hi + length idx 0 (10 frames)')
            self.emit('    sta $4003')
        elif name == 'sfx_hit':
            # Short noise burst
            self.emit('    lda #%00010111  ; noise vol 7, length counter on')
            self.emit('    sta $400C')
            self.emit('    lda #$04       ; mid-frequency noise')
            self.emit('    sta $400E')
            self.emit('    lda #$00       ; length idx 0 = 10 frames')
            self.emit('    sta $400F')
        elif name == 'sfx_jump':
            # Quick sweep-up on pulse 1
            self.emit('    lda #%10010110  ; duty 50%, vol 6')
            self.emit('    sta $4000')
            self.emit('    lda #%10000101  ; sweep: enable, period 0, shift 5, up')
            self.emit('    sta $4001')
            self.emit('    lda #$00       ; timer = ~$100 (low start)')
            self.emit('    sta $4002')
            self.emit('    lda #$01       ; timer hi=1, length idx 0')
            self.emit('    sta $4003')
        elif name == 'sfx_explode':
            # Long low noise
            self.emit('    lda #%00011111  ; noise vol 15, length on')
            self.emit('    sta $400C')
            self.emit('    lda #$08       ; low-frequency noise')
            self.emit('    sta $400E')
            self.emit('    lda #$10       ; length idx 2 = 20 frames')
            self.emit('    sta $400F')
        elif name == 'music_init':
            if not self.music_data:
                self.error("music_init() вызвана, но music не загружена. Добавьте: music \"file.txt\";")
            self.emit('    jsr __music_init')
        elif name == 'music_tick':
            if not self.music_data:
                self.error("music_tick() вызвана, но music не загружена. Добавьте: music \"file.txt\";")
            self.emit('    jsr __music_tick')
        else:
            # User function call
            if name not in self.funcs:
                self.error(f"Неизвестная функция: {name}")
            func = self.funcs[name]
            if len(args) != len(func.params):
                self.error(f"{name}() принимает {len(func.params)} аргументов")
            for i, arg in enumerate(args):
                pkey = f"{name}__{func.params[i]}"
                self.gen_expr(arg)
                self.emit(f'    sta {self.zp_vars[pkey]}')
            self.emit(f'    jsr _func_{name}')

    def emit_rodata_segment(self):
        self.emit('')
        self.emit('.segment "RODATA"')
        # Const arrays
        for node in self.ast:
            if isinstance(node, ArrayDecl) and node.const:
                lbl = self.arrays[node.name][0]
                vals = ', '.join(str(v.value if isinstance(v, Num) else 0) for v in node.values)
                self.emit(f'{lbl}: .byte {vals}')
        for line in self.rodata:
            self.emit(line)
        # Music data tables
        if self.music_data:
            self.emit('')
            for line in self.music_data[2].split('\n'):
                self.emit(line)
        self.emit('')

    def emit_vectors(self):
        self.emit('.segment "VECTORS"')
        self.emit('    .word nmi')
        self.emit('    .word reset')
        self.emit('    .word irq')
        self.emit('')

    def tile_rows_to_bytes(self, rows):
        """Convert 8 rows of '.XO#' strings into 16 NES tile bytes (plane0 + plane1)"""
        PIXEL_MAP = {'.': 0, ' ': 0, 'X': 1, '1': 1, 'O': 2, '2': 2, '#': 3, '3': 3}
        plane0 = []
        plane1 = []
        for row in rows:
            b0 = 0; b1 = 0
            for i, ch in enumerate(row[:8]):
                val = PIXEL_MAP.get(ch, 0)
                bit = 7 - i
                if val & 1: b0 |= (1 << bit)
                if val & 2: b1 |= (1 << bit)
            plane0.append(b0)
            plane1.append(b1)
        return plane0 + plane1

    def font_char_to_bytes(self, char_data):
        """Convert 8-byte font data to 16-byte NES tile (plane0 = data, plane1 = 0)"""
        return char_data + [0]*8  # plane0 = font data, plane1 = all zeros (color 1 only)

    def emit_chr(self):
        self.emit('.segment "CHARS"')
        
        # We need tiles 0-90 minimum (0=empty, 1-15=box drawing, 32-90=font)
        max_tile_id = max(
            max(self.tiles.keys()) if self.tiles else 0,
            90  # ASCII 'Z'
        )
        
        tiles_emitted = 0
        for tid in range(max_tile_id + 1):
            if tid in self.tiles:
                # User-defined tile
                rows = self.tiles[tid].rows
                tile_bytes = self.tile_rows_to_bytes(rows)
                self.emit(f'; Tile {tid} (user)')
            elif tid in BOX_TILES and tid >= 1 and tid <= 15:
                # Box drawing
                rows = BOX_TILES[tid]
                tile_bytes = self.tile_rows_to_bytes(rows)
                self.emit(f'; Tile {tid} (box)')
            elif tid in FONT_8X8:
                # Font character
                ch = chr(tid) if 32 <= tid <= 126 else '?'
                tile_bytes = self.font_char_to_bytes(FONT_8X8[tid])
                self.emit(f"; Tile {tid} ('{ch}')")
            else:
                # Empty
                tile_bytes = [0]*16
                self.emit(f'; Tile {tid} (empty)')
            
            hex_str = ','.join(f'${b:02X}' for b in tile_bytes)
            self.emit(f'    .byte {hex_str}')
            tiles_emitted += 1
        
        # Pad remaining CHR to 8KB
        remaining = 8192 - (tiles_emitted * 16)
        if remaining > 0:
            self.emit(f'    .res {remaining}, $00')


# ======================== BUILD ========================
NES_CFG = """MEMORY {
    ZP:     start = $00,    size = $100,  type = rw, define = yes;
    OAM:    start = $0200,  size = $100,  type = rw, define = yes;
    RAM:    start = $0300,  size = $500,  type = rw, define = yes;
    HDR:    start = $0000,  size = $10,   type = ro, file = %O, fill = yes;
    PRG:    start = $8000,  size = $8000, type = ro, file = %O, fill = yes;
    CHR:    start = $0000,  size = $2000, type = ro, file = %O, fill = yes;
}
SEGMENTS {
    HEADER:   load = HDR, type = ro;
    CODE:     load = PRG, type = ro, start = $8000;
    RODATA:   load = PRG, type = ro;
    VECTORS:  load = PRG, type = ro, start = $FFFA;
    CHARS:    load = CHR, type = ro;
    ZEROPAGE: load = ZP,  type = zp;
    BSS:      load = RAM, type = bss;
}
"""

def compile_neslang(source_path, output_path=None):
    if output_path is None:
        output_path = os.path.splitext(source_path)[0] + '.nes'

    # Read source
    with open(source_path, 'r') as f:
        source = f.read()

    # Lex
    try:
        tokens = Lexer(source).tokenize()
    except LexError as e:
        print(f"ОШИБКА ЛЕКСЕРА: {e}")
        sys.exit(1)

    # Parse
    try:
        ast = Parser(tokens).parse()
    except ParseError as e:
        print(f"ОШИБКА ПАРСЕРА: {e}")
        sys.exit(1)

    # Generate code
    try:
        asm_code = CodeGen(ast, source_path=source_path).generate()
    except CodeGenError as e:
        print(f"ОШИБКА КОДОГЕНЕРАЦИИ: {e}")
        sys.exit(1)

    # Write temp files and assemble
    base = os.path.splitext(output_path)[0]
    asm_path = base + '.s'
    cfg_path = base + '_nes.cfg'
    obj_path = base + '.o'

    with open(asm_path, 'w') as f:
        f.write(asm_code)
    with open(cfg_path, 'w') as f:
        f.write(NES_CFG)

    print(f"  Ассемблер: {asm_path}")

    # Assemble
    r = subprocess.run(['ca65', '-o', obj_path, asm_path], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ОШИБКА АССЕМБЛЕРА:\n{r.stderr}")
        sys.exit(1)

    # Link
    r = subprocess.run(['ld65', '-C', cfg_path, '-o', output_path, obj_path], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ОШИБКА ЛИНКЕРА:\n{r.stderr}")
        sys.exit(1)

    # Cleanup obj
    try: os.unlink(obj_path)
    except: pass
    try: os.unlink(cfg_path)
    except: pass

    size = os.path.getsize(output_path)
    print(f"  Готово: {output_path} ({size} байт)")
    return output_path

# ======================== MAIN ========================
HELP = """
╔══════════════════════════════════════════╗
║       NesLang Compiler v0.3.0           ║
║  Простой язык для создания NES-игр      ║
╚══════════════════════════════════════════╝

Использование:
  python3 neslang.py <файл.nsl> [-o выход.nes]

Пример:
  python3 neslang.py game.nsl
  python3 neslang.py game.nsl -o mygame.nes

Язык NesLang:
  Типы:     byte (8 бит, 0-255)
  Функции:  func name(byte a, byte b) { ... }
  Условия:  if (x > 5) { ... } else { ... }
  Циклы:    while (true) { ... }
  Массивы:  byte[4] data = { 1, 2, 3, 4 };

Встроенные функции:
  vblank()                     — ждать кадр (60 fps)
  gamepad(port)                — прочитать геймпад (0 или 1)
  sprite(id, x, y, tile, attr) — установить спрайт
  hide_sprite(id)              — скрыть спрайт
  ppu_on() / ppu_off()         — вкл/выкл экран
  color(offset, c0,c1,c2,c3)  — установить палитру
  scroll(x, y)                 — скролл экрана
  play_note(ch, lo, hi, vol)   — играть ноту
  noise(period, volume)        — шум (ударные)
  rand()                       — случайное число 0-255

Константы кнопок:
  BTN_A BTN_B BTN_SELECT BTN_START
  BTN_UP BTN_DOWN BTN_LEFT BTN_RIGHT

Тайлы (встроенные в CHR ROM):
  0=пусто 1=блок 2=персонаж 3=мяч 4=сердце 5=звезда 6=ромб
"""

if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print(HELP)
        sys.exit(0)

    src = sys.argv[1]
    out = None
    if '-o' in sys.argv:
        idx = sys.argv.index('-o')
        if idx + 1 < len(sys.argv):
            out = sys.argv[idx + 1]

    if not os.path.exists(src):
        print(f"Файл не найден: {src}")
        sys.exit(1)

    print(f"Компиляция {src}...")
    compile_neslang(src, out)
