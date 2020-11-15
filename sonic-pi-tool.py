#!/usr/bin/env python3
# coding: utf-8

import click
import glob
import html
import os
import platform
import psutil
import queue
import re
import socket
import subprocess
import sys
import threading
import time

from oscpy.server import OSCThreadServer
from oscpy.client import OSCClient

SERVER_OUTPUT = "~/.sonic-pi/log/server-output.log"
SERVER_ERRORS = "~/.sonic-pi/log/server-errors.log"


class Logger:
    def __init__(self, verbose):
        self.verbose = verbose

    def __call__(self, message, high=False):
        if high or self.verbose:
            print(message)


class Installation:
    """Represents a Sonic Pi installation. Used for starting the Sonic Pi server."""

    default_paths = ('./Sonic Pi.app/Contents/Resources/app',  # Check current dir first
                     './Sonic Pi.app',
                     './Sonic Pi/app',
                     './app',
                     '~/Applications/Sonic Pi.app/Contents/Resources/app',  # Then home dir
                     '~/Applications/Sonic Pi.app',
                     '~/Sonic Pi/app',
                     '/Applications/Sonic Pi.app/Contents/Resources/app',  # Finally standard dirs
                     '/Applications/Sonic Pi.app',
                     'c:/Program Files/Sonic Pi/app',
                     '/opt/sonic-pi-*/app',
                     '/opt/sonic-pi/app',
                     '/usr/bin/sonic-pi-*',
                     '/usr/bin/sonic-pi',
                     '/usr/lib/sonic-pi')
    ruby_paths = ['server/native/ruby/bin/ruby',
                  'server/native/ruby/bin/ruby.exe']
    server_paths = ['server/ruby/bin/sonic-pi-server.rb',
                    'server/bin/sonic-pi-server.rb']

    @staticmethod
    def get_installation(paths, verbose):
        logger = Logger(verbose)
        for pp in paths + Installation.default_paths:
            for p in reversed(glob.glob(pp)):
                inst = Installation(p, logger)
                if inst.exists():
                    inst.log("Found installation at: {}".format(inst.base))
                    return inst
        logger("I couldn't find the Sonic Pi server executable :(", True)

    def __init__(self, base, logger):
        self.log = logger
        self.base = os.path.expanduser(base)
        self.ruby = None
        for i, path in enumerate(Installation.ruby_paths):
            if os.path.isfile(self.expand_path(path)):
                self.ruby = i
                break
        self.server = None
        for i, path in enumerate(Installation.server_paths):
            if os.path.isfile(self.expand_path(path)):
                self.server = i
                break

    def exists(self):
        return self.server is not None

    def expand_path(self, path):
        return os.path.normpath(os.path.join(self.base, path))

    def ruby_path(self):
        if self.ruby is None:
            return 'ruby'
        else:
            return self.expand_path(Installation.ruby_paths[self.ruby])

    def server_path(self):
        return self.expand_path(Installation.server_paths[self.server])

    def run(self, background, callback):
        args = [self.ruby_path(), '-E', 'utf-8']
        if platform.system in ['Darwin', 'Windows']:
            args.append('--enable-frozen-string-literal')
        args.append(self.server_path())
        self.log("Running: {}".format(' '.join(args)))
        out = os.path.expanduser(SERVER_OUTPUT)
        err = os.path.expanduser(SERVER_ERRORS)
        q = queue.Queue(1)

        def outfun(line):
            print(line[:-1])
            if line.startswith('Sonic Pi Server successfully booted'):
                q.put(True)

        def errfun(line):
            print("ERROR: " + line[:-1])

        with open(out, 'w') as outfile:
            with open(err, 'w') as errfile:
                process = subprocess.Popen(args, text=True, bufsize=1,
                                           stdout=outfile, stderr=errfile)
                Installation.background_tail(out, outfun)
                Installation.background_tail(err, errfun)
                ok = False
                for _ in range(30):
                    try:
                        process.wait(timeout=1)
                        break
                    except subprocess.TimeoutExpired:
                        pass
                    try:
                        ok = q.get_nowait()
                        break
                    except queue.Empty:
                        ok = False
                if process.poll() is not None:
                    self.log("Sonic Pi server failed to start", True)
                    return 1
                if callback is not None:
                    callback()
                if background:
                    if ok:
                        self.log("Sonic Pi started, leaving it in the background now", True)
                        return 0
                    else:
                        self.log("Sonic Pi doesn't seem to have started yet, "
                                 "but leaving it in the background now", True)
                        return 1
                ret = process.wait()
                if ret:
                    self.log("Sonic Pi server quit with error code {}".format(ret), True)
                    return 1
                self.log("Sonic Pi server has now quit", True)
                return 0

    @staticmethod
    def background_tail(fname, func):
        def tail():
            with open(fname, 'r') as f:
                line = ''
                while True:
                    tmp = f.readline()
                    if tmp:
                        line += tmp
                        if line.endswith('\n'):
                            func(line)
                            line = ''
                    else:
                        time.sleep(0.1)

        thread = threading.Thread(target=tail)
        thread.daemon = True
        thread.start()
        return thread


