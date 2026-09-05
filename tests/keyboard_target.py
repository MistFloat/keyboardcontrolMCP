from __future__ import annotations

import argparse
from pathlib import Path
import tkinter as tk


parser = argparse.ArgumentParser()
parser.add_argument("--title", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()

root = tk.Tk()
root.title(args.title)
root.geometry("560x120")
label = tk.Label(root, text="Keyboard MCP smoke-test target")
label.pack(pady=(12, 4))
entry = tk.Entry(root, width=70)
entry.pack(padx=12, pady=4)


def finish(_event: object) -> str:
    Path(args.output).write_text(entry.get(), encoding="utf-8")
    root.after(50, root.destroy)
    return "break"


entry.bind("<Return>", finish)
root.after(100, entry.focus_force)
root.mainloop()

