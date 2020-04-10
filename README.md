# My Dotfiles

Configuration files specific to my Arch Linux installation.

## Getting Started

To get started, you'll need to get a copy of this repository:

```console
$ git clone git@github.com:Michael-F-Bryan/dotfiles.git
```

The `install.py` script at the root of this repository will set up an entire
system from scratch. It is designed to be idempotent, so you can run the script
again and again and it won't unnecessarily reinstall things.

You can use the `--help` flag to see help info.

```console
$ ./install.py --help
usage: install.py [-h] [-n DRY_RUN] [-c CONFIG] [-v]

A script for setting up a Linux system just the way you want it.

optional arguments:
  -h, --help            show this help message and exit
  -n DRY_RUN, --dry-run DRY_RUN
                        Show all the commands which would be executed, but don't actually do anything.
  -c CONFIG, --config CONFIG
                        The configuration file to read from (default: config.json)
  -v, --verbose         Generate detailed output, repeat for increased verbosity
```

The installation process is driven using the contents of
[`config.json`](./config.json).

## License

This project is licensed under either of

 * Apache License, Version 2.0, ([LICENSE-APACHE](LICENSE-APACHE.md) or
   http://www.apache.org/licenses/LICENSE-2.0)
 * MIT license ([LICENSE-MIT](LICENSE-MIT.md) or
   http://opensource.org/licenses/MIT)

at your option.

### Contribution

Unless you explicitly state otherwise, any contribution intentionally
submitted for inclusion in the work by you, as defined in the Apache-2.0
license, shall be dual licensed as above, without any additional terms or
conditions.
