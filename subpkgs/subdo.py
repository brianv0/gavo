# Let's see if we can do some automation here.

import os
import subprocess
import sys

import subsetup


remoteHost = "alnilam.ari.uni-heidelberg.de"
remotePath = "/var/www/soft/dist"

class Error(Exception):
	pass


def copyPkg(opts, subkey, subdef):
	name = subdef["name"]
	distName =  "%s-%s.tar.gz"%(name, subsetup.baseKeys["version"])
	linkName = "%s-latest.tar.gz"%(name)
	srcPath = os.path.join("pkgdir", subkey, "dist", distName)
	if not os.path.exists(srcPath):
		raise Error("No dist archive %s, try subsetup.py"%srcPath)
	subprocess.check_call(["scp", srcPath, "%s:%s"%(remoteHost, remotePath)])
	subprocess.check_call(["ssh", remoteHost, 
		"rm -f %s/%s; ln -s %s/%s %s/%s"%(
			remotePath, linkName, remotePath, distName, remotePath, linkName)])


def parseCmdLine():
	actions = {
		"upload": copyPkg,
	}
	from optparse import OptionParser
	parser = OptionParser(usage="%%prog [options] %s"%"|".join(actions))
	parser.add_option("-r", "--restrict", help="Only operate on the comma-"
		"separated list of subpackges", action="store", dest="restrictTo")
	opts, args = parser.parse_args()
	if len(args)!=1 or args[0] not in actions:
		parser.print_help()
		sys.exit(1)
	return actions[args[0]], opts


def main():
	action, opts = parseCmdLine()
	if opts.restrictTo:
		toProcess = [(name, subsetup.subpkgs[name])
			for name in opts.restrictTo.split(",")]
	else:
		toProcess = subsetup.subpkgs.iteritems()
	for pkg in toProcess:
		action(opts, *pkg)

if __name__=="__main__":
	main()
