# Copyright (c) 2009, Giampaolo Rodola'. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Common objects shared by all _ps* modules."""

from __future__ import division

import contextlib
import errno
import functools
import os
import socket
import stat
import sys
import warnings
from collections import namedtuple
from socket import AF_INET
from socket import SOCK_DGRAM
from socket import SOCK_STREAM

try:
    import threading
except ImportError:
    import dummy_threading as threading

if sys.version_info >= (3, 4):
    import enum
else:
    enum = None


# --- constants

POSIX = os.name == "posix"
WINDOWS = os.name == "nt"
LINUX = sys.platform.startswith("linux")
OSX = sys.platform.startswith("darwin")
FREEBSD = sys.platform.startswith("freebsd")
OPENBSD = sys.platform.startswith("openbsd")
NETBSD = sys.platform.startswith("netbsd")
BSD = FREEBSD or OPENBSD or NETBSD
SUNOS = sys.platform.startswith("sunos") or sys.platform.startswith("solaris")

AF_INET6 = getattr(socket, 'AF_INET6', None)
AF_UNIX = getattr(socket, 'AF_UNIX', None)

STATUS_RUNNING = "running"
STATUS_SLEEPING = "sleeping"
STATUS_DISK_SLEEP = "disk-sleep"
STATUS_STOPPED = "stopped"
STATUS_TRACING_STOP = "tracing-stop"
STATUS_ZOMBIE = "zombie"
STATUS_DEAD = "dead"
STATUS_WAKE_KILL = "wake-kill"
STATUS_WAKING = "waking"
STATUS_IDLE = "idle"  # FreeBSD, OSX
STATUS_LOCKED = "locked"  # FreeBSD
STATUS_WAITING = "waiting"  # FreeBSD
STATUS_SUSPENDED = "suspended"  # NetBSD

CONN_ESTABLISHED = "ESTABLISHED"
CONN_SYN_SENT = "SYN_SENT"
CONN_SYN_RECV = "SYN_RECV"
CONN_FIN_WAIT1 = "FIN_WAIT1"
CONN_FIN_WAIT2 = "FIN_WAIT2"
CONN_TIME_WAIT = "TIME_WAIT"
CONN_CLOSE = "CLOSE"
CONN_CLOSE_WAIT = "CLOSE_WAIT"
CONN_LAST_ACK = "LAST_ACK"
CONN_LISTEN = "LISTEN"
CONN_CLOSING = "CLOSING"
CONN_NONE = "NONE"

if enum is None:
    NIC_DUPLEX_FULL = 2
    NIC_DUPLEX_HALF = 1
    NIC_DUPLEX_UNKNOWN = 0
else:
    class NicDuplex(enum.IntEnum):
        NIC_DUPLEX_FULL = 2
        NIC_DUPLEX_HALF = 1
        NIC_DUPLEX_UNKNOWN = 0

    globals().update(NicDuplex.__members__)


# --- functions

def usage_percent(used, total, _round=None):
    """Calculate percentage usage of 'used' against 'total'."""
    try:
        ret = (used / total) * 100
    except ZeroDivisionError:
        ret = 0.0 if isinstance(used, float) or isinstance(total, float) else 0
    if _round is not None:
        return round(ret, _round)
    else:
        return ret


def memoize(fun):
    """A simple memoize decorator for functions supporting (hashable)
    positional arguments.
    It also provides a cache_clear() function for clearing the cache:

    >>> @memoize
    ... def foo()
    ...     return 1
    ...
    >>> foo()
    1
    >>> foo.cache_clear()
    >>>
    """
    @functools.wraps(fun)
    def wrapper(*args, **kwargs):
        key = (args, frozenset(sorted(kwargs.items())))
        with lock:
            try:
                return cache[key]
            except KeyError:
                ret = cache[key] = fun(*args, **kwargs)
        return ret

    def cache_clear():
        """Clear cache."""
        lock.acquire()
        try:
            cache.clear()
        finally:
            lock.release()

    lock = threading.RLock()
    cache = {}
    wrapper.cache_clear = cache_clear
    return wrapper


def isfile_strict(path):
    """Same as os.path.isfile() but does not swallow EACCES / EPERM
    exceptions, see:
    http://mail.python.org/pipermail/python-dev/2012-June/120787.html
    """
    try:
        st = os.stat(path)
    except OSError as err:
        if err.errno in (errno.EPERM, errno.EACCES):
            raise
        return False
    else:
        return stat.S_ISREG(st.st_mode)


def path_exists_strict(path):
    """Same as os.path.exists() but does not swallow EACCES / EPERM
    exceptions, see:
    http://mail.python.org/pipermail/python-dev/2012-June/120787.html
    """
    try:
        os.stat(path)
    except OSError as err:
        if err.errno in (errno.EPERM, errno.EACCES):
            raise
        return False
    else:
        return True


def supports_ipv6():
    """Return True if IPv6 is supported on this platform."""
    if not socket.has_ipv6 or not hasattr(socket, "AF_INET6"):
        return False
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        with contextlib.closing(sock):
            sock.bind(("::1", 0))
        return True
    except socket.error:
        return False


