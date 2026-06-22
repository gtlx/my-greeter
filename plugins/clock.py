#!/usr/bin/env python3
"""
像素风格时钟插件
输出一个 5 行高的 ASCII art 时钟，支持冒号闪烁。
"""

import json
from datetime import datetime

DIGITS = {
    "0": [" ██ ", "█  █", "█  █", "█  █", " ██ "],
    "1": ["  █ ", " ██ ", "  █ ", "  █ ", " ███"],
    "2": [" ██ ", "   █", " ██ ", "█   ", "████"],
    "3": [" ██ ", "   █", " ██ ", "   █", " ██ "],
    "4": ["█  █", "█  █", "████", "   █", "   █"],
    "5": ["████", "█   ", "███ ", "   █", "███ "],
    "6": [" ██ ", "█   ", "███ ", "█  █", " ██ "],
    "7": ["████", "   █", "  █ ", " █  ", "█   "],
    "8": [" ██ ", "█  █", " ██ ", "█  █", " ██ "],
    "9": [" ██ ", "█  █", " ███", "   █", " ██ "],
}

COLON = ["    ", " ██ ", "    ", " ██ ", "    "]


def build_clock(hh: str, mm: str, ss: str, colon_on: bool) -> list[str]:
    """构建 5 行像素时钟"""
    parts = [hh, mm] if colon_on else [hh, mm]
    colon_glyph = COLON if colon_on else ["    "] * 5

    lines = [""] * 5
    for idx, part in enumerate(parts):
        for row in range(5):
            if lines[row]:
                lines[row] += "  "
            lines[row] += DIGITS[part[0]][row]
            lines[row] += " "
            lines[row] += DIGITS[part[1]][row]
        if idx == 0:
            for row in range(5):
                lines[row] += " " + colon_glyph[row]

    return [f"  {line}" for line in lines]


def main():
    now = datetime.now()
    hh = now.strftime("%H")
    mm = now.strftime("%M")
    ss = now.strftime("%S")
    colon_on = int(ss) % 2 == 0

    lines = build_clock(hh, mm, ss, colon_on)
    print(json.dumps({"name": "clock", "lines": lines, "position": "center"}))


if __name__ == "__main__":
    main()
