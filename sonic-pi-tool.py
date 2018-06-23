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

class Server:
    def __init__(self, host, port):
        # fix for https://github.com/repl-electric/sonic-pi.el/issues/19#issuecomment-345222832
        self.prefix = b'@osc_server ||= SonicPi::OSC::UDPServer.new(4559, use_decoder_cache: true) #__nosave__\n'
        self.client_name = b'SONIC_PI_TOOL_PY'
        self.host = host
        self.port = port
        self.client = OSCClient(host, port)

    def send(self, msg, *args):
        self.client.send_message(msg, (self.client_name,) + args)

    def server_port_in_use(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            try:
                sock.bind(('127.0.0.1', self.port))
            except OSError:
                return True
        return False

    def stop_all_jobs(self):
        self.send(b'/stop-all-jobs')

    def run_code(self, code):
        self.send(b'/run-code', self.prefix + code.encode('utf8'))

    def start_recording(self):
        self.send(b'/start-recording')

    def stop_and_save_recording(self, path):
        self.send(b'/stop-recording')
        self.send(b'/save-recording', path.encode('utf8'))

    @staticmethod
    def handle_log_info(style, msg):
        print("=> {}\n".format(msg.decode('utf8')))

    @staticmethod
    def handle_multi_message(run, thread, time, n, *msgs):
        print("{{run: {}, time: {}}}".format(run, time))
        for i in range(n):
            typ, msg = msgs[2*i: 2*i+2]
            print(" {}─ {}".format("├" if i < n - 1 else "└", msg.decode('utf8')))
        print()

    @staticmethod
    def handle_error(run, msg, trace, line):
        print("Runtime Error: {}\n{}\n".format(html.unescape(msg.decode('utf8')),
                                               html.unescape(trace.decode('utf8'))))

    @staticmethod
    def handle_syntax_error(run, msg, code, line, line_s):
        if line >= 0:
            print("Error: {}\n[Line {}]: {}".format(html.unescape(msg.decode('utf8')),
                                                    line, code))
        else:
            print("Error: {}\n{}".format(html.unescape(msg), code))

    def follow_logs(self):
        try:
            server = OSCThreadServer()
            sock = server.listen(address='127.0.0.1', port=4558, default=True)
            server.bind(b'/log/multi_message', self.handle_multi_message)
            server.bind(b'/multi_message', self.handle_multi_message)
            server.bind(b'/log/info', self.handle_log_info)
            server.bind(b'/info', self.handle_log_info)
            server.bind(b'/error', self.handle_error)
            server.bind(b'/syntax_error', self.handle_syntax_error)
            while True:
                time.sleep(1)
        except Exception as e:
            return e

class Installation:
    ruby_paths = ['server/native/ruby/bin/ruby']
    server_paths = ['server/ruby/bin/sonic-pi-server.rb',
                    'server/bin/sonic-pi-server.rb']
    def __init__(self, base):
        self.base = base
        for i, path in enumerate(Installation.ruby_paths):
            if os.path.isfile('{}/{}'.format(base, path)):
                self.ruby = i
                break
        else:
            self.ruby = None
        for i, path in enumerate(Installation.server_paths):
            if os.path.isfile('{}/{}'.format(base, path)):
                self.server = i
                break
        else:
            self.server = None

    def exists(self):
        return self.server is not None

    def ruby_path(self):
        if self.ruby is None:
            return 'ruby'
        else:
            return '{}/{}'.format(self.base, Installation.ruby_paths[self.ruby])

    def server_path(self):
        return '{}/{}'.format(self.base, Installation.server_paths[self.server])

CONTEXT_SETTINGS = dict(token_normalize_func=lambda x: x.lower().replace('-', '_'))

@click.group(context_settings=CONTEXT_SETTINGS)
@click.option('--host', default='127.0.0.1')
@click.option('--port', default=4557)
@click.pass_context
def cli(ctx, host, port):
    ctx.obj = Server(host, port)

@cli.command(help="Check if Sonic Pi server is running.")
@click.pass_context
def check(ctx):
    if ctx.obj.server_port_in_use():
        print("Sonic Pi server listening on port 4557")
    else:
        print("Sonic Pi server NOT listening on port 4557")
        sys.exit(1)

@cli.command(help="Send Sonic Pi code to the server to be played.")
@click.argument('code')
@click.pass_context
def eval(ctx, code):
    ctx.obj.run_code(code)

@cli.command(help="Read Sonic Pi code from stdin and send it to the server to be played.")
@click.pass_context
def eval_stdin(ctx):
    ctx.obj.run_code(sys.stdin.read())

@cli.command(help="Read Sonic Pi code from a file and send it to the server to be played.")
@click.argument('path', type=click.File('r'))
@click.pass_context
def eval_file(ctx, path):
    ctx.obj.run_code(path.read())

@cli.command(help="Send path to the server for it to read and play file (for big files).")
@click.argument('path', type=click.Path(exists=True))
@click.pass_context
def run_file(ctx, path):
    cmd = 'run_file "{}"'.format(os.path.abspath(path).replace('\\', '\\\\').replace('"', '\\"'))
    ctx.obj.run_code(cmd)

@cli.command(help="Try to locate the Sonic Pi server executable and start it.")
def start_server():
    paths = [Installation('/Applications/Sonic Pi.app'),
             Installation('./app'),
             Installation('/opt/sonic-pi/app'),
             Installation('/usr/lib/sonic-pi')]
    try:
        paths.insert(0, Installation('{}/{}'.format(os.environ['HOME'], 'Applications/Sonic Pi.app')))
    except KeyError:
        pass
    for inst in paths:
        if inst.exists():
            print("Found installation at: {}".format(inst.base))
            print("Running: {} {}".format(inst.ruby_path(), inst.server_path()))
            subprocess.run([inst.ruby_path(), inst.server_path()]).check_returncode()
            break
    else:
        print("I couldn't find the Sonic Pi server executable :(")
        sys.exit(1)

@cli.command(help="Stop all jobs (and therefore music) running on the Sonic Pi server.")
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

@cli.command(help="Record the audio output of Sonic Pi to a local file.")
@click.argument('path')
@click.pass_context
def record(ctx, path):
    ctx.obj.start_recording()
    print("Recording started, saving to {}".format(path))
    input("Press Enter to stop the recording...")
    ctx.obj.stop_and_save_recording(path)

if __name__ == '__main__':
    cli(obj=None)