def parse_environ_block(data):
    """Parse a C environ block of environment variables into a dictionary."""
    # The block is usually raw data from the target process.  It might contain
    # trailing garbage and lines that do not look like assignments.
    ret = {}
    pos = 0

    # localize global variable to speed up access.
    WINDOWS_ = WINDOWS
    while True:
        next_pos = data.find("\0", pos)
        # nul byte at the beginning or double nul byte means finish
        if next_pos <= pos:
            break
        # there might not be an equals sign
        equal_pos = data.find("=", pos, next_pos)
        if equal_pos > pos:
            key = data[pos:equal_pos]
            value = data[equal_pos+1:next_pos]
            # Windows expects environment variables to be uppercase only
            if WINDOWS_:
                key = key.upper()
            ret[key] = value
        pos = next_pos + 1

    return ret


def sockfam_to_enum(num):
    """Convert a numeric socket family value to an IntEnum member.
    If it's not a known member, return the numeric value itself.
    """
    if enum is None:
        return num
    else:
        try:
            return socket.AddressFamily(num)
        except (ValueError, AttributeError):
            return num


def socktype_to_enum(num):
    """Convert a numeric socket type value to an IntEnum member.
    If it's not a known member, return the numeric value itself.
    """
    if enum is None:
        return num
    else:
        try:
            return socket.AddressType(num)
        except (ValueError, AttributeError):
            return num


def deprecated_method(replacement):
    """A decorator which can be used to mark a method as deprecated
    'replcement' is the method name which will be called instead.
    """
    def outer(fun):
        msg = "%s() is deprecated; use %s() instead" % (
            fun.__name__, replacement)
        if fun.__doc__ is None:
            fun.__doc__ = msg

        @functools.wraps(fun)
        def inner(self, *args, **kwargs):
            warnings.warn(msg, category=DeprecationWarning, stacklevel=2)
            return getattr(self, replacement)(*args, **kwargs)
        return inner
    return outer


# --- Process.connections() 'kind' parameter mapping

conn_tmap = {
    "all": ([AF_INET, AF_INET6, AF_UNIX], [SOCK_STREAM, SOCK_DGRAM]),
    "tcp": ([AF_INET, AF_INET6], [SOCK_STREAM]),
    "tcp4": ([AF_INET], [SOCK_STREAM]),
    "udp": ([AF_INET, AF_INET6], [SOCK_DGRAM]),
    "udp4": ([AF_INET], [SOCK_DGRAM]),
    "inet": ([AF_INET, AF_INET6], [SOCK_STREAM, SOCK_DGRAM]),
    "inet4": ([AF_INET], [SOCK_STREAM, SOCK_DGRAM]),
    "inet6": ([AF_INET6], [SOCK_STREAM, SOCK_DGRAM]),
}

if AF_INET6 is not None:
    conn_tmap.update({
        "tcp6": ([AF_INET6], [SOCK_STREAM]),
        "udp6": ([AF_INET6], [SOCK_DGRAM]),
    })

if AF_UNIX is not None:
    conn_tmap.update({
        "unix": ([AF_UNIX], [SOCK_STREAM, SOCK_DGRAM]),
    })

del AF_INET, AF_INET6, AF_UNIX, SOCK_STREAM, SOCK_DGRAM


# --- namedtuples for psutil.* system-related functions

# psutil.swap_memory()
sswap = namedtuple('sswap', ['total', 'used', 'free', 'percent', 'sin',
                             'sout'])
# psutil.disk_usage()
sdiskusage = namedtuple('sdiskusage', ['total', 'used', 'free', 'percent'])
# psutil.disk_io_counters()
sdiskio = namedtuple('sdiskio', ['read_count', 'write_count',
                                 'read_bytes', 'write_bytes',
                                 'read_time', 'write_time'])
# psutil.disk_partitions()
sdiskpart = namedtuple('sdiskpart', ['device', 'mountpoint', 'fstype', 'opts'])
# psutil.net_io_counters()
snetio = namedtuple('snetio', ['bytes_sent', 'bytes_recv',
                               'packets_sent', 'packets_recv',
                               'errin', 'errout',
                               'dropin', 'dropout'])
# psutil.users()
suser = namedtuple('suser', ['name', 'terminal', 'host', 'started'])
# psutil.net_connections()
sconn = namedtuple('sconn', ['fd', 'family', 'type', 'laddr', 'raddr',
                             'status', 'pid'])
# psutil.net_if_addrs()
snic = namedtuple('snic', ['family', 'address', 'netmask', 'broadcast', 'ptp'])
# psutil.net_if_stats()
snicstats = namedtuple('snicstats', ['isup', 'duplex', 'speed', 'mtu'])


# --- namedtuples for psutil.Process methods

# psutil.Process.cpu_times()
pcputimes = namedtuple('pcputimes', ['user', 'system'])
# psutil.Process.open_files()
popenfile = namedtuple('popenfile', ['path', 'fd'])
# psutil.Process.threads()
pthread = namedtuple('pthread', ['id', 'user_time', 'system_time'])
# psutil.Process.uids()
puids = namedtuple('puids', ['real', 'effective', 'saved'])
# psutil.Process.gids()
pgids = namedtuple('pgids', ['real', 'effective', 'saved'])
# psutil.Process.io_counters()
pio = namedtuple('pio', ['read_count', 'write_count',
                         'read_bytes', 'write_bytes'])
# psutil.Process.ionice()
pionice = namedtuple('pionice', ['ioclass', 'value'])
# psutil.Process.ctx_switches()
pctxsw = namedtuple('pctxsw', ['voluntary', 'involuntary'])
# psutil.Process.connections()
pconn = namedtuple('pconn', ['fd', 'family', 'type', 'laddr', 'raddr',
                             'status'])
