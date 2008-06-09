"""
output a python string that's a base64 encoded zlib compressed representation
of arg.
"""

import sys

if __name__=="__main__":
	data = open(sys.argv[1]).read()
	print '"""%s"""'%data.encode("zlib").encode("base64")
