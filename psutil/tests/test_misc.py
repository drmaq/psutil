#!/usr/bin/env python

# Copyright (c) 2009, Giampaolo Rodola'. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import ast
import errno
import imp
import json
import os
import pickle
import psutil
import socket
import stat
import sys

from psutil import LINUX
from psutil import NETBSD
from psutil import OPENBSD
from psutil import OSX
from psutil import POSIX
from psutil import WINDOWS
from psutil._common import supports_ipv6
from psutil.tests import APPVEYOR
from psutil.tests import SCRIPTS_DIR
from psutil.tests import importlib
from psutil.tests import mock
from psutil.tests import ROOT_DIR
from psutil.tests import run_test_module_by_name
from psutil.tests import sh
from psutil.tests import TOX
from psutil.tests import TRAVIS
from psutil.tests import unittest


# ===================================================================
# --- Misc tests
# ===================================================================

class TestMisc(unittest.TestCase):
    """Misc / generic tests."""

    def test_process__repr__(self, func=repr):
        p = psutil.Process()
        r = func(p)
        self.assertIn("psutil.Process", r)
        self.assertIn("pid=%s" % p.pid, r)
        self.assertIn("name=", r)
        self.assertIn(p.name(), r)
        with mock.patch.object(psutil.Process, "name",
                               side_effect=psutil.ZombieProcess(os.getpid())):
            p = psutil.Process()
            r = func(p)
            self.assertIn("pid=%s" % p.pid, r)
            self.assertIn("zombie", r)
            self.assertNotIn("name=", r)
        with mock.patch.object(psutil.Process, "name",
                               side_effect=psutil.NoSuchProcess(os.getpid())):
            p = psutil.Process()
            r = func(p)
            self.assertIn("pid=%s" % p.pid, r)
            self.assertIn("terminated", r)
            self.assertNotIn("name=", r)
        with mock.patch.object(psutil.Process, "name",
                               side_effect=psutil.AccessDenied(os.getpid())):
            p = psutil.Process()
            r = func(p)
            self.assertIn("pid=%s" % p.pid, r)
            self.assertNotIn("name=", r)

    def test_process__str__(self):
        self.test_process__repr__(func=str)

    def test_no_such_process__repr__(self, func=repr):
        self.assertEqual(
            repr(psutil.NoSuchProcess(321)),
            "psutil.NoSuchProcess process no longer exists (pid=321)")
        self.assertEqual(
            repr(psutil.NoSuchProcess(321, name='foo')),
            "psutil.NoSuchProcess process no longer exists (pid=321, "
            "name='foo')")
        self.assertEqual(
            repr(psutil.NoSuchProcess(321, msg='foo')),
            "psutil.NoSuchProcess foo")

    def test_zombie_process__repr__(self, func=repr):
        self.assertEqual(
            repr(psutil.ZombieProcess(321)),
            "psutil.ZombieProcess process still exists but it's a zombie "
            "(pid=321)")
        self.assertEqual(
            repr(psutil.ZombieProcess(321, name='foo')),
            "psutil.ZombieProcess process still exists but it's a zombie "
            "(pid=321, name='foo')")
        self.assertEqual(
            repr(psutil.ZombieProcess(321, name='foo', ppid=1)),
            "psutil.ZombieProcess process still exists but it's a zombie "
            "(pid=321, name='foo', ppid=1)")
        self.assertEqual(
            repr(psutil.ZombieProcess(321, msg='foo')),
            "psutil.ZombieProcess foo")

    def test_access_denied__repr__(self, func=repr):
        self.assertEqual(
            repr(psutil.AccessDenied(321)),
            "psutil.AccessDenied (pid=321)")
        self.assertEqual(
            repr(psutil.AccessDenied(321, name='foo')),
            "psutil.AccessDenied (pid=321, name='foo')")
        self.assertEqual(
            repr(psutil.AccessDenied(321, msg='foo')),
            "psutil.AccessDenied foo")

    def test_timeout_expired__repr__(self, func=repr):
        self.assertEqual(
            repr(psutil.TimeoutExpired(321)),
            "psutil.TimeoutExpired timeout after 321 seconds")
        self.assertEqual(
            repr(psutil.TimeoutExpired(321, pid=111)),
            "psutil.TimeoutExpired timeout after 321 seconds (pid=111)")
        self.assertEqual(
            repr(psutil.TimeoutExpired(321, pid=111, name='foo')),
            "psutil.TimeoutExpired timeout after 321 seconds "
            "(pid=111, name='foo')")

    def test_process__eq__(self):
        p1 = psutil.Process()
        p2 = psutil.Process()
        self.assertEqual(p1, p2)
        p2._ident = (0, 0)
        self.assertNotEqual(p1, p2)
        self.assertNotEqual(p1, 'foo')

    def test_process__hash__(self):
        s = set([psutil.Process(), psutil.Process()])
        self.assertEqual(len(s), 1)

    def test__all__(self):
        dir_psutil = dir(psutil)
        for name in dir_psutil:
            if name in ('callable', 'error', 'namedtuple', 'tests',
                        'long', 'test', 'NUM_CPUS', 'BOOT_TIME',
                        'TOTAL_PHYMEM'):
                continue
            if not name.startswith('_'):
                try:
                    __import__(name)
                except ImportError:
                    if name not in psutil.__all__:
                        fun = getattr(psutil, name)
                        if fun is None:
                            continue
                        if (fun.__doc__ is not None and
                                'deprecated' not in fun.__doc__.lower()):
                            self.fail('%r not in psutil.__all__' % name)

        # Import 'star' will break if __all__ is inconsistent, see:
        # https://github.com/giampaolo/psutil/issues/656
        # Can't do `from psutil import *` as it won't work on python 3
        # so we simply iterate over __all__.
        for name in psutil.__all__:
            self.assertIn(name, dir_psutil)

    def test_version(self):
        self.assertEqual('.'.join([str(x) for x in psutil.version_info]),
                         psutil.__version__)

    def test_memoize(self):
        from psutil._common import memoize

        @memoize
        def foo(*args, **kwargs):
            "foo docstring"
            calls.append(None)
            return (args, kwargs)

        calls = []
        # no args
        for x in range(2):
            ret = foo()
            expected = ((), {})
            self.assertEqual(ret, expected)
            self.assertEqual(len(calls), 1)
        # with args
        for x in range(2):
            ret = foo(1)
            expected = ((1, ), {})
            self.assertEqual(ret, expected)
            self.assertEqual(len(calls), 2)
        # with args + kwargs
        for x in range(2):
            ret = foo(1, bar=2)
            expected = ((1, ), {'bar': 2})
            self.assertEqual(ret, expected)
            self.assertEqual(len(calls), 3)
        # clear cache
        foo.cache_clear()
        ret = foo()
        expected = ((), {})
        self.assertEqual(ret, expected)
        self.assertEqual(len(calls), 4)
        # docstring
        self.assertEqual(foo.__doc__, "foo docstring")

    def test_parse_environ_block(self):
        from psutil._common import parse_environ_block

        def k(s):
            return s.upper() if WINDOWS else s

        self.assertEqual(parse_environ_block("a=1\0"),
                         {k("a"): "1"})
        self.assertEqual(parse_environ_block("a=1\0b=2\0\0"),
                         {k("a"): "1", k("b"): "2"})
        self.assertEqual(parse_environ_block("a=1\0b=\0\0"),
                         {k("a"): "1", k("b"): ""})
        # ignore everything after \0\0
        self.assertEqual(parse_environ_block("a=1\0b=2\0\0c=3\0"),
                         {k("a"): "1", k("b"): "2"})
        # ignore everything that is not an assignment
        self.assertEqual(parse_environ_block("xxx\0a=1\0"), {k("a"): "1"})
        self.assertEqual(parse_environ_block("a=1\0=b=2\0"), {k("a"): "1"})
        # do not fail if the block is incomplete
        self.assertEqual(parse_environ_block("a=1\0b=2"), {k("a"): "1"})

    def test_supports_ipv6(self):
        if supports_ipv6():
            with mock.patch('psutil._common.socket') as s:
                s.has_ipv6 = False
                assert not supports_ipv6()
            with mock.patch('psutil._common.socket.socket',
                            side_effect=socket.error) as s:
                assert not supports_ipv6()
                assert s.called
            with mock.patch('psutil._common.socket.socket',
                            side_effect=socket.gaierror) as s:
                assert not supports_ipv6()
                assert s.called
            with mock.patch('psutil._common.socket.socket.bind',
                            side_effect=socket.gaierror) as s:
                assert not supports_ipv6()
                assert s.called
        else:
            if hasattr(socket, 'AF_INET6'):
                with self.assertRaises(Exception):
                    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                    sock.bind(("::1", 0))

    def test_isfile_strict(self):
        from psutil._common import isfile_strict
        this_file = os.path.abspath(__file__)
        assert isfile_strict(this_file)
        assert not isfile_strict(os.path.dirname(this_file))
        with mock.patch('psutil._common.os.stat',
                        side_effect=OSError(errno.EPERM, "foo")):
            self.assertRaises(OSError, isfile_strict, this_file)
        with mock.patch('psutil._common.os.stat',
                        side_effect=OSError(errno.EACCES, "foo")):
            self.assertRaises(OSError, isfile_strict, this_file)
        with mock.patch('psutil._common.os.stat',
                        side_effect=OSError(errno.EINVAL, "foo")):
            assert not isfile_strict(this_file)
        with mock.patch('psutil._common.stat.S_ISREG', return_value=False):
            assert not isfile_strict(this_file)

    def test_serialization(self):
        def check(ret):
            if json is not None:
                json.loads(json.dumps(ret))
            a = pickle.dumps(ret)
            b = pickle.loads(a)
            self.assertEqual(ret, b)

        check(psutil.Process().as_dict())
        check(psutil.virtual_memory())
        check(psutil.swap_memory())
        check(psutil.cpu_times())
        check(psutil.cpu_times_percent(interval=0))
        check(psutil.net_io_counters())
        if LINUX and not os.path.exists('/proc/diskstats'):
            pass
        else:
            if not APPVEYOR:
                check(psutil.disk_io_counters())
        check(psutil.disk_partitions())
        check(psutil.disk_usage(os.getcwd()))
        check(psutil.users())

    def test_setup_script(self):
        setup_py = os.path.join(ROOT_DIR, 'setup.py')
        module = imp.load_source('setup', setup_py)
        self.assertRaises(SystemExit, module.setup)
        self.assertEqual(module.get_version(), psutil.__version__)

    def test_ad_on_process_creation(self):
        # We are supposed to be able to instantiate Process also in case
        # of zombie processes or access denied.
        with mock.patch.object(psutil.Process, 'create_time',
                               side_effect=psutil.AccessDenied) as meth:
            psutil.Process()
            assert meth.called
        with mock.patch.object(psutil.Process, 'create_time',
                               side_effect=psutil.ZombieProcess(1)) as meth:
            psutil.Process()
            assert meth.called
        with mock.patch.object(psutil.Process, 'create_time',
                               side_effect=ValueError) as meth:
            with self.assertRaises(ValueError):
                psutil.Process()
            assert meth.called

    def test_psutil_is_reloadable(self):
        importlib.reload(psutil)

    def test_sanity_version_check(self):
        # see: https://github.com/giampaolo/psutil/issues/564
        try:
            with mock.patch(
                    "psutil._psplatform.cext.version", return_value="0.0.0"):
                with self.assertRaises(ImportError) as cm:
                    importlib.reload(psutil)
                self.assertIn("version conflict", str(cm.exception).lower())
        finally:
            importlib.reload(psutil)

    def test_memory_percent_0_division(self):
        import collections
        try:
            retval = collections.namedtuple("mem", "total")(0)
            with mock.patch(
                    "psutil._psplatform.virtual_memory", return_value=retval):
                self.assertRaises(ValueError, psutil.Process().memory_percent)
        finally:
            importlib.reload(psutil)


