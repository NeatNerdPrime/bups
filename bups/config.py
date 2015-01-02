import os
import json

sys_config_file = os.path.realpath(os.path.dirname(__file__)+"/config/config.json")
user_config_file = os.path.expanduser("~/.config/bups/config.json")

def read():
	if os.path.isfile(user_config_file):
		f = open(user_config_file, 'r')
	else:
		f = open(sys_config_file, 'r')
	cfg = json.load(f)
	f.close()
	return cfg

def write(cfg):
	user_config_dir = os.path.dirname(user_config_file)
	if not os.path.exists(user_config_dir):
		os.makedirs(user_config_dir)
	f = open(user_config_file, 'w')

	json.dump(cfg, f, indent=4)
	f.close()
