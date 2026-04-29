import sys
import os
from subprocess import call
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, GObject, Pango, Gdk, Gio, GLib, Adw
from .manager import BupManager
from .sudo import Worker as SudoWorker
from .scheduler import schedulers
from .version import __version__
import threading
from . import config
import traceback
import gettext
import getpass

# l10n
if gettext.find('bups', os.path.dirname(__file__) + '/../locale'):
	gettext.install('bups', os.path.dirname(__file__) + '/../locale')
else:
	gettext.install('bups')


class BackupWindow(Gtk.Window):
	def __init__(self, manager, parent=None):
		super().__init__(title=_("Backup"))
		self.set_default_size(500, 300)

		if parent is not None:
			self.set_transient_for(parent)
			self.set_modal(True)

		vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		vbox.set_margin_top(10)
		vbox.set_margin_bottom(10)
		vbox.set_margin_start(10)
		vbox.set_margin_end(10)
		self.set_child(vbox)

		self.label = Gtk.Label(label=_("Ready."), xalign=0)
		self.label.set_justify(Gtk.Justification.LEFT)
		vbox.append(self.label)

		self.progressbar = Gtk.ProgressBar()
		vbox.append(self.progressbar)

		self.textview = Gtk.TextView()
		self.textview.set_editable(False)
		self.textview.set_monospace(True)
		sw = Gtk.ScrolledWindow()
		sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
		sw.set_min_content_height(200)
		sw.set_child(self.textview)
		exp = Gtk.Expander(label=_("Details"))
		exp.set_child(sw)
		vbox.append(exp)

		hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=50)
		vbox.append(hbox)
		self.close_button = Gtk.Button(label=_("Close"))
		self.close_button.connect("clicked", self.on_close_clicked)
		hbox.append(self.close_button)

		self.manager = manager

	def backup(self):
		manager = self.manager

		finished = False

		def set_window_deletable(deletable):
			if not deletable:
				self.close_button.set_visible(False)
			else:
				self.close_button.set_visible(True)

		def onstatus(status, ctx):
			GLib.idle_add(self.set_label, status)

		def onprogress(progress, ctx):
			if finished:
				return

			if "percentage" in progress:
				if isinstance(progress["percentage"], (int, float)):
					GLib.idle_add(self.progressbar.set_fraction, progress["percentage"] / 100)
				else:
					GLib.idle_add(self.progressbar.pulse)

			lbl = _("Backing up {name}: ").format(name=ctx["name"])

			if "status" not in progress:
				return

			if progress["status"] == "indexing":
				lbl += _("indexing files")
			elif progress["status"] == "saving":
				lbl += _("saving files")
			elif progress["status"] == "reading_index":
				lbl += _("reading indexes")
			else:
				return

			lbl += " ("

			if "files_done" in progress:
				lbl += str(progress["files_done"])
				if "files_total" in progress:
					lbl += "/" + str(progress["files_total"])
				lbl += " " + _("files")
			if "bytes_done" in progress:
				lbl += ", " + str(int(progress["bytes_done"] / 1024)) + "/" + str(int(progress["bytes_total"] / 1024)) + " " + _("KiB")
			if "remaining_time" in progress and progress["remaining_time"]:
				lbl += ", " + _("{remaining_time} remaining").format(remaining_time=progress["remaining_time"])
			if "speed" in progress and progress["speed"]:
				lbl += ", " + str(progress["speed"]) + " " + _("KiB/s")
			if progress["status"] == "indexing":
				if "paths_per_sec" in progress:
					lbl += str(int(progress["paths_per_sec"])) + " " + _("paths/s")
				if "total_paths" in progress:
					lbl += ", " + str(progress["total_paths"]) + " " + _("paths indexed")

			if lbl[-1] == "(":
				lbl = lbl[:-2]
			else:
				lbl += ")"
			lbl += "..."

			GLib.idle_add(self.set_label, lbl, False)

		def onerror(err, ctx):
			GLib.idle_add(self.append_log, err)

		def onfinish(data, ctx):
			GLib.idle_add(set_window_deletable, True)
			GLib.idle_add(self.progressbar.set_fraction, 1)
			nonlocal finished
			finished = True

		def onabord(data, ctx):
			GLib.idle_add(set_window_deletable, True)
			GLib.idle_add(self.set_label, _("Backup canceled."), False)

		callbacks = {
			"onstatus": onstatus,
			"onprogress": onprogress,
			"onerror": onerror,
			"onfinish": onfinish,
			"onabord": onabord
		}

		self.set_label(_("Backup started..."))

		set_window_deletable(False)

		def do_backup(manager, callbacks):
			try:
				return manager.backup(callbacks)
			except Exception:
				callbacks["onerror"](traceback.format_exc(), {})
				callbacks["onabord"]({}, {})

		t = threading.Thread(target=do_backup, args=(manager, callbacks))
		t.start()

	def set_label(self, txt, logLabel=True):
		if txt == "":
			return
		self.label.set_text(txt)

		if logLabel:
			self.append_log(txt + "\n")

	def append_log(self, txt):
		buf = self.textview.get_buffer()
		buf.insert(buf.get_end_iter(), txt)
		print(txt.strip())

	def on_close_clicked(self, btn):
		self.destroy()


