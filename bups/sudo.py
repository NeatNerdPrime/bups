import os
import subprocess
import json
import sys
from . import config

def command_exists(cmd):
	with open(os.devnull, 'wb') as devnull:
		rc = subprocess.call(['which', cmd], stdout=devnull, stderr=devnull)
	return rc == 0

def get_sudo(cmd):
	if isinstance(cmd, list):
		cmd = " && ".join(cmd)

	if os.geteuid() != 0:
		if "DISPLAY" in os.environ:
			if command_exists("pkexec"):
				sudo_cmd = "pkexec sh -c"
			elif command_exists("gksu"):
				sudo_cmd = "gksu"
			elif "SSH_ASKPASS" in os.environ:
				sudo_cmd = os.environ["SSH_ASKPASS"] + " | sudo -S sh -c"
			else:
				raise Exception("Could not find graphical sudo executable")
		else:
			sudo_cmd = "sudo sh -c"
		cmd = sudo_cmd + ' "' + cmd + '"'
	return cmd

def sudo(cmd):
	return subprocess.call(get_sudo(cmd), shell=True)

class SudoQueue:
	def __init__(self):
		self.queue = []

	def append(self, cmd):
		self.queue.append(cmd)

	def execute(self):
		return sudo(self.queue)

	def reset(self):
		self.queue = []

class Worker:
	def __init__(self):
		self.proc = None

	def start(self):
		dirname = os.path.realpath(os.path.dirname(__file__))
		cmd = sys.executable + " " + dirname + "/sudo_worker.py " + config.file_path()
		self.proc = subprocess.Popen(
			get_sudo(cmd), shell=True,
			stdin=subprocess.PIPE, stdout=subprocess.PIPE,
			text=True
		)

	def send_command(self, cmd):
		if self.proc is None or self.proc.returncode is not None:
			self.start()

		print('Send command', cmd)
		self.proc.stdin.write(cmd + "\n")
		self.proc.stdin.flush()
		json_res = self.proc.stdout.readline().strip()
		print('Got response', json_res)

		try:
			res = json.loads(json_res)
		except ValueError:
			res = {
				"success": False,
				"output": json_res
			}

		return res

	def proxy_command(self, cmd, callbacks):
		res = self.send_command(cmd)

		if res["output"] != "":
			callbacks["onerror"](res["output"], {})

		return res
