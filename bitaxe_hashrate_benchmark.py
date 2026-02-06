#!/usr/bin/env python3
"""
Bitaxe Hashrate Benchmark Tool v2.0

This script allows you to benchmark your Bitaxe miner across various
voltage and frequency settings, or apply specific settings directly.

For web UI, run: python bitaxe_hashrate_benchmark.py serve
For CLI benchmark: python bitaxe_hashrate_benchmark.py 192.168.1.136 -v 1150 -f 500

See --help for all options.
"""

import sys

# Backwards compatibility wrapper
# The actual implementation is now in src/cli/main.py
# This file provides the same CLI interface as the original script

if __name__ == "__main__":
    # Check if this is the old-style invocation (IP as first positional arg)
    # or new-style (subcommand like 'serve' or 'benchmark')

    args = sys.argv[1:]

    # If no args or --help, let typer handle it
    if not args or args[0] in ("--help", "-h"):
        from src.cli.main import app
        app()
    # If first arg looks like an IP address (contains dots, no dashes at start)
    elif args[0] and not args[0].startswith("-") and "." in args[0]:
        # Old-style: IP address as first argument
        # Insert 'benchmark' command for backwards compatibility
        sys.argv.insert(1, "benchmark")
        from src.cli.main import app
        app()
    else:
        # New-style with subcommand (serve, benchmark, etc.)
        from src.cli.main import app
        app()
