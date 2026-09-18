#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Project-level wrapper for Antigravity Token Tracker.
"""
import os
import sys

global_tracker = r"C:\Users\Admin\.gemini\config\scripts\token_tracker.py"
if os.path.isfile(global_tracker):
    import runpy
    runpy.run_path(global_tracker, run_name="__main__")
else:
    print("Global token tracker not found.")
