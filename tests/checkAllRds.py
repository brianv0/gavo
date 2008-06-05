"""
Import all localizable RDs to make sure they still parse.

Since walking the inputs dir may be time consuming, I cache the found
rds in a hare-brained scheme by writing them into the program source.

Call the program with an argument to make it refresh that cache.
"""

import re
import sys

from gavo import config
from gavo.parsing import importparser
from gavo.web import servicelist

cachedIDs = ['liverpool/res/rawframes', 'lensdemo/view', '2mass/res/2mass', 'apfs/res/apfs_new', 'dexter/ui', 'ucds/ui', 'ppmx/res/ppmxautopm', 'ppmx/res/ppmxauto', 'ppmx/res/ppmx', 'usnob/res/redux', 'usnob/res/usnob', 'poslenscands/res/cands', 'brownDwarfs/bd', 'fk6/res/fk6', 'rauchspectra/theospectra', 'cns/res/cns', 'inflight/res/lc1', 'apo/res/apo', 'genupload/do', 'maidanak/res/rawframes', 'lswscans/res/positions', '__system__/cutout/cutout', '__system__/products/products', '__system__/services/services', '__system__/tests/misc', '__system__/users/users']

def patchMySource(newIDs):
	f = open("checkAllRds.py")
	src = f.read()
	f.close()
	src = re.sub(r"\ncachedIDs = \[.*", r"\ncachedIDs = %s"%repr(newIDs),
		src)
	f = open("checkAllRds.py", "w")
	f.write(src)
	f.close()

builtinIDs = ["__system__/cutout/cutout", "__system__/products/products",
	"__system__/services/services", "__system__/tests/misc",
	"__system__/users/users"]

config.setDbProfile("querulator")
if len(sys.argv)>1:
	newIDs = []
	for rdPath in servicelist.findAllRDs():
		newIDs.append(importparser.getRd(rdPath).sourceId)
	patchMySource(newIDs+builtinIDs)
else:
	for id in cachedIDs:
		importparser.getRd(id)
		print "-- %s ok"%id
