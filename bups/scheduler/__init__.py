from . import anacron
from . import systemd
from . import systemd_user

schedulers = {
    "anacron": anacron,
    "systemd": systemd,
    "systemd-user": systemd_user
}
