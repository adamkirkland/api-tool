#!/usr/bin/env python3

from api_request import ApiResponse
import curses
from typing import Dict, List, Tuple

from display import Display, Line

class MenuCallback:
    def invoke(self, vars: Dict, menu: 'MenuDisplay', last_response: ApiResponse):
        pass

class MenuDisplay(Display):
    def __init__(self, title: str, items: List[Tuple[str, str]], instructions: str = None, callback: MenuCallback = MenuCallback()):
        super().__init__()
        self.title = title
        self.items = items
        self.instructions = instructions
        self.selection = 0
        self.shortcuts = {x[1]: idx for idx, x in enumerate(items)}
        self.callback = callback

    def draw(self):
        if not self.started:
            self.start()

        self.scr.erase()

        row = 0
        lines = []
        for title_row in self.title.splitlines():
            lines.append(Line(title_row, colors=[(0, 4)]))
        lines.append(Line())
        for idx, (desc, shortcut) in enumerate(self.items):
            selected = self.selection is idx
            lines.append(Line('> [{0}] {1}'.format(shortcut, desc), idx, [(0, 1), (3, 3), (4, 1), (6, 2 if selected else 1)]))
        if self.instructions:
            lines += [Line(), Line(self.instructions)]

        self.draw_lines(lines)

        self.scr.refresh()

    def scroll_up(self):
        new_selection = self.selection-1
        if new_selection < 0:
            new_selection = len(self.items)-1
        self.selection = new_selection

    def scroll_down(self):
        new_selection = self.selection+1
        if new_selection > len(self.items)-1:
            new_selection = 0
        self.selection = new_selection

    def wait_for_selection(self) -> int:
        if not self.started:
            self.start()
        result = None

        while True:
            try:
                self.draw()
                ch = self.scr.getch()
                try:
                    keyname = curses.keyname(ch).decode('utf-8').lower()
                except ValueError:
                    keyname = ''
                if ch == curses.KEY_UP:
                    self.scroll_up()
                elif ch == curses.KEY_DOWN:
                    self.scroll_down()
                elif ch == 27:  # ESC
                    return None
                elif ch == curses.KEY_ENTER or ch == 10 or ch == 13:  # ENTER
                    result = self.selection
                    break
                elif keyname != ' ' and keyname in self.shortcuts:
                    result = self.shortcuts[keyname]
                    break
            except KeyboardInterrupt:
                break

        self.stop()
        return result
