#!/usr/bin/env python

""" 
This script takes restructured text input from stdin, looks for
lines starting with .. !! and executes the command given after that.
It then replaces the input line with the output of the command.
"""

import sys
import os

if __name__=="__main__":
	for line in sys.stdin:
		if line.startswith(".. !!"):
			cmd = line[5:].strip()
			sys.stderr.write("Running %s\n"%cmd)
			sys.stdout.flush()
			if os.system(cmd):
				sys.exit("Run of %s failed"%cmd)
		else:
			sys.stdout.write(line)