# ===================================================================
# --- Example script tests
# ===================================================================

@unittest.skipIf(TOX, "can't test on tox")
class TestScripts(unittest.TestCase):
    """Tests for scripts in the "scripts" directory."""

    def assert_stdout(self, exe, args=None):
        exe = os.path.join(SCRIPTS_DIR, exe)
        if args:
            exe = exe + ' ' + args
        try:
            out = sh(sys.executable + ' ' + exe).strip()
        except RuntimeError as err:
            if 'AccessDenied' in str(err):
                return str(err)
            else:
                raise
        assert out, out
        return out

    def assert_syntax(self, exe, args=None):
        exe = os.path.join(SCRIPTS_DIR, exe)
        with open(exe, 'r') as f:
            src = f.read()
        ast.parse(src)

    def test_check_presence(self):
        # make sure all example scripts have a test method defined
        meths = dir(self)
        for name in os.listdir(SCRIPTS_DIR):
            if name.endswith('.py'):
                if 'test_' + os.path.splitext(name)[0] not in meths:
                    # self.assert_stdout(name)
                    self.fail('no test defined for %r script'
                              % os.path.join(SCRIPTS_DIR, name))

    @unittest.skipUnless(POSIX, "UNIX only")
    def test_executable(self):
        for name in os.listdir(SCRIPTS_DIR):
            if name.endswith('.py'):
                path = os.path.join(SCRIPTS_DIR, name)
                if not stat.S_IXUSR & os.stat(path)[stat.ST_MODE]:
                    self.fail('%r is not executable' % path)

    def test_disk_usage(self):
        self.assert_stdout('disk_usage.py')

    def test_free(self):
        self.assert_stdout('free.py')

    def test_meminfo(self):
        self.assert_stdout('meminfo.py')

    def test_procinfo(self):
        self.assert_stdout('procinfo.py')

    @unittest.skipIf(APPVEYOR, "can't find users on Appveyor")
    def test_who(self):
        self.assert_stdout('who.py')

    def test_ps(self):
        self.assert_stdout('ps.py')

    def test_pstree(self):
        self.assert_stdout('pstree.py')

    def test_netstat(self):
        self.assert_stdout('netstat.py')

    @unittest.skipIf(TRAVIS, "permission denied on travis")
    def test_ifconfig(self):
        self.assert_stdout('ifconfig.py')

    @unittest.skipIf(OPENBSD or NETBSD, "memory maps not supported")
    def test_pmap(self):
        self.assert_stdout('pmap.py', args=str(os.getpid()))

    @unittest.skipUnless(OSX or WINDOWS or LINUX, "uss not available")
    def test_procsmem(self):
        self.assert_stdout('procsmem.py')

    @unittest.skipIf(ast is None,
                     'ast module not available on this python version')
    def test_killall(self):
        self.assert_syntax('killall.py')

    @unittest.skipIf(ast is None,
                     'ast module not available on this python version')
    def test_nettop(self):
        self.assert_syntax('nettop.py')

    @unittest.skipIf(ast is None,
                     'ast module not available on this python version')
    def test_top(self):
        self.assert_syntax('top.py')

    @unittest.skipIf(ast is None,
                     'ast module not available on this python version')
    def test_iotop(self):
        self.assert_syntax('iotop.py')

    def test_pidof(self):
        output = self.assert_stdout('pidof.py %s' % psutil.Process().name())
        self.assertIn(str(os.getpid()), output)


if __name__ == '__main__':
    run_test_module_by_name(__file__)
