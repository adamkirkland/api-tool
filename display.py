#!/usr/bin/env python3

import curses
from enum import Enum
import re
from threading import Lock
from typing import List, Tuple

# Tuple of string index from which to apply the color, and index of a curses
# color pair
Color = Tuple[int, int]
# Tuple of starting index, ending index
Span = Tuple[int, int]

class JsonType(Enum):
    OBJ_START = 1
    OBJ_END = 2
    ARR_START = 3
    ARR_END = 4
    EMPTY = 5
    STRING = 6
    NUMBER = 7
    BOOL = 8
    NULL = 9

# Annotation for a single line in a json print. Contains metadata about the
# json structure the line is part of
class JsonAnnotation:
    def __init__(self, type: JsonType, key: Span, value: Span):
        self.type: JsonType = type
        # Every line will contain a value, not all will contain keys
        # key and value below are string spans
        self.key: Span = key
        self.value: Span = value
        self.color = 3
        self.hidden: int = 0  # > 0 Indicates that this entity is hidden by a collapsed parent
        # hidden is an int rather than bool because multiple parents can be collapsed

    def collapsible(self) -> bool:
        return self.type is JsonType.OBJ_START or self.type is JsonType.ARR_START

# Represents JSON objects or arrays, which could span multiple lines
class JsonEntity(JsonAnnotation):
    def __init__(self, type: JsonType, key: Span, value: Span, pair_idx: int):
        super().__init__(type, key, value)
        self.color: int = 8
        self.pair_idx: int = pair_idx  # Line index of the other end of the entity
        self.child_count: int = 0  # Only used for type=ARR_START
        self.collapsed: bool = False  # Arrays and objects can collapse

class Line:
    def __init__(self, s: str = '', row: int = None, colors: List[Color] = None):
        self.s = s
        self.colors: List[Color] = colors if colors else []  # tuples of (position, color)
        self.json: JsonAnnotation = None
        self.row: int = row
        self.offset: int = 0  # Used to scroll across lines that are truncated

    def length(self) -> int:
        return len(self.s)

    # Does not modify the line object, instead returns a new colors list
    def add_color_span(self, colors: List[Color], color_i: int, start: int, w: int) -> List[Color]:
        try:
            prev_color = [c[1] for c in colors if c[0] <= start+w][-1]
        except IndexError:
            prev_color = 1
            colors = [(0, prev_color)] + colors
        colors = [x for x in colors if x[0] != start]
        colors += [(start, color_i), (start+w, prev_color)]
        return sorted(colors, key=lambda tup: tup[0])

    def draw(self, scr, row: int, w: int, cursor_span: Span = None):
        # Drawing should have no side effects - uses copies of colors and s to
        # avoid modifying the line
        colors = self.colors
        if len(colors) == 0:
            colors = [(0, 1)]
        s = self.s

        # Special JSON formatting that we want to do at draw time, rather than parse time
        if self.json and (self.json.type is JsonType.ARR_START or self.json.type is JsonType.OBJ_START):
            prefix = s[:self.json.value[0]]
            if self.json.collapsed:
                if self.json.type is JsonType.ARR_START:
                    suffix = '[ … count: {0} ]'.format(self.json.child_count)
                elif self.json.type is JsonType.OBJ_START:
                    suffix = '{ … }'
                s = prefix + suffix
                colors = self.add_color_span(colors, 9, len(prefix)+2, len(suffix)-4)
                colors = self.add_color_span(colors, self.json.color, len(prefix) + len(suffix) - 1, 1)
            elif self.json.type is JsonType.ARR_START:
                suffix = '[ count: {0}'.format(self.json.child_count)
                s = prefix + suffix
                colors = self.add_color_span(colors, 9, len(prefix) + 1, len(suffix) - 1)

        # If we're in a string line that has an offset, trim that many chars from the start
        if self.json and self.json.type is JsonType.STRING and self.offset:
            prefix = s[:self.json.value[0]+1]  # +1 to let the opening quotes through
            s = prefix + '[…]' + s[self.json.value[0]+1+self.offset:]
            colors = self.add_color_span(colors, 5, len(prefix), 3)
            # Modify any colors starting after the offset
            for i, color in enumerate(colors):
                if color[0] > len(prefix):
                    colors[i] = (max(len(prefix), color[0] - self.offset) + 3, color[1])

        # Truncate lines that are too long
        if len(s) > w:
            s = s[:w-3] + '[…]'
            colors = self.add_color_span(colors, 5, len(s)-3, 3)

        # Pad line with whitespace, so the background of the latest color will
        # fill the line
        s = s + ' '*(w - len(s))

        if cursor_span:
            colors = self.add_color_span(colors, 2, cursor_span[0], cursor_span[1] - cursor_span[0])

        # The actual drawing
        col, color_i = colors[0]
        for next_col, next_color_i in colors[1:]:
            next_col = min(next_col, w)
            if next_col > col:
                scr.addstr(row, col, s[col:next_col], curses.color_pair(color_i))
            col, color_i = next_col, next_color_i
        if col < w:
            scr.addstr(row, col, s[col:], curses.color_pair(color_i))

    def increase_offset(self, scr_w):
        if not self.json:
            return
        self.offset = min(max(0, len(self.s) - scr_w + 3), self.offset + 10)

    def decrease_offset(self):
        self.offset = max(0, self.offset - 10)



class Display:
    def __init__(self):
        self.scr = None
        self.started = False
        self.mutex = Lock()

    def start(self):
        self.scr = curses.initscr()
        curses.start_color()
        # TODO a more sensible way to organize these
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_WHITE)
        curses.init_pair(3, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(5, curses.COLOR_BLUE, curses.COLOR_BLACK)
        curses.init_pair(6, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
        curses.init_pair(7, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(8, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(9, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.noecho()
        curses.cbreak()
        curses.curs_set(0)
        try:
            curses.set_escdelay(100)
        except:
            pass
        self.scr.keypad(1)
        self.started = True

    def stop(self):
        curses.endwin()
        self.scr = None
        self.started = False

    def draw_lines(self, lines: List[Line], starting_row: int = 0, cursor_row: int = None):
        if not self.started:
            self.start()
        height, width = self.scr.getmaxyx()
        row = starting_row
        for idx, line in enumerate(lines):
            line = lines[idx]
            if row < height:
                if row == height-1:
                    width -= 1
                cursor_span = None
                if idx == cursor_row:
                    if line.json.key:
                        cursor_span = line.json.key
                    elif line.json.collapsible():
                        cursor_span = line.json.value
                line.draw(self.scr, row, width, cursor_span)
            row += 1