class RestoreWindow(Gtk.Window):
	def __init__(self, manager, parent):
		super().__init__(title=_("Restore"))
		self.set_default_size(400, 300)
		self.set_transient_for(parent)
		self.set_modal(True)

		cfg = parent.load_config()

		vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		vbox.set_margin_top(10)
		vbox.set_margin_bottom(10)
		vbox.set_margin_start(10)
		vbox.set_margin_end(10)
		self.set_child(vbox)

		# Backup name dropdown
		backup_names = [d["name"] for d in cfg["dirs"]]
		hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=50)
		vbox.append(hbox)
		label = Gtk.Label(label=_("Backup name"), xalign=0, hexpand=True)
		self.backup_name_entry = Gtk.Entry()
		if backup_names:
			self.backup_name_entry.set_text(backup_names[0])
		hbox.append(label)
		hbox.append(self.backup_name_entry)

		# Backup date
		hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=50)
		vbox.append(hbox)
		label = Gtk.Label(label=_("Backup date"), xalign=0, hexpand=True)
		self.backup_date_entry = Gtk.Entry()
		self.backup_date_entry.set_text("latest")
		hbox.append(label)
		hbox.append(self.backup_date_entry)

		# Backup path
		hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=50)
		vbox.append(hbox)
		label = Gtk.Label(label=_("Backup path"), xalign=0, hexpand=True)
		self.backup_path_entry = Gtk.Entry()
		hbox.append(label)
		hbox.append(self.backup_path_entry)

		# Destination
		hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=50)
		vbox.append(hbox)
		label = Gtk.Label(label=_("Destination"), xalign=0, hexpand=True)
		self.dest_entry = Gtk.Entry()
		self.dest_entry.set_text("/")
		self.dest_choose_btn = Gtk.Button(label=_("Choose..."))
		self.dest_choose_btn.connect("clicked", self.on_choose_dest)
		hbox.append(label)
		hbox.append(self.dest_entry)
		hbox.append(self.dest_choose_btn)

		# Buttons
		btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
		btn_box.set_halign(Gtk.Align.END)
		vbox.append(btn_box)

		button = Gtk.Button(label=_("Cancel"))
		button.connect("clicked", self.on_close_clicked)
		btn_box.append(button)

		button = Gtk.Button(label=_("Restore"))
		button.add_css_class("suggested-action")
		button.connect("clicked", self.on_restore_clicked)
		btn_box.append(button)

		self.manager = manager

	def on_choose_dest(self, btn):
		dialog = Gtk.FileDialog()
		dialog.set_title(_("Choose a destination folder"))
		dialog.select_folder(self, None, self._on_dest_chosen)

	def _on_dest_chosen(self, dialog, result):
		try:
			folder = dialog.select_folder_finish(result)
			if folder:
				self.dest_entry.set_text(folder.get_path())
		except GLib.Error:
			pass

	def restore(self):
		manager = self.manager

		backup_name = self.backup_name_entry.get_text()
		backup_date = self.backup_date_entry.get_text()
		backup_path = self.backup_path_entry.get_text()
		if backup_name == "":
			return
		from_path = "/" + backup_name + "/" + backup_date + "/" + backup_path
		to_path = self.dest_entry.get_text()
		if not to_path:
			to_path = "/"

		# Progress window
		progress_win = Gtk.Window(title=_("Restoring..."))
		progress_win.set_default_size(300, 100)
		progress_win.set_transient_for(self)
		progress_win.set_modal(True)

		box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		box.set_margin_top(10)
		box.set_margin_bottom(10)
		box.set_margin_start(10)
		box.set_margin_end(10)
		progress_win.set_child(box)

		label = Gtk.Label(label=_("Ready."), xalign=0)
		label.set_justify(Gtk.Justification.LEFT)
		box.append(label)

		progress_win.present()

		def set_label(msg):
			label.set_text(msg)

		def close_progress_win(btn):
			progress_win.destroy()

		def add_close_btn():
			button = Gtk.Button(label=_("Close"))
			button.connect("clicked", close_progress_win)
			box.append(button)
			progress_win.connect("destroy", lambda w: self.on_close_clicked(None))

		has_error = False

		def onstatus(status):
			print(status)
			if not has_error:
				GLib.idle_add(set_label, status)

		def onprogress(progress):
			GLib.idle_add(set_label, _("Restoring, ") + str(progress["files_done"]) + _(" files done..."))

		def onerror(err):
			print(err)
			nonlocal has_error
			has_error = True

		def onfinish():
			if not has_error:
				GLib.idle_add(set_label, _("Restoration finished."))
			GLib.idle_add(add_close_btn)

		def onabord():
			GLib.idle_add(add_close_btn)

		callbacks = {
			"onstatus": onstatus,
			"onprogress": onprogress,
			"onerror": onerror,
			"onfinish": onfinish,
			"onabord": onabord
		}

		def do_restore(manager, callbacks, from_path, to_path):
			try:
				return manager.restore({
					"from": from_path,
					"to": to_path
				}, callbacks)
			except Exception:
				callbacks["onerror"](traceback.format_exc())
				callbacks["onabord"]()

		t = threading.Thread(target=do_restore, args=(manager, callbacks, from_path, to_path))
		t.start()

	def on_restore_clicked(self, btn):
		self.restore()

	def on_close_clicked(self, btn):
		self.destroy()


