# -*- coding: utf-8 -*-

import re, time, os

from ConfigParser import SafeConfigParser as ConfigParser
from . import util

# DD-Mon-YY HH:MM:SS host user PV new=A old=B [min=C max=D]
_capl = r'(?P<time>\d+-\S+-\d+ \d+:\d+:\d+) (?P<host>\S+) (?P<user>\S+) (?P<pv>\S+)' + \
        r'.*'
#        r' new=(?P<new>\S*) old=(?P<old>\S*) (?:min=(?P<min>\S*) max=(?P<max>\S*))?'

_capl=re.compile(_capl)

class Entry(object):
    def __init__(self, line, peer, rxtime):
        self.line, self.peer, self.rxtime = line, peer, rxtime
        self.user, self.host, self.pv = None, None, None

class Processor(object):
    def __init__(self):
        self.dest = []
        self.addDest = self.dest.append

    def load(self, conf):
        P = ConfigParser()
        with open(conf,'r') as F:
            P.readfp(F)
        C = util.ConfigDict(P, 'processor')

        for name in map(str.strip, C['chain'].split(',')):
            S = util.ConfigDict(P, name)
            D = Destination(S)
            self.addDest(D)

    def proc(self, entries):
        try:
            for D in self.dest:
                D.prepare()
            for src, peer, line, rxtime in entries:
                E = Entry(line.strip(), peer, rxtime)
                M=_capl.match(E.line)
                if M:
                    E.user = M.group('user')
                    E.host = M.group('host')
                    E.pv = M.group('pv')

                for D in self.dest:
                    if D.consume(E):
                        break
        finally:
            for D in self.dest:
                D.cleanup()

class Destination(object):
    def __init__(self, conf):
        self._fname = conf['filename']
        self._maxsize, self._nbackup = conf.getint('maxsize',100*2**20), conf.getint('numbackup', 4)

        self.users = set(filter(len, map(str.strip, conf.get('users','').split(','))))
        self.hosts = set(filter(len, map(str.strip, conf.get('hosts','').split(','))))
        self.filter = conf.getbool('stop',False)

        self.pvs = None
        if 'pvpat' in conf:
            self.pvs = re.compile(conf['pvpat'])

        self.F = None

    def prepare(self):
        if self.F is not None:
            self.F.close()
            self.F = None
        util.rotateFile(self._fname, maxsize=self._maxsize, nbackup=self._nbackup)
        self.F=open(self._fname, 'a')
        os.fchmod(self.F.fileno(), 0644)

    def cleanup(self):
        if self.F is not None:
            self.F.close()
            self.F = None

    def consume(self, E):
        assert self.F is not None
        if (not self.users or E.user in self.users) and \
            (not self.hosts or E.host in self.hosts) and \
            (not self.pvs or self.pvs.match(E.pv or '')):
            # diagioc-br-rgp.cs.nsls2.local:3 Thu Apr  3 18:16:33 2014 ...
            if E.peer:
                src = '%s:%-5d'%(E.peer.host, E.peer.port)
            else:
                src = '0.0.0.0:0    '
            ts = time.strftime('%a %b %d %H:%M:%S %Y', time.localtime(E.rxtime))
            self.F.write('%s %s %s\n'%(src, ts, E.line))
            return self.filter
        return False
