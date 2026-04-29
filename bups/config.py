import os
import json

sys_config_file = os.path.realpath(os.path.join(os.path.dirname(__file__), "config", "config.json"))
user_config_file = os.path.expanduser("~/.config/bups/config.json")

def file_path():
	if os.path.isfile(user_config_file):
		return user_config_file
	return sys_config_file

def read(custom_config_file=None):
	config_path = custom_config_file if custom_config_file and os.path.isfile(custom_config_file) else file_path()
	with open(config_path, 'r') as f:
		return json.load(f)

def write(cfg):
	user_config_dir = os.path.dirname(user_config_file)
	os.makedirs(user_config_dir, exist_ok=True)
	with open(user_config_file, 'w') as f:
		json.dump(cfg, f, indent=4)
