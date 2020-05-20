Sonic Pi Tool (Python)
=============

`sonic-pi-tool.py` is a rewrite of the Rust [sonic-pi-tool](https://github.com/lpil/sonic-pi-tool) in Python.
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
pip install oscpy click

# Download script:
curl -O https://raw.githubusercontent.com/emlyn/sonic-pi-tool/master/sonic-pi-tool.py

# Make it executable:
chmod +x sonic-pi-tool.py

# Copy it somewhere on the PATH:
sudo cp sonic-pi-tool.py /usr/local/bin/
```

`sonic-pi-tool.py` should be compatible with both Python 2.7+ and Python 3.6+,
but it hasn't been tested extensively, so if you have trouble running it please file an issue.


## Usage

- [check](#check)
- [eval](#eval)
- [eval-file](#eval-file)
- [eval-stdin](#eval-stdin)
- [run-file](#run-file)
- [osc](#osc)
- [stop](#stop)
- [logs](#logs)
- [start-server](#start-server)
- [record](#record)


### `check`

Used to check if the Sonic Pi server is running. If the server isn't running
many of the tool's commands (such as `eval`) will not work.

This command returns an exit code of zero if the server is running,
one if it is not running, or two if it cannot determine whether it is running.

```sh
sonic-pi-tool.py check
# Sonic Pi is running, and listening on port 4557 for commands and 4560 for OSC
```


### `eval`

Take a string of Sonic Pi code and send it to the Sonic Pi server to be
played.

```sh
sonic-pi-tool.py eval "play :C4"
# *ding*
```


### `eval-file`

Read Sonic Pi code from a file and send it to the Sonic Pi server to be
played. If the file is too big, consider using `run-file` instead.

```sh
sonic-pi-tool.py eval-file path/to/code.rb
# *music*
```


### `eval-stdin`

Read Sonic Pi code from standard in and send it to the Sonic Pi server to be
played.

```sh
echo "play :C4" | sonic-pi-tool.py eval-stdin
# *ding*
```


### `run-file`

Send a command to the Sonic Pi server to load and play the specified file.
This avoids problems with files being too long since the entire content no longer
needs to fit in a single OSC message.

```sh
sonic-pi-tool.py run-file path/to/code.rb
# *music*
```


### `osc`

Send an OSC cue to Sonic Pi.
Allows a running Sonic Pi script to receive data from or synchronise to an external system.

``` sh
sonic-pi-tool.py osc /trigger/foo 123
# Triggers `sync "/osc*/trigger/foo"` command running in Sonic Pi
```


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
Searches a few standard locations, first in the current directory,
then the users home directory
and finally some standard install locations.

If it is unable to find your installation, you can pass the location in the `--path` option.
Please also consider raising an issue including the path to your install,
and I will add it to the list of search paths.

Not currently supported on Windows.

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