class SettingsWindow(Gtk.Window):
	def __init__(self, parent):
		super().__init__(title=_("Settings"))
		self.set_default_size(500, 400)
		self.set_transient_for(parent)
		self.set_modal(True)

		self.cfg = parent.load_config()

		box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		box.set_margin_top(10)
		box.set_margin_bottom(10)
		box.set_margin_start(10)
		box.set_margin_end(10)
		self.set_child(box)

		# Use Notebook for tabs (still available in GTK 4)
		nb = Gtk.Notebook()
		box.append(nb)

		# ── Destination tab ──
		vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		vbox.set_margin_top(10)
		vbox.set_margin_bottom(10)
		vbox.set_margin_start(10)
		vbox.set_margin_end(10)
		nb.append_page(vbox, Gtk.Label(label=_("Destination")))

		# Filesystem type
		hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=50)
		vbox.append(hbox)
		label = Gtk.Label(label=_("Filesystem type"), xalign=0, hexpand=True)

		mount_types = ["", "cifs", "sshfs", "google_drive"]
		mount_types_names = [_("Local"), _("SAMBA"), _("SSH"), _("Google Drive")]
		string_list = Gtk.StringList.new(mount_types_names)
		self.mount_type_dropdown = Gtk.DropDown(model=string_list)
		self.mount_type_dropdown.set_selected(mount_types.index(self.cfg["mount"]["type"]))
		self.mount_type_dropdown.connect("notify::selected", self.on_mount_type_changed)
		self._mount_types = mount_types
		hbox.append(label)
		hbox.append(self.mount_type_dropdown)

		self.mount_boxes = {}

		# SAMBA options
		samba_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		vbox.append(samba_box)

		hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=50)
		samba_box.append(hbox)
		label = Gtk.Label(label=_("Hostname"), xalign=0, hexpand=True)
		self.samba_host_entry = Gtk.Entry()
		hbox.append(label)
		hbox.append(self.samba_host_entry)

		hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=50)
		samba_box.append(hbox)
		label = Gtk.Label(label=_("Samba share"), xalign=0, hexpand=True)
		self.samba_share_entry = Gtk.Entry()
		hbox.append(label)
		hbox.append(self.samba_share_entry)

		self.samba_guest_check = Gtk.CheckButton(label=_("Anonymous login"))
		self.samba_guest_check.set_sensitive(False)
		self.samba_guest_check.set_active(True)
		samba_box.append(self.samba_guest_check)

		self.mount_boxes["cifs"] = samba_box

		# SSH options
		sshfs_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		vbox.append(sshfs_box)

		hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=50)
		sshfs_box.append(hbox)
		label = Gtk.Label(label=_("Host"), xalign=0, hexpand=True)
		self.sshfs_host_entry = Gtk.Entry()
		hbox.append(label)
		hbox.append(self.sshfs_host_entry)

		self.mount_boxes["sshfs"] = sshfs_box

		# Path
		hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=50)
		vbox.append(hbox)
		label = Gtk.Label(label=_("Backup path"), xalign=0, hexpand=True)
		self.path_prefix_entry = Gtk.Entry()
		self.path_prefix_entry.set_text(self.cfg["mount"].get("path", ""))
		hbox.append(label)
		hbox.append(self.path_prefix_entry)

		# Load mount settings
		if self.cfg["mount"]["type"] == "cifs":
			host = ""
			share = ""
			target = self.cfg["mount"]["target"]
			if target.startswith("//"):
				target = target[2:]
			if "/" in target:
				host, share = target.split("/", 1)
			self.samba_host_entry.set_text(host)
			self.samba_share_entry.set_text(share)
		if self.cfg["mount"]["type"] == "sshfs":
			self.sshfs_host_entry.set_text(self.cfg["mount"]["target"])

		# Encrypt
		hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=50)
		vbox.append(hbox)
		self.encrypt_check = Gtk.CheckButton(label=_("Encrypt filesystem"))
		self.encrypt_check.set_active(self.cfg["mount"].get("encrypt", False))
		hbox.append(self.encrypt_check)

		# ── Schedule tab ──
		vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		vbox.set_margin_top(10)
		vbox.set_margin_bottom(10)
		vbox.set_margin_start(10)
		vbox.set_margin_end(10)
		nb.append_page(vbox, Gtk.Label(label=_("Schedule")))

		# Discover current scheduler
		job = None
		active_scheduler_idx = 0
		i = 0
		for name in schedulers:
			s = schedulers[name]
			try:
				job = s.get_job("bups")
			except (IOError, OSError):
				i += 1
				continue
			active_scheduler_idx = i
			break

		hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=50)
		vbox.append(hbox)
		label = Gtk.Label(label=_("Schedule backups"), xalign=0, hexpand=True)
		self.schedule_switch = Gtk.Switch()
		self.schedule_switch.set_active(job is not None)
		hbox.append(label)
		hbox.append(self.schedule_switch)

		# Scheduler dropdown
		hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=50)
		vbox.append(hbox)
		label = Gtk.Label(label=_("Scheduler"), xalign=0, hexpand=True)
		scheduler_names = list(schedulers.keys())
		self._scheduler_names = scheduler_names
		available_schedulers_nbr = sum(1 for n in scheduler_names if schedulers[n].is_available())

		scheduler_string_list = Gtk.StringList.new(scheduler_names)
		self.scheduler_dropdown = Gtk.DropDown(model=scheduler_string_list)
		if available_schedulers_nbr > 0:
			self.scheduler_dropdown.set_selected(active_scheduler_idx)
		hbox.append(label)
		hbox.append(self.scheduler_dropdown)

		# Period
		hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=50)
		vbox.append(hbox)
		label = Gtk.Label(label=_("Interval (days)"), xalign=0, hexpand=True)
		period = 1
		if job is not None and "period" in job:
			period = int(job["period"])
		adjustment = Gtk.Adjustment(value=period, lower=1, upper=100, step_increment=1, page_increment=7)
		self.schedule_period_spin = Gtk.SpinButton()
		self.schedule_period_spin.set_adjustment(adjustment)
		hbox.append(label)
		hbox.append(self.schedule_period_spin)

		if available_schedulers_nbr == 0:
			self.schedule_switch.set_sensitive(False)
			self.schedule_period_spin.set_sensitive(False)
			label = Gtk.Label(label=_("No scheduler available. Please install one of:") + " " + ", ".join(scheduler_names) + ".")
			vbox.append(label)

		# Buttons
		hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=50)
		box.append(hbox)
		button = Gtk.Button(label=_("About"))
		button.connect("clicked", parent.on_about_clicked)
		hbox.append(button)
		spacer = Gtk.Box(hexpand=True)
		hbox.append(spacer)
		button = Gtk.Button(label=_("Close"))
		button.connect("clicked", self.on_close_clicked)
		hbox.append(button)

		# Apply mount visibility
		self._update_mount_visibility()

	def on_close_clicked(self, btn):
		self.set_visible(False)

	def on_mount_type_changed(self, dropdown, pspec):
		self._update_mount_visibility()

	def _update_mount_visibility(self):
		mount_type = self.get_mount_type()

		for t in self.mount_boxes:
			box = self.mount_boxes[t]
			box.set_visible(t == mount_type)

	def get_mount_type(self):
		idx = self.mount_type_dropdown.get_selected()
		if idx < len(self._mount_types):
			return self._mount_types[idx]
		return ""

	def get_config(self):
		self.cfg["mount"]["type"] = self.get_mount_type()
		self.cfg["mount"]["path"] = self.path_prefix_entry.get_text()
		self.cfg["mount"]["encrypt"] = self.encrypt_check.get_active()

		if self.cfg["mount"]["type"] == "cifs":
			self.cfg["mount"]["target"] = "//" + self.samba_host_entry.get_text() + "/" + self.samba_share_entry.get_text()
			opts = ""
			if self.samba_guest_check.get_active():
				opts = "guest"
			self.cfg["mount"]["options"] = opts
		if self.cfg["mount"]["type"] == "sshfs":
			self.cfg["mount"]["target"] = self.sshfs_host_entry.get_text()
		if self.cfg["mount"]["type"] == "":
			self.cfg["mount"]["target"] = ""
			self.cfg["mount"]["options"] = ""

		return self.cfg

	def get_scheduler_name(self):
		idx = self.scheduler_dropdown.get_selected()
		if idx < len(self._scheduler_names):
			return self._scheduler_names[idx]
		return ""

	def get_scheduler_config(self):
		if not self.schedule_switch.get_active():
			return None

		dirname = os.path.realpath(os.path.dirname(__file__))
		logfile = dirname + "/scheduler-log.log"
		cmd = sys.executable + " " + dirname + "/scheduler_worker.py " + config.file_path()
		cmd += " > " + logfile + " 2>&1"

		cfg = {
			"period": self.schedule_period_spin.get_value_as_int(),
			"delay": 15,
			"id": "bups",
			"command": cmd
		}

		return cfg


