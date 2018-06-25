Sonic Pi Tool (Python)
=============

`sonic-pi-tool.py` is a port of [sonic-pi-tool](https://github.com/lpil/sonic-pi-tool) to Python.
It is a handy command line utility for playing with the Sonic Pi
server. It can be used instead of the Sonic Pi GUI for all your music making
needs :)

It's ideal for use with [sonicpi.vim](https://github.com/dermusikman/sonicpi.vim)


## Installation

Sonic Pi Tool doesn't currently have a proper installer.
However it is just a simple Python script with a couple of dependencies,
so it's not hard to install manually:

```sh
# Install dependencies:
pip3 install python-osc click

# Download script:
curl -O https://raw.githubusercontent.com/emlyn/sonic-pi-tool/master/sonic-pi-tool.py

# Make it executable:
chmod +x sonic-pi-tool.py

# Copy it somewhere on the PATH:
sudo cp sonic-pi-tool.py /usr/local/bin/
```

`sonic-pi-tool.py` does not currently support Python 2.


## Usage

- [check](#check)
- [eval](#eval)
- [eval-file](#eval-file)
- [eval-stdin](#eval-stdin)
- [stop](#stop)
- [logs](#logs)
- [start-server](#start-server)
- [record](#record)

### `check`

```sh
sonic-pi-tool.py check
# => Sonic Pi server listening on port 4557
```

Used to check if the Sonic Pi server is running. If the server isn't running
many of the tool's commands (such as `eval`) will not work.

This command returns a non-zero exit code if the server is not running.


### `eval`

```sh
sonic-pi-tool.py eval "play :C4"
# *ding*
```

Take a string Sonic Pi code and send it to the Sonic Pi server to be
played.


### `eval-file`

```sh
sonic-pi-tool.py eval-file path/to/code.rb
# *music*
```

Read Sonic Pi code from a file and send it to the Sonic Pi server to be
played.


### `eval-stdin`

```sh
echo "play :C4" | sonic-pi-tool.py eval-stdin
# *ding*
```

Read Sonic Pi code from standard in and send it to the Sonic Pi server to be
played.


### `stop`

Stop all jobs running on the Sonic Pi server, stopping the music.

```sh
sonic-pi-tool.py stop
# *silence*
```


### `logs`

Prints out log messages emitted by the Sonic Pi server.

This command won't succeed if the Sonic Pi GUI is running as it will be
consuming the logs already.

```sh
sonic-pi-tool.py logs
#
# [Run 2, Time 32.7]
#  └ synth :beep, {note: 65.0, release: 0.1, amp: 0.9741}
#
# [Run 2, Time 32.8]
#  └ synth :beep, {note: 39.0, release: 0.1, amp: 0.9727}
```


### `start-server`

Attempts start the Sonic Pi server, if the executable can be found.

Not supported on Windows.

```sh
sonic-pi-tool.py start-server
# Sonic Pi server booting...
# Using protocol: udp
# Detecting port numbers...
# ...
```

### `record`

Record the audio output of a Sonic Pi session to a local file.
Stop and save the recording when the Enter key is pressed.

```sh
sonic-pi-tool.py record /tmp/output.wav
# Recording started, saving to /tmp/output.wav.
# Press Enter to stop the recording...
```

## MPL 2.0 Licence