class Server:
    """Represents a running instance of Sonic Pi."""

    preamble = '@osc_server||=SonicPi::OSC::UDPServer.new' + \
               '({},use_decoder_cache:true) #__nosave__\n'
    styles = {
        # Info message
        'info': {'bold': True, 'reverse': True},
        # Multi message and different subtypes
        'multi': {'bold': True},
        0: {'bold': True, 'fg': 'magenta'},
        1: {'bold': True, 'fg': 'blue'},
        2: {'bold': True, 'fg': 'yellow'},
        3: {'bold': True, 'fg': 'red'},
        4: {'bold': True, 'bg': 'magenta'},
        5: {'bold': True, 'bg': 'blue'},
        6: {'bold': True, 'bg': 'yellow'},
        # Runtime error and trace
        'runtime': {'bold': True, 'bg': 'magenta'},
        'trace': {},
        # Syntax error and line + code
        'syntax': {'bold': True, 'bg': 'blue'},
        'line': {'bold': True, 'fg': 'magenta'},
        'code': {}}

    def __init__(self, host, cmd_port, osc_port, send_preamble, verbose):
        self.client_name = 'SONIC_PI_TOOL_PY'
        self.log = Logger(verbose)
        self.host = host
        self._cmd_port = cmd_port
        self._cached_cmd_port = None
        self.osc_port = osc_port
        # fix for https://github.com/repl-electric/sonic-pi.el/issues/19#issuecomment-345222832
        self.send_preamble = send_preamble
        self._cmd_client = None
        self._osc_client = None

    def get_cmd_port(self):
        if self._cached_cmd_port is None:
            if self._cmd_port > 0:
                self._cached_cmd_port = self._cmd_port
                self.log("Using command port of {}".format(self._cached_cmd_port))
            else:
                self._cached_cmd_port = Server.determine_command_port()
                if self._cached_cmd_port is not None:
                    self.log("Found command port in log: {}".format(self._cached_cmd_port))
                else:
                    self._cached_cmd_port = -self._cmd_port
                    self.log(("Couldn't find command port in log, using {}"
                              .format(self._cached_cmd_port)))
        return self._cached_cmd_port

    def cmd_client(self):
        if self._cmd_client is None:
            self._cmd_client = OSCClient(self.host, self.get_cmd_port(),
                                         encoding='utf8')
        return self._cmd_client

    def osc_client(self):
        if self._osc_client is None:
            self._osc_client = OSCClient(self.host, self.osc_port,
                                         encoding='utf8')
        return self._osc_client

    def get_preamble(self):
        if self.send_preamble:
            return Server.preamble.format(self.get_cmd_port())
        return ''

    def send_cmd(self, msg, *args):
        client = self.cmd_client()
        self.log("Sending command to {}:{}: {} {}"
                 .format(self.host, self.get_cmd_port(), msg,
                         ', '.join(repr(v) for v in (self.client_name,) + args)))
        client.send_message(msg, (self.client_name,) + args)

    def send_osc(self, path, args):
        def parse_val(s):
            try:
                return int(s)
            except ValueError:
                pass
            try:
                return float(s)
            except ValueError:
                pass
            if len(s) > 1 and s[0] == '"' and s[-1] == '"':
                return s[1:-1]
            return s

        client = self.osc_client()
        parsed = [parse_val(s) for s in args]
        self.log("Sending OSC message to {}:{}: {} {}"
                 .format(self.host, self.osc_port, path,
                         ', '.join(repr(v) for v in parsed)))
        client.send_message(path, parsed)

    def check_if_running(self):
        cmd_listening = Server.port_in_use(self.get_cmd_port())
        self.log("The command port ({}) is {}in use".format(self.get_cmd_port(),
                                                            "" if cmd_listening else "not "))
        osc_listening = Server.port_in_use(self.osc_port)
        self.log("The OSC port ({}) is {}in use".format(self.osc_port,
                                                        "" if osc_listening else "not "))
        if cmd_listening and osc_listening:
            self.log("Sonic Pi is running, and listening on port {} for commands and {} for OSC"
                     .format(self.get_cmd_port(), self.osc_port), True)
            return 0
        elif not cmd_listening and not osc_listening:
            self.log("Sonic Pi is not running", True)
            return 1
        else:
            self.log("Sonic Pi is not running properly, or there's an issue with the port numbers",
                     True)
            return 2

    def stop_all_jobs(self):
        self.send_cmd('/stop-all-jobs')

    def run_code(self, code):
        self.send_cmd('/run-code', self.get_preamble() + code)

    def start_recording(self):
        self.send_cmd('/start-recording')

    def stop_and_save_recording(self, path):
        self.send_cmd('/stop-recording')
        self.send_cmd('/save-recording', path)

    @staticmethod
    def port_in_use(port):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            try:
                sock.bind(('127.0.0.1', port))
            except OSError:
                return True
        return False

    @staticmethod
    def determine_command_port():
        try:
            with open(os.path.expanduser(SERVER_OUTPUT)) as f:
                for line in f:
                    m = re.search('^Listen port: *([0-9]+)', line)
                    if m:
                        return int(m.groups()[0])
        except FileNotFoundError:
            pass

    @staticmethod
    def printc(*txt_style):
        """Print with colour. Takes pairs of text and style (dict, or key into
        Server.styles)"""
        r = ''
        for i in range(0, len(txt_style), 2):
            txt, style = txt_style[i: i+2]
            if not isinstance(style, dict):
                try:
                    style = Server.styles[style]
                except KeyError:
                    style = {}
            r += click.style(txt, **style)
        click.echo(r)

    @staticmethod
    def handle_log_info(style, msg):
        msg = "=> {}".format(msg)
        Server.printc(msg, 'info')
        click.echo()

    @staticmethod
    def handle_multi_message(run, thread, time, n, *msgs):
        msg = "{{run: {}, time: {}}}".format(run, time)
        Server.printc(msg, 'multi')
        for i in range(n):
            typ, msg = msgs[2*i: 2*i+2]
            for j, line in enumerate(msg.splitlines()):
                if i < n - 1:
                    prefix = "  ├─ " if j == 0 else "  │"
                else:
                    prefix = "  └─ " if j == 0 else "   "
                Server.printc(prefix, 'multi', line, typ)
        click.echo()

    @staticmethod
    def handle_runtime_error(run, msg, trace, line_num):
        lines = html.unescape(msg).splitlines()
        prefix = "Runtime Error: "
        for line in lines:
            Server.printc(prefix + line, 'runtime')
            prefix = ""
        Server.printc(html.unescape(trace), 'trace')
        click.echo()

    @staticmethod
    def handle_syntax_error(run, msg, code, line_num, line_s):
        Server.printc("Error: " + html.unescape(msg), 'syntax')
        prefix = "[Line {}]: ".format(line_num) if line_num >= 0 else ""
        Server.printc(prefix, 'line', code, 'code')

    def follow_logs(self):
        try:
            server = OSCThreadServer(encoding='utf8')
            server.listen(address='127.0.0.1', port=4558, default=True)
            server.bind('/log/multi_message', self.handle_multi_message)
            server.bind('/multi_message', self.handle_multi_message)
            server.bind('/log/info', self.handle_log_info)
            server.bind('/info', self.handle_log_info)
            server.bind('/error', self.handle_runtime_error)
            server.bind('/syntax_error', self.handle_syntax_error)
            while True:
                time.sleep(1)
        except Exception as e:
            return e

    def kill_process(self, name, exe, arg=None):
        exe_re = re.compile(exe.replace('/', r'[/\\]') + '$', re.IGNORECASE)
        if arg:
            arg_re = re.compile(arg.replace('/', r'[/\\]') + '$', re.IGNORECASE)
        for p in psutil.process_iter():
            try:
                # Put in a try block because it can throw if the process has stopped
                m = re.match(exe_re, p.exe())
                if m and arg:
                    m = [c for c in p.cmdline() if re.match(arg_re, c)]
            except Exception:
                m = False
            if m:
                self.log("Found {} with pid {} at {}"
                         .format(name, p.pid, p.exe()))
                try:
                    p.terminate()
                    psutil.wait_procs([p], timeout=5)
                except psutil.Error:
                    pass
                if not p.is_running():
                    return True
                self.log("Failed to terminate {} nicely, let's try something else"
                         .format(name))
                try:
                    p.kill()
                    psutil.wait_procs([p], timeout=2)
                except psutil.Error:
                    pass
                if not p.is_running():
                    return True
                self.log("Error shutting down {}".format(name), True)
                return False
        return False

    def shutdown_sonic_pi(self):
        full = False
        full += self.kill_process('GUI', '.*/Sonic[ -]Pi([.]exe)?')
        full += self.kill_process('Server', '.*/ruby([.]exe)?$', '.*/sonic-pi-server.rb')
        part = False
        part += self.kill_process('SCSynth', '.*/app/server/native/scsynth([.]exe)?')
        part += self.kill_process('Erlang', '.*/app/server/native/.*/(beam[.]smp|erl([.]exe)?)')
        part += self.kill_process('o2m', '.*/app/server/native/.*/o2m([.]exe)?')
        part += self.kill_process('m2o', '.*/app/server/native/.*/m2o([.]exe)?')
        if full:
            self.log("Sonic Pi has been shut down", True)
        elif part:
            self.log("Partial Sonic Pi processes have been shut down", True)
        else:
            self.log("No Sonic Pi processes were found to shut down", True)


CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'],
                        token_normalize_func=lambda x:
                        x.lower().replace('-', '_'))


@click.group(context_settings=CONTEXT_SETTINGS)
@click.option('--host', default='127.0.0.1',
              help="IP or hostname of Sonic Pi server.")
@click.option('--cmd-port', default=-4557,
              help="Port number of Sonic Pi command server "
              "(-ve = determine from logs if possible).")
@click.option('--osc-port', default=4560,
              help="Port number of Sonic Pi OSC cue server.")
@click.option('--preamble/--no-preamble',
              help="Send preamble to enable OSC server (needed on some Sonic Pi versions).")
@click.option('--verbose/--no-verbose',
              help="Print more information to help with debugging.")
@click.pass_context
def cli(ctx, host, cmd_port, osc_port, preamble, verbose):
    ctx.obj = Server(host, cmd_port, osc_port, preamble, verbose)


@cli.command(help="Check if Sonic Pi server is running.")
@click.pass_context
def check(ctx):
    sys.exit(ctx.obj.check_if_running())


@cli.command(help="Send code to the server to be played.")
@click.argument('code', nargs=-1, required=True)
@click.pass_context
def eval(ctx, code):
    ctx.obj.run_code(' '.join(code))


@cli.command(help="Send code from stdin to be played.")
@click.pass_context
def eval_stdin(ctx):
    ctx.obj.run_code(sys.stdin.read())


