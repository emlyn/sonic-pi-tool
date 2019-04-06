#!/usr/bin/env python
# coding: utf-8

from __future__ import print_function

import click
import os
import socket
import subprocess
import sys
import time

from oscpy.server import OSCThreadServer
from oscpy.client import OSCClient

try:
    import html
except ImportError:
    from HTMLParser import HTMLParser
    html = HTMLParser()

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

class Server:
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

    def __init__(self, host, cmd_port, osc_port):
        # fix for https://github.com/repl-electric/sonic-pi.el/issues/19#issuecomment-345222832
        self.prefix = '@osc_server||=SonicPi::OSC::UDPServer.new(4559,use_decoder_cache:true) #__nosave__\n'
        self.client_name = 'SONIC_PI_TOOL_PY'
        self.host = host
        self.cmd_port = cmd_port
        self.osc_port = osc_port
        self.cmd_client = None
        self.osc_client = None

    def send_cmd(self, msg, *args):
        if self.cmd_client is None:
            self.cmd_client = OSCClient(self.host, self.cmd_port, encoding='utf8')
        self.cmd_client.send_message(msg, (self.client_name,) + args)

    def send_osc(self, path, args):
        if self.osc_client is None:
            self.osc_client = OSCClient(self.host, self.osc_port, encoding='utf8')
        self.osc_client.send_message(path, [parse_val(s) for s in args])

    def server_port_in_use(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            try:
                sock.bind(('127.0.0.1', self.port))
            except OSError:
                return True
        return False

    def stop_all_jobs(self):
        self.send_cmd('/stop-all-jobs')

    def run_code(self, code):
        self.send_cmd('/run-code', self.prefix + code)

    def start_recording(self):
        self.send_cmd('/start-recording')

    def stop_and_save_recording(self, path):
        self.send_cmd('/stop-recording')
        self.send_cmd('/save-recording', path)

    @staticmethod
    def printc(*txt_style):
        """Print with colour. Takes pairs of text and style (dict, or key into Server.styles)"""
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
            sock = server.listen(address='127.0.0.1', port=4558, default=True)
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

class Installation:
    ruby_paths = ['server/native/ruby/bin/ruby']
    server_paths = ['server/ruby/bin/sonic-pi-server.rb',
                    'server/bin/sonic-pi-server.rb']
    def __init__(self, base):
        self.base = os.path.expanduser(base)
        self.ruby = None
        for i, path in enumerate(Installation.ruby_paths):
            if os.path.isfile(os.path.join(base, path)):
                self.ruby = i
                break
        self.server = None
        for i, path in enumerate(Installation.server_paths):
            if os.path.isfile(os.path.join(base, path)):
                self.server = i
                break

    def exists(self):
        return self.server is not None

    def ruby_path(self):
        if self.ruby is None:
            return 'ruby'
        else:
            return os.path.join(self.base, Installation.ruby_paths[self.ruby])

    def server_path(self):
        return os.path.join(self.base, Installation.server_paths[self.server])

CONTEXT_SETTINGS = dict(token_normalize_func=lambda x: x.lower().replace('-', '_'))

@click.group(context_settings=CONTEXT_SETTINGS)
@click.option('--host', default='127.0.0.1', help="IP or hostname of Sonic Pi server")
@click.option('--port', default=4557, help="Port number of Sonic Pi server")
@click.option('--osc-port', default=4559, help="Port number of Sonic Pi OSC cue server")
@click.pass_context
def cli(ctx, host, port, osc_port):
    ctx.obj = Server(host, port, osc_port)

@cli.command(help="Check if Sonic Pi server is running.")
@click.pass_context
def check(ctx):
    if ctx.obj.server_port_in_use():
        print("Sonic Pi server listening on port 4557")
    else:
        print("Sonic Pi server NOT listening on port 4557")
        sys.exit(1)

@cli.command(help="Send code to the server to be played.")
@click.argument('code')
@click.pass_context
def eval(ctx, code):
    ctx.obj.run_code(code)

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
    cmd = 'run_file "{}"'.format(os.path.abspath(path).replace('\\', '\\\\').replace('"', '\\"'))
    ctx.obj.run_code(cmd)

@cli.command(help="Send an OSC cue to a running Sonic Pi script")
@click.argument('path', required=True)
@click.argument('args', nargs=-1)
@click.pass_context
def osc(ctx, path, args):
    ctx.obj.send_osc(path, args)

@cli.command(help="Try to locate Sonic Pi server and start it.")
@click.option('--path', multiple=True, type=click.Path(exists=True),
              help="Path to Sonic Pi app to try before defaults, may be specified multiple times")
def start_server(path):
    default_paths = ('./Sonic Pi.app', # Check current dir first
                     './app',
                     '~/Applications/Sonic Pi.app', # Then home dir
                     '/Applications/Sonic Pi.app', # And finally standard install locations
                     '/opt/sonic-pi/app',
                     '/usr/lib/sonic-pi')
    for p in path + default_paths:
        inst = Installation(p)
        if inst.exists():
            print("Found installation at: {}".format(inst.base))
            print("Running: {} {}".format(inst.ruby_path(), inst.server_path()))
            subprocess.run([inst.ruby_path(), inst.server_path()]).check_returncode()
            break
    else:
        print("I couldn't find the Sonic Pi server executable :(")
        sys.exit(1)

@cli.command(help="Stop all jobs running on the server.")
@click.pass_context
def stop(ctx):
    ctx.obj.stop_all_jobs()

@cli.command(help="Print logs emitted by the Sonic Pi server.")
@click.pass_context
def logs(ctx):
    err = ctx.obj.follow_logs()
    if err == True:
        print("""error: Unable to listen for Sonic Pi server logs, address already in use.
This may because the Sonic Pi GUI is running and already listening on the desired port.
If the GUI is running this command cannot function, try running just the Sonic Pi server.""")
        sys.exit(1)
    elif err:
        print("Unexpected error: {}\n".format(err))
        print("Please report this error at https://github.com/emlyn/sonic-pi-tool/issues")
        sys.exit(1)

@cli.command(help="Record audio output to a local file.")
@click.argument('path')
@click.pass_context
def record(ctx, path):
    ctx.obj.start_recording()
    print("Recording started, saving to {}".format(path))
    input("Press Enter to stop the recording...")
    ctx.obj.stop_and_save_recording(path)

if __name__ == '__main__':
    cli(obj=None)
