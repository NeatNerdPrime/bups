#!/usr/bin/env python3

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from bups import config
from bups.manager import BupManager

if __name__ == '__main__':
    manager = BupManager(config.read(sys.argv[1]))

    while True:
        try:
            cmd = input().strip()
        except EOFError:
            cmd = 'quit'

        res = {
            "success": True,
            "output": ""
        }

        def onerror(err, ctx):
            res["output"] += err + "\n"

        callbacks = {
            "onerror": onerror
        }

        if cmd == 'quit':
            sys.exit()
        if cmd == 'mount':
            res["success"] = manager.mount_parents(callbacks)
            res["bup_path"] = manager.bup.get_dir()
        if cmd == 'unmount':
            res["success"] = manager.unmount_parents(callbacks)

        sys.stdout.write(json.dumps(res) + "\n")
        sys.stdout.flush()