@cli.command(help="Send code from a file to be played.")
@click.argument('path', type=click.File('r'))
@click.pass_context
def eval_file(ctx, path):
    ctx.obj.run_code(path.read())


@cli.command(help="Tell server to play file (for big files).")
@click.argument('path', type=click.Path(exists=True))
@click.pass_context
def run_file(ctx, path):
    cmd = 'run_file "{}"'.format(os.path.abspath(path).replace('\\', '\\\\')
                                 .replace('"', '\\"'))
    ctx.obj.run_code(cmd)


@cli.command(help="Send an OSC cue to a running Sonic Pi script.")
@click.argument('path', required=True)
@click.argument('args', nargs=-1)
@click.pass_context
def osc(ctx, path, args):
    ctx.obj.send_osc(path, args)


@cli.command(help="Try to locate Sonic Pi server and start it.")
@click.option('--path', multiple=True, type=click.Path(exists=True),
              help="Path to Sonic Pi app to try before defaults, "
              "may be specified multiple times.")
@click.option('--background/--foreground',
              help="Run server process in the background.")
@click.option('--cue-server', type=click.Choice(['internal', 'external', 'off']),
              default='internal',
              help="Change cue server configuration (default is internal listener).")
@click.pass_context
def start_server(ctx, path, background, cue_server):
    def setup_server():
        if cue_server == 'off':
            ctx.obj.send_cmd('/cue-port-stop')
        else:
            ctx.obj.send_cmd('/cue-port-start')
            if cue_server == 'internal':
                ctx.obj.send_cmd('/cue-port-internal')
            elif cue_server == 'external':
                ctx.obj.send_cmd('/cue-port-external')

    inst = Installation.get_installation(path, ctx.parent.params['verbose'])
    if inst:
        sys.exit(inst.run(background, setup_server))
    sys.exit(1)


@cli.command(help="Shut down any Sonic Pi processes.")
@click.pass_context
def shutdown(ctx):
    ctx.obj.shutdown_sonic_pi()


@cli.command(help="Stop all jobs running on the server.")
@click.pass_context
def stop(ctx):
    ctx.obj.stop_all_jobs()


@cli.command(help="Print logs emitted by the Sonic Pi server.")
@click.pass_context
def logs(ctx):
    err = ctx.obj.follow_logs()
    if err:
        ctx.obj.log("""error: Unable to listen for Sonic Pi server logs, address
already in use. This may be because the Sonic Pi GUI is running and already
listening on the desired port. If the GUI is running this command cannot
        function, try running just the Sonic Pi server.""", True)
        sys.exit(1)


@cli.command(help="Record audio output to a local file.")
@click.argument('path')
@click.pass_context
def record(ctx, path):
    ctx.obj.start_recording()
    ctx.obj.log("Recording started, saving to {}".format(path))
    input("Press Enter to stop the recording...")
    ctx.obj.stop_and_save_recording(path)


if __name__ == '__main__':
    cli(obj=None)
