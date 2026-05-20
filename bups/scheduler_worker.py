#!/usr/bin/env python3

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bups import config
from bups.manager import BupManager

manager = BupManager(config.read(sys.argv[1]))

def onstatus(status, ctx):
	print(status)

def onerror(err, ctx):
	sys.stderr.write(err+"\n")

callbacks = {
	"onstatus": onstatus,
	"onerror": onerror
}

manager.backup(callbacks)