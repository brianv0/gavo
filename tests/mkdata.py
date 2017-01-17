"""
output a python string that's a base64 encoded zlib compressed representation
of arg.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import sys

if __name__=="__main__":
	data = open(sys.argv[1]).read()
	print '"""%s"""'%data.encode("zlib").encode("base64")
