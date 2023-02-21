#!/usr/bin/env python3

import curses
from enum import Enum
import json
import re
from typing import Any, List

from display import Display, JsonAnnotation, JsonEntity, JsonType, Line

class LinesDisplay(Display):
    class Mode(Enum):
        SCROLL = 1
        JSON = 2

    def __init__(self):
        super().__init__()
        self.mode = LinesDisplay.Mode.SCROLL
        self.top_row: int = 0
        self.bottom_row: int = 0
        self.content: List[Line] = []
        self.header = Line()
        self.cursor_row = None
        self.footer = Line()

    def start(self):
        super().start()
        self.top_row = 0
        self.bottom_row = 0
        self.content = []
        #self.scr.nodelay(False)

    def print(self, s: str, flush: bool = True):
        if not self.started:
            self.start()
        new_lines = [Line(x) for x in s.splitlines()]
        if new_lines and self.content and not flush:
            # Merge the last line, and the first of the new lines
            first_new_line = new_lines[0]
            new_lines = new_lines[1:]
            prev_line = self.content[-1]
            self.content = self.content[:-1] + [Line(prev_line.s + first_new_line.s)]
        self.content += new_lines
        self.draw()

    # Adds a json element to the content, and marks relevant lines as
    # containing keys, multi-line objects, and multi-line arrays
    def print_json(self, obj: Any, flush: bool = True):
        indent = 4
        as_str = json.dumps(obj, indent=indent)
        lines: List[Line] = []
        key_value_re = r'\s*?(\".*?\")(\s?:\s?)(.*?)$'  # matches key-value lines

        stack: List[int] = []
        num_existing_lines = len(self.content)
        for i, line_str in enumerate(as_str.splitlines()):
            line = Line(line_str)
            unindented = line_str.lstrip()
            if len(unindented) == 0:
                lines.append(line)
                continue

            # This is pretty messy, but basically we're adding a bunch of JSON
            # metadata to each line. We rely a lot on the json library to do
            # nice formatting for us with correct indentations
            annotation = None
            kv_match = re.match(key_value_re, line_str)
            value_span = None
            value = None
            key_span = None
            if kv_match:
                key_span = kv_match.span(1)
                value_span = kv_match.span(3)
                value = line.s[value_span[0]:value_span[1]]
            else:
                end_i = max(0, len(line.s.rstrip()))
                value_span = (len(line.s)-len(unindented), end_i)
                value = line.s[value_span[0]:value_span[1]]

            # Trim trailing commas
            if value[-1] == ',':
                value = value[:-1]
                value_span = (value_span[0], value_span[1]-1)

            if value == '[':
                annotation = JsonEntity(JsonType.ARR_START, key_span, value_span, None)
                stack.append(i)
            elif value == '{':
                annotation = JsonEntity(JsonType.OBJ_START, key_span, value_span, None)
                stack.append(i)
            elif value == ']':
                entity_start = stack.pop()
                annotation = JsonEntity(JsonType.ARR_END, key_span, value_span, entity_start)
                start_line = lines[entity_start]
                start_line.json.pair_idx = i + num_existing_lines
                start_indentation = len(start_line.s) - len(start_line.s.lstrip())
                # Now we have the end of the multi-line array, count the children
                start_line.json.child_count = 0
                for l in lines[entity_start: i]:
                    lstripped = l.s.lstrip()
                    if lstripped[0] == ']' or lstripped[0] == '}':
                        continue
                    if len(l.s) - len(l.s.lstrip()) == start_indentation + 4:
                        start_line.json.child_count += 1
            elif value == '}':
                entity_start = stack.pop()
                annotation = JsonEntity(JsonType.OBJ_END, key_span, value_span, entity_start)
                lines[entity_start].json.pair_idx = i + num_existing_lines
            elif value == '[]' or value == '{}':
                annotation = JsonEntity(JsonType.EMPTY, key_span, value_span, None)
            elif value == 'null':
                annotation = JsonAnnotation(JsonType.NULL, key_span, value_span)
            elif value == 'true' or value == 'false':
                annotation = JsonAnnotation(JsonType.BOOL, key_span, value_span)
            elif value[0] == '"' and value[-1] == '"':
                annotation = JsonAnnotation(JsonType.STRING, key_span, value_span)
            else:
                annotation = JsonAnnotation(JsonType.NUMBER, key_span, value_span)

            line.json = annotation

            # If not flushing previous display line, add it on here so as not to mess up the json parsing
            # This means we need to increase the key and value spans accordingly
            if i == 0 and not flush and self.content:
                old_line = self.content[-1]
                line.s = old_line.s + line.s
                if line.json and line.json.key:
                    line.json.key = tuple(x+len(old_line.s) for x in line.json.key)
                if line.json and line.json.value:
                    line.json.value = tuple(x+len(old_line.s) for x in line.json.value)
                self.content = self.content[:-1]

            # Add JSON coloring
            color_key = 7
            if annotation:
                line.colors = line.add_color_span(line.colors, annotation.color, annotation.value[0], annotation.value[1] - annotation.value[0])
                if annotation.key:
                    line.colors = line.add_color_span(line.colors, color_key, annotation.key[0], annotation.key[1]-annotation.key[0])

            lines.append(line)

        self.content += lines
        for idx, line in enumerate(self.content):
            line.row = idx
        self.draw()

    def set_footer(self, s: str, flush: bool = True):
        if hasattr(self, 'footer') and not flush:
            self.footer.s += s
        else:
            self.footer = Line(s, colors=[(0, 4)] if s else [])

    def set_header(self, s: str, flush: bool = True):
        if hasattr(self, 'header') and not flush:
            self.header.s += s
        else:
            self.header = Line(s, colors=[(0, 4)])

    def draw(self):
        if not self.started:
            self.start()
        self.scr.erase()

        height, width = self.scr.getmaxyx()
        cursor_row = None

        lines: List[Line] = [self.header]

        content_space = height - len(lines) - 1  # 1 to account for footer
        idx = self.top_row
        while idx < len(self.content) and content_space > 0:
            line = self.content[idx]
            lines.append(line)
            if self.cursor_row == idx and line.json and (line.json.key or line.json.collapsible()):
                cursor_row = len(lines) - 1
            if line.json and line.json.collapsible() and line.json.collapsed:
                idx += line.json.pair_idx - line.row
            idx += 1
            content_space -= 1

        # Filler for lines beyond what we have to display
        for i in range(content_space):
            lines.append(Line('~'))

        if self.footer:
            lines.append(self.footer)

        self.bottom_row =max(0, idx-1)
        self.draw_lines(lines, 0, cursor_row if self.mode is LinesDisplay.Mode.JSON else None)

        self.scr.refresh()

    def scroll_screen_up(self, n=1):
        for _ in range(n):
            self.top_row = next((i for i in range(self.top_row-1, -1, -1) if (self.content[i].json is None or not self.content[i].json.hidden)), self.top_row)

    def scroll_screen_down(self, n=1):
        for _ in range(n):
            self.top_row = next((i for i in range(self.top_row+1, len(self.content)) if (self.content[i].json is None or not self.content[i].json.hidden)), self.top_row)

    def scroll_json_up(self):
        prev_row = next(
            (i for i in range(self.cursor_row-1, -1, -1) if self.content[i].json and (self.content[i].json.key or self.content[i].json.collapsible()) and not self.content[i].json.hidden),
            None
        )
        if prev_row is not None:
            self.cursor_row = prev_row
        else:
            # If there is no previous json line, we still want to scroll the screen in case there's non-json text to display
            self.scroll_screen_up()

        # Make the screen catch up to the cursor
        if self.cursor_row < self.top_row:
            self.top_row = self.cursor_row
        # bottom_row will be set next draw cycle

    def scroll_json_down(self):
        next_row = next(
            (i for i in range(self.cursor_row+1, len(self.content)) if self.content[i].json and (self.content[i].json.key or self.content[i].json.collapsible()) and not self.content[i].json.hidden),
            None
        )
        if next_row is not None:
            self.cursor_row = next_row
        else:
            self.scroll_screen_down()
        while self.cursor_row > self.bottom_row:
            self.scroll_screen_down()
            self.draw()  # lazy, but bottom_row gets set on draw cycle

    def cycle_mode(self):
        if self.mode is LinesDisplay.Mode.SCROLL:
            if self.cursor_row == None or self.cursor_row < self.top_row or self.cursor_row > self.bottom_row:
                self.cursor_row = next((i for i in range(self.top_row, len(self.content)) if self.content[i].json and (self.content[i].json.key or self.content[i].json.collapsible())), None)
                if self.cursor_row == None:
                    return
            self.mode = LinesDisplay.Mode.JSON
        else:
            self.mode = LinesDisplay.Mode.SCROLL

        self.set_footer_for_mode()

        self.draw()

    def set_footer_for_mode(self):
        if not self.mode:
            return
        footer_str = 'Navigation mode: {0}'.format(self.mode.name)
        if self.mode == LinesDisplay.Mode.JSON:
            footer_str += ', use left/right arrows to collapse/expand elements'
        elif self.mode == LinesDisplay.Mode.SCROLL:
            footer_str += ', use left/right arrows to page up and down'
        self.set_footer(footer_str)

    def set_collapsed(self, line_num: int, collapsed: bool):
        line = self.content[line_num]
        if not line.json or not line.json.collapsible():
            return
        if line.json.collapsed == collapsed:
            return

        line.json.collapsed = collapsed

        for x in range(line.row + 1, line.json.pair_idx+1):
            if self.content[x].json:
                self.content[x].json.hidden += -1 if collapsed else 1

        self.draw()

    def display_and_browse(self):
        if not self.started:
            self.start()
        page_size = 30
        self.set_header('ENTER or ESC to return to menu, SPACE to swap modes')
        self.mode = LinesDisplay.Mode.SCROLL
        self.set_footer_for_mode()
        width = self.scr.getmaxyx()[1]

        while True:
            try:
                self.draw()
                ch = self.scr.getch()
                try:
                    keyname = curses.keyname(ch).decode('utf-8')
                except ValueError:
                    keyname = ''
                if ch == curses.KEY_UP:
                    if self.mode is LinesDisplay.Mode.JSON:
                        self.scroll_json_up()
                    else:
                        self.scroll_screen_up()
                elif ch == curses.KEY_DOWN:
                    if self.mode is LinesDisplay.Mode.JSON:
                        self.scroll_json_down()
                    else:
                        self.scroll_screen_down()
                elif ch == curses.KEY_LEFT:
                    if self.mode is LinesDisplay.Mode.JSON:
                        line: Line = self.content[self.cursor_row]
                        if line.json and line.json.type is JsonType.STRING:
                            line.decrease_offset()
                        else:
                            self.set_collapsed(self.cursor_row, True)
                    else:
                        self.scroll_screen_up(page_size)
                elif ch == curses.KEY_RIGHT:
                    if self.mode is LinesDisplay.Mode.JSON:
                        line: Line = self.content[self.cursor_row]
                        if line.json and line.json.type is JsonType.STRING:
                            line.increase_offset(width)
                        else:
                            self.set_collapsed(self.cursor_row, False)
                    else:
                        self.scroll_screen_down(page_size)
                elif ch == 27 or keyname == 'q' or ch == curses.KEY_ENTER or ch == 10 or ch == 13:  # ESC, q, or ENTER
                    break
                elif ch == ord(' '):
                    self.cycle_mode()
            except KeyboardInterrupt:
                break
        self.stop()

    def get_numeric_input(self, prompt) -> str:
        self.set_footer(prompt)
        self.draw()

        height, _ = self.scr.getmaxyx()
        self.scr.nodelay(False)
        # getstr doesn't work on windows, so we have to use something a bit more manual
        code_chars = []
        while len(code_chars) < 20:  # Arbitrary cap on length
            char = self.scr.getch(height-1, len(prompt)+1+len(code_chars))
            if char >= 48 and char < 58:  # 0-9
                code_chars.append(str(char-48))
            elif char == 27 or char == 81 or char == 113:  # ESC, Q, q
                return None
            elif char == 10 or char == 13:  # ENTER
                break
            elif char == 8 or char == 127:  # BACKSPACE
                code_chars.pop()
            self.set_footer('{0} {1}'.format(prompt, ''.join(code_chars)))
            self.footer.colors = self.footer.add_color_span(self.footer.colors, 0, len(prompt)+1, len(code_chars))
            self.draw()
        response = ''.join(code_chars)
        self.scr.nodelay(True)

        self.footer = Line()
        return response