class BupWindow(Gtk.ApplicationWindow):
	def __init__(self, app):
		super().__init__(application=app, title="Bups")
		self.set_default_size(800, 400)

		vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
		self.set_child(vbox)

		# Header bar
		hb = Gtk.HeaderBar()
		self.set_titlebar(hb)

		# Add/remove/properties buttons
		box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
		box.add_css_class("linked")

		button = Gtk.Button(icon_name="list-add-symbolic")
		button.set_tooltip_text(_("Add a directory"))
		button.connect("clicked", self.on_add_clicked)
		box.append(button)

		button = Gtk.Button(icon_name="list-remove-symbolic")
		button.set_tooltip_text(_("Remove this directory"))
		button.connect("clicked", self.on_remove_clicked)
		box.append(button)

		button = Gtk.ToggleButton(icon_name="document-properties-symbolic")
		button.set_tooltip_text(_("Properties"))
		button.connect("clicked", self.on_properties_clicked)
		box.append(button)
		self.sidebar_btn = button

		hb.pack_start(box)

		# Backup/restore/browse buttons
		box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
		box.add_css_class("linked")

		button = Gtk.Button(icon_name="drive-harddisk-symbolic")
		button.set_tooltip_text(_("Backup now"))
		button.connect("clicked", self.on_backup_clicked)
		box.append(button)

		button = Gtk.Button(icon_name="view-refresh-symbolic")
		button.set_tooltip_text(_("Restore a backup"))
		button.connect("clicked", self.on_restore_clicked)
		box.append(button)

		button = Gtk.Button(icon_name="document-open-symbolic")
		button.set_tooltip_text(_("Browse backups"))
		button.connect("clicked", self.on_mount_clicked)
		box.append(button)

		hb.pack_start(box)

		# Settings button
		button = Gtk.Button(icon_name="emblem-system-symbolic")
		button.set_tooltip_text(_("Settings"))
		button.connect("clicked", self.on_settings_clicked)
		hb.pack_end(button)

		# Main content: directory list using Gtk.ListView
		hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
		vbox.append(hbox)

		# Build the list model and view
		self.dir_store = Gio.ListStore.new(DirItem)
		self.selection_model = Gtk.SingleSelection(model=self.dir_store)

		factory = Gtk.SignalListItemFactory()
		factory.connect("setup", self._on_list_setup)
		factory.connect("bind", self._on_list_bind)

		self.listview = Gtk.ListView(model=self.selection_model, factory=factory)
		self.listview.set_vexpand(True)
		self.listview.set_hexpand(True)

		scrolled = Gtk.ScrolledWindow()
		scrolled.set_child(self.listview)
		scrolled.set_vexpand(True)
		scrolled.set_hexpand(True)
		hbox.append(scrolled)

		# Sidebar revealer for properties
		self.sidebar = Gtk.Revealer()
		self.sidebar.set_transition_type(Gtk.RevealerTransitionType.SLIDE_LEFT)

		self._create_properties(self.sidebar)

		hbox.append(self.sidebar)

		self.selection_model.connect("notify::selected", self._on_selection_changed)

		self.config = None
		self.load_config()
		for dirpath in self.config["dirs"]:
			self._add_dir_ui(dirpath)

		sudo_worker = SudoWorker()
		self.manager = BupManager(self.load_config(), sudo_worker)

	def _on_list_setup(self, factory, list_item):
		box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
		box.set_margin_top(4)
		box.set_margin_bottom(4)
		box.set_margin_start(8)
		box.set_margin_end(8)
		dir_label = Gtk.Label(xalign=0, hexpand=True)
		name_label = Gtk.Label(xalign=0)
		box.append(dir_label)
		box.append(name_label)
		list_item.set_child(box)

	def _on_list_bind(self, factory, list_item):
		item = list_item.get_item()
		box = list_item.get_child()
		dir_label = box.get_first_child()
		name_label = dir_label.get_next_sibling()
		dir_label.set_text(item.path)
		name_label.set_text(item.name)

	def _create_properties(self, outer):
		sidebar_ctn = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
		outer.set_child(sidebar_ctn)

		sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
		sidebar_ctn.append(sep)

		sidebar_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
		sidebar_vbox.set_margin_top(10)
		sidebar_vbox.set_margin_bottom(10)
		sidebar_vbox.set_margin_start(10)
		sidebar_vbox.set_margin_end(10)
		sidebar_ctn.append(sidebar_vbox)

		sidebar_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
		sidebar_vbox.append(sidebar_hbox)
		label = Gtk.Label(label=_("Backup name"), xalign=0, hexpand=True)
		self.sidebar_name_entry = Gtk.Entry()
		sidebar_hbox.append(label)
		sidebar_hbox.append(self.sidebar_name_entry)

		sidebar_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
		sidebar_vbox.append(sidebar_hbox)
		label = Gtk.Label(label=_("Exclude paths"), xalign=0, hexpand=True)
		self.sidebar_exclude_entry = Gtk.Entry()
		sidebar_hbox.append(label)
		sidebar_hbox.append(self.sidebar_exclude_entry)

		sidebar_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
		sidebar_vbox.append(sidebar_hbox)
		label = Gtk.Label(label=_("Exclude patterns"), xalign=0, hexpand=True)
		self.sidebar_excluderx_entry = Gtk.Entry()
		sidebar_hbox.append(label)
		sidebar_hbox.append(self.sidebar_excluderx_entry)

		label = Gtk.Label()
		label.set_markup(
			"<small>" + _("Enter a comma-separated list of paths and patterns to exclude.") +
			'\n<a href="https://github.com/bup/bup/blob/master/Documentation/bup-index.md">' +
			_("Read the docs") + "</a></small>"
		)
		sidebar_vbox.append(label)

		self.sidebar_onefilesystem_check = Gtk.CheckButton(label=_("Don't cross filesystem boundaries"))
		sidebar_vbox.append(self.sidebar_onefilesystem_check)

		sidebar_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
		sidebar_hbox.set_halign(Gtk.Align.END)
		sidebar_vbox.append(sidebar_hbox)
		button = Gtk.Button(label=_("Cancel"))
		button.connect("clicked", self.on_sidebar_cancel)
		sidebar_hbox.append(button)
		button = Gtk.Button(label=_("Save"))
		button.add_css_class("suggested-action")
		button.connect("clicked", self.on_sidebar_save)
		sidebar_hbox.append(button)

	def get_selected_row_index(self):
		idx = self.selection_model.get_selected()
		if idx == Gtk.INVALID_LIST_POSITION:
			return None
		return idx

	def show_sidebar(self):
		self.sidebar.set_reveal_child(True)
		self.sidebar_btn.set_active(True)

	def hide_sidebar(self):
		self.sidebar.set_reveal_child(False)
		self.sidebar_btn.set_active(False)

	def update_sidebar(self):
		index = self.get_selected_row_index()
		if index is None:
			return
		cfg = self.config["dirs"][index]

		self.sidebar_name_entry.set_text(cfg.get("name", ""))

		exclude = ", ".join(cfg.get("exclude", []))
		self.sidebar_exclude_entry.set_text(exclude)

		excluderx = ", ".join(cfg.get("excluderx", []))
		self.sidebar_excluderx_entry.set_text(excluderx)

		onefilesystem = cfg.get("onefilesystem", False)
		self.sidebar_onefilesystem_check.set_active(onefilesystem)

	def _on_selection_changed(self, model, pspec):
		if self.sidebar.get_reveal_child():
			self.update_sidebar()

	def on_properties_clicked(self, btn):
		index = self.get_selected_row_index()
		is_row_selected = index is not None

		if not self.sidebar_btn.get_active() or not is_row_selected:
			self.hide_sidebar()
			return

		self.update_sidebar()
		self.show_sidebar()

	def on_sidebar_cancel(self, btn):
		self.hide_sidebar()

	def on_sidebar_save(self, btn):
		index = self.get_selected_row_index()
		if index is None:
			return

		cfg = self.config["dirs"][index]

		cfg["name"] = self.sidebar_name_entry.get_text()

		exclude = self.sidebar_exclude_entry.get_text()
		cfg["exclude"] = [x.strip() for x in exclude.split(',') if x.strip()]

		excluderx = self.sidebar_excluderx_entry.get_text()
		cfg["excluderx"] = [x.strip() for x in excluderx.split(',') if x.strip()]

		cfg["onefilesystem"] = self.sidebar_onefilesystem_check.get_active()

		self.config["dirs"][index] = cfg
		self.save_config()

		# Update the list item
		item = self.dir_store.get_item(index)
		if item:
			item.name = cfg["name"]

		self.hide_sidebar()

	def on_add_clicked(self, btn):
		dialog = Gtk.FileDialog()
		dialog.set_title(_("Please choose a directory"))
		dialog.select_folder(self, None, self._on_folder_chosen)

	def _on_folder_chosen(self, dialog, result):
		try:
			folder = dialog.select_folder_finish(result)
			if folder:
				dirpath = folder.get_path()
				print("Dir selected: " + dirpath)
				self.add_dir(dirpath)
		except GLib.Error:
			pass

	def on_remove_clicked(self, btn):
		index = self.get_selected_row_index()
		if index is not None:
			dirpath = self.config["dirs"][index].get("path", "")
			print("Removing dir " + dirpath)

			self.dir_store.remove(index)
			del self.config["dirs"][index]
			self.save_config()
			self.on_sidebar_cancel(None)

	def get_default_backup_name(self, dirpath):
		login = getpass.getuser()
		dirname = os.path.basename(dirpath).lower()
		return login + "-" + dirname

	def normalize_dir(self, dir_data):
		if isinstance(dir_data, str):
			dir_data = {
				"path": dir_data,
				"name": self.get_default_backup_name(dir_data)
			}
		return dir_data

	def add_dir(self, dirpath):
		self.config["dirs"].append({
			"path": dirpath,
			"name": self.get_default_backup_name(dirpath)
		})
		self.save_config()
		self._add_dir_ui(dirpath)

	def _add_dir_ui(self, dir_data):
		dir_data = self.normalize_dir(dir_data)
		item = DirItem(path=dir_data["path"], name=dir_data["name"])
		self.dir_store.append(item)

	def on_backup_clicked(self, btn):
		win = BackupWindow(self.manager, parent=self)
		win.present()
		win.backup()

	def on_restore_clicked(self, btn):
		win = RestoreWindow(self.manager, parent=self)
		win.present()

	def on_mount_clicked(self, btn):
		info_label = Gtk.Label(label=_("Mounting filesystem..."))
		mount_win = Gtk.Window(title=_("Mounting..."))
		mount_win.set_default_size(300, 80)
		mount_win.set_transient_for(self)
		mount_win.set_modal(True)
		box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
		box.set_margin_top(10)
		box.set_margin_bottom(10)
		box.set_margin_start(10)
		box.set_margin_end(10)
		box.append(info_label)
		mount_win.set_child(box)
		mount_win.present()

		def open_mounted(data):
			print("Open dir:", data["path"])
			call(["xdg-open", data["path"]])

		def show_error(e):
			print("ERR: could not mount bup filesystem: " + str(e))
			dialog = Gtk.AlertDialog()
			dialog.set_message(_("Could not mount filesystem"))
			dialog.set_detail(str(e))
			dialog.show(self)

		def onstatus(status):
			GLib.idle_add(info_label.set_text, status)
			print(status)

		def onready(data):
			GLib.idle_add(mount_win.destroy)
			GLib.idle_add(open_mounted, data)

		def onerror(err):
			GLib.idle_add(show_error, err)

		def onabord():
			GLib.idle_add(mount_win.destroy)

		callbacks = {
			"onready": onready,
			"onstatus": onstatus,
			"onerror": onerror,
			"onabord": onabord
		}

		def do_mount(manager, callbacks):
			try:
				manager.mount(callbacks)
			except Exception:
				callbacks["onabord"]()
				callbacks["onerror"](traceback.format_exc())

		t = threading.Thread(target=do_mount, args=(self.manager, callbacks))
		t.start()

	def on_settings_clicked(self, btn):
		win = SettingsWindow(self)
		win.connect("hide", self.on_settings_closed)
		win.present()

	def on_settings_closed(self, win):
		self.config = win.get_config()
		self.save_config()

		new_scheduler_name = win.get_scheduler_name()
		new_cfg = win.get_scheduler_config()
		win.destroy()

		current_scheduler_name = ""
		current_cfg = None
		for name in schedulers:
			try:
				current_scheduler_name = name
				current_cfg = schedulers[name].get_job("bups")
				break
			except (IOError, OSError):
				current_cfg = None

		current_scheduler = schedulers.get(current_scheduler_name)
		new_scheduler = schedulers.get(new_scheduler_name)

		def remove_job():
			print("Removing scheduler job " + current_cfg["id"])
			current_scheduler.remove_job(current_cfg["id"])

		def update_job():
			print("Updating scheduler job " + new_cfg["id"])
			new_scheduler.update_job(new_cfg)

		def remove_update_job():
			if current_cfg is not None:
				remove_job()
			update_job()

		def show_error(e):
			print("ERR: could not update scheduler config: " + str(e))
			dialog = Gtk.AlertDialog()
			dialog.set_message(_("Could not update scheduler config"))
			dialog.set_detail(str(e))
			dialog.show(self)

		task = None
		if new_cfg is None and current_cfg is not None:
			task = remove_job
		elif new_cfg is not None:
			cfg_changed = True
			if current_scheduler_name != new_scheduler_name:
				task = remove_update_job
			else:
				if current_cfg is not None:
					cfg_changed = int(current_cfg["period"]) != int(new_cfg["period"])
				if cfg_changed:
					task = update_job

		if task is not None:
			info_label = Gtk.Label(label=_("Updating configuration..."))
			task_win = Gtk.Window(title=_("Updating..."))
			task_win.set_default_size(300, 80)
			task_win.set_transient_for(self)
			task_win.set_modal(True)
			box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
			box.set_margin_top(10)
			box.set_margin_bottom(10)
			box.set_margin_start(10)
			box.set_margin_end(10)
			box.append(info_label)
			task_win.set_child(box)
			task_win.present()

			def run_task(task, onexit):
				try:
					task()
				except Exception as e:
					GLib.idle_add(show_error, e)
				onexit()

			def onexit():
				GLib.idle_add(task_win.destroy)

			t = threading.Thread(target=run_task, args=(task, onexit))
			t.start()

	def on_about_clicked(self, btn):
		dialog = Gtk.AboutDialog()
		dialog.set_transient_for(self)
		dialog.set_modal(True)
		dialog.set_program_name('Bups')
		dialog.set_version(__version__)
		dialog.set_authors(['Emersion'])
		dialog.set_comments(_('Simple GUI for Bup, a very efficient backup system.'))
		dialog.set_website('https://github.com/emersion/bups')
		dialog.set_logo_icon_name('drive-harddisk')
		dialog.set_license(_('Distributed under the MIT license.') + '\nhttp://opensource.org/licenses/MIT')
		dialog.present()

	def load_config(self):
		if self.config is None:
			self.config = config.read()
		return self.config

	def save_config(self):
		if self.config is None:
			print("INFO: save_config() called but no config set")
			return

		print("Saving config")

		try:
			config.write(self.config)
		except IOError as e:
			print("ERR: could not update config: " + str(e))
			dialog = Gtk.AlertDialog()
			dialog.set_message(_("Could not update config"))
			dialog.set_detail(str(e))
			dialog.show(self)

	def quit(self, *args):
		if self.manager.mounted:
			info_label = Gtk.Label(label=_("Unmounting filesystem..."))
			unmount_win = Gtk.Window(title=_("Unmounting..."))
			unmount_win.set_default_size(300, 80)
			unmount_win.set_transient_for(self)
			unmount_win.set_modal(True)
			box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
			box.set_margin_top(10)
			box.set_margin_bottom(10)
			box.set_margin_start(10)
			box.set_margin_end(10)
			box.append(info_label)
			unmount_win.set_child(box)
			unmount_win.present()

			def onstatus(status):
				GLib.idle_add(info_label.set_text, status)
				print(status)

			def onfinish(data):
				GLib.idle_add(unmount_win.destroy)

			callbacks = {
				"onfinish": onfinish,
				"onstatus": onstatus
			}

			t = threading.Thread(target=self.manager.unmount, args=(callbacks,))
			t.start()


class DirItem(GObject.Object):
	"""Data model for a backup directory entry."""
	__gtype_name__ = 'DirItem'

	path = GObject.Property(type=str, default="")
	name = GObject.Property(type=str, default="")

	def __init__(self, path="", name=""):
		super().__init__()
		self.path = path
		self.name = name


class BupApp(Gtk.Application):
	def __init__(self):
		super().__init__(application_id="org.emersion.bups")

	def do_activate(self):
		win = BupWindow(self)
		win.connect("close-request", lambda w: w.quit())
		win.present()

	def do_startup(self):
		Gtk.Application.do_startup(self)
