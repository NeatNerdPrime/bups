#!/usr/bin/env python3

import sys
import os

# Add bup library path if it exists
bup_lib = '/usr/lib/bup'
if os.path.isdir(bup_lib) and bup_lib not in sys.path:
	sys.path.append(bup_lib)

from subprocess import PIPE, Popen
import contextlib

# Unix, Windows and old Macintosh end-of-line
newlines = ['\n', '\r\n', '\r']
def unbuffered(proc, stream='stdout'):
	stream = getattr(proc, stream)
	with contextlib.closing(stream):
		while True:
			out = []
			last = stream.read(1)
			# Don't loop forever
			if last == '' and proc.poll() is not None:
				break
			while last not in newlines:
				# Don't loop forever
				if last == '' and proc.poll() is not None:
					break
				out.append(last)
				last = stream.read(1)
			out = ''.join(out)
			yield out

class BupWorker:
	def __init__(self, bup_dir=None):
		self.dir = None

		# Save default dir now, otherwise BUP_DIR will be overwritten in the future
		self.default_dir = os.environ.get('BUP_DIR', os.path.expanduser('~/.bup'))

		# Set bup exe
		os.environ['BUP_MAIN_EXE'] = os.environ.get('BUP_MAIN_EXE', 'bup')

		if bup_dir is not None:
			self.set_dir(bup_dir)

	def get_default_dir(self):
		return self.default_dir

	def set_dir(self, bup_dir):
		self.dir = bup_dir
		os.environ['BUP_DIR'] = bup_dir

	def get_dir(self):
		return self.dir

	def init(self, callbacks=None):
		return self.run(['init'], callbacks or {})

	def index(self, dirpath, opts=None, callbacks=None):
		opts = opts or {}
		callbacks = callbacks or {}
		args = ['index', '-u', dirpath]
		if 'exclude_paths' in opts:
			for excluded in opts['exclude_paths']:
				args.extend(('--exclude', excluded))
		if 'exclude_rxs' in opts:
			for excluded in opts['exclude_rxs']:
				args.extend(('--exclude-rx', excluded))
		if 'one_file_system' in opts and opts['one_file_system']:
			args.append('--one-file-system')

		return self.run(args, callbacks)

	def save(self, dirpath, opts=None, callbacks=None):
		opts = opts or {}
		callbacks = callbacks or {}
		args = ['save', '-n', opts['name'], dirpath]
		return self.run(args, callbacks)

	def fuse(self, mount_path, callbacks=None):
		self.run(['fuse', mount_path], callbacks or {})

	def restore(self, from_path, to_path, callbacks=None):
		self.run(['restore', '-C', to_path, from_path], callbacks or {})

	def run(self, args, callbacks=None):
		callbacks = callbacks or {}
		env = {
			'BUP_FORCE_TTY': '2',
			'BUP_MAIN_EXE': os.environ['BUP_MAIN_EXE'],
			'PATH': os.environ['PATH']
		}
		if self.dir is not None:
			env['BUP_DIR'] = self.dir

		args.insert(0, os.environ['BUP_MAIN_EXE'])

		if 'onstatus' in callbacks:
			callbacks['stderr'] = callbacks['onstatus']

		proc = Popen(args, env=env, stdout=None, stderr=PIPE, universal_newlines=True)

		if "stderr" in callbacks:
			for line in unbuffered(proc, 'stderr'):
				callbacks["stderr"](line)
		elif "stdout" in callbacks:
			for line in unbuffered(proc, 'stdout'):
				callbacks["stdout"](line)

		if "onclose" in callbacks:
			callbacks["onclose"](proc.poll())
