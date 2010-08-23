"""
A collective setup.py for the subpackages.

The scheme here is extremely tacky, but other schemes seem hard given that
distutils and friends apparently really don't like setup.pys below the
distribution root and I want to keep a global setup.py, and also the rule
that everything under version control gets added by default is a pain here.

So, this machinery builds on subdirectories with subpackage-specific data
(probably mostly a README plus possibly a MANIFEST.in).  This gets copied
to a subdirectory of pkgdir.  A setup.py gets generated from a module-internal
definition that also includes an iterator giving files and directories
to copy from the main tree.  Everything mentioned is included into
MANIFEST.in just to be on the safe side.

Finally, the newly created setup.py is called with the arguments given to 
subsetup.

This script has to be run from its location.

It's a mess, yes.
"""

#c Copyright 2009 the GAVO Project.
#c
#c This program is free software, covered by the GNU GPL.  See COPYING.


from __future__ import with_statement

import itertools
import glob
import os
import sys
import shutil
import subprocess

PKGDIR = "pkgdir"
GAVO_VERSION = "0.5"

setupHead = """# setup.py for GAVO DC subpackage.
# Automatically generated by subpkgs/subsetup.py in the DC main source
# tree.  Edit that file rather than this.

import os
import sys

from setuptools import setup, Extension

setup("""

setupFoot = """)"""


baseKeys = {
	"url": "http://vo.ari.uni-heidelberg.de/soft",
	"license": "GPL",
	"author": "Markus Demleitner",
	"author_email": "gavo@ari.uni-heidelberg.de",
	"version": GAVO_VERSION,
	"url": "http://vo.ari.uni-heidelberg.de/soft",
	"namespace_packages": ["gavo"],
}

baseFiles = ["gavo/__init__.py"]

subpkgs = {
	"utils": {
		"name":"gavoutils",
		"description": "DaCHS basic helper modules.",
		"packages": ["gavo", "gavo.utils"],
		"install_requires": ["pyfits", "numpy"],
		"dependency_links": ["http://vo.ari.uni-heidelberg.de/soft/dist",
			"http://www.stsci.edu/resources/software_hardware/pyfits/Download"],
		"MAINTREEFILES": ["gavo/utils", "gavo/__init__.py"],
	},

	"stc": {
		"name": "gavostc",
		"description": "A library for processing IVOA STC information",
		"packages": ["gavo", "gavo.stc"],
		"install_requires": ["gavoutils"],
		"dependency_links": ["http://vo.ari.uni-heidelberg.de/soft/dist"],
		"MAINTREEFILES": [
			"tests/"+n for n in os.listdir("../tests") if n.startswith("stc")]
			+["tests/testhelpers.py", "docs/stc.rstx", "gavo/stc",
			"docs/stcsgrammar.txt"]
	},

	"votable": {
		"name": "gavovot",
		"description": "A library to read and write VOTables, plus a TAP client",
		"packages": ["gavo", "gavo.votable"],
		"install_requires": ["gavoutils"],
		"dependency_links": ["http://vo.ari.uni-heidelberg.de/soft/dist"],
		"MAINTREEFILES": ["gavo/votable", "docs/votable.rstx", 
			"docs/tapquery.rstx"],
	},
}


def preparePackageDir(pkgName):
	"""recreates the package directory with files in the pkgName subdirectory.

	This is to make sure no cruft from previous runs is left; if pkgName does
	not exist, an empty package directory is created.
	"""
	if not os.path.exists(PKGDIR):
		os.makedirs(PKGDIR)
	destPath = os.path.join(PKGDIR, pkgName)
	if os.path.exists(destPath):
		shutil.rmtree(destPath)
	if os.path.exists(pkgName):
		shutil.copytree(pkgName, destPath)
	else:
		os.makedirs(destPath)
	return destPath


def makeSetup(destDir, **packageKeys):
	fullDesc = baseKeys.copy()
	fullDesc.update(packageKeys)
	with open(os.path.join(destDir, "setup.py"), "w") as output:
		output.write(setupHead)
		for key, value in fullDesc.iteritems():
			output.write("%s=%s,\n"%(key, repr(value)))
		output.write(setupFoot)


def copytree(src, dst):
	"""shutil.copytree with a different contract.

	yadda.
	"""
	if not os.path.exists(dst):
		os.makedirs(dst)
	for name in os.listdir(src):
		if os.path.basename(name).startswith("."):
			continue
		srcname = os.path.join(src, name)
		dstname = os.path.join(dst, name)
		if os.path.isdir(srcname):
			copytree(srcname, dstname)
		else:
			shutil.copy2(srcname, dstname)
	shutil.copystat(src, dst)


def copyFile(src, dest):
	"""copies src to dest.

	Both may contain path parts.  If dest's directory does not exist,
	it will be created.
	"""
	destDir = os.path.dirname(dest)
	if not os.path.exists(destDir):
		os.makedirs(destDir)
	shutil.copy2(src, dest)


def copyPattern(src, destRoot):
	"""copies all files matching the glob-pattern src to destRoot.
	"""
	for name in glob.glob(src):
		copyFile(name,
			os.path.join(destRoot, 
				os.path.join(*name.split('/')[1:])))


def copyGlobalFiles(destDir):
	"""copies files global to all subpackages to destDir.
	"""
	for localName, destName in [
			('INSTALL.generic', 'INSTALL'),
			('../COPYING', 'COPYING')]:
		copyFile(localName, os.path.join(destDir, destName))
		yield "include "+destName


def copyTreeFiles(destDir, treeFiles):
	"""copies the shell-patterns and directories mentioned in the sequence 
	treeFiles to destDir.

	treeFiles are relative to the source tree root.  You cannot specify
	directories in your shell patterns.

	The function returns MANIFEST.in statements for all items copied.
	"""
	manifestItems = ["include ez_setup.py"]
	for path in itertools.chain(baseFiles, treeFiles):
		src = os.path.join("..", path)
		if os.path.isdir(src):
			copytree(src, os.path.join(destDir, path))
			manifestItems.append("recursive-include %s *"%path)
		else:
			copyPattern(src, destDir)
			manifestItems.append("include "+path)
	manifestItems.extend(copyGlobalFiles(destDir))
	return manifestItems


def amendManifest(destDir, items):
	"""adds items to destDir/MANFEST.in.
	"""
	f = open(os.path.join(destDir, "MANIFEST.in"), "a")
	f.write("\n".join(items)+"\n")
	f.close()


def usage():
	return """Usage: %s <subpackage name> <setup.py arguments>

Creates and runs a setup.py for a gavo subpackage.
Known subpackage names include:
%s

The pseudo-subpackage ALL causes all known subpackages to be built.
"""%(sys.argv[0], ", ".join(subpkgs))


def parseCmdLine():
	if len(sys.argv)<3:
		sys.exit(usage())
	subName, setupArgs = sys.argv[1], sys.argv[2:]
	if subName=="ALL":
		return subpkgs.keys(), setupArgs
	elif subName not in subpkgs:
		sys.exit(usage())
	else:
		return [subName], setupArgs


def procOne(subName, setupArgs):
	pkgDir = preparePackageDir(subName)
	packageDef = subpkgs[subName]
	amendManifest(pkgDir,
		copyTreeFiles(pkgDir, packageDef.pop("MAINTREEFILES", [])))
	makeSetup(pkgDir, **packageDef)
	oDir = os.getcwd()
	os.chdir(pkgDir)
	subprocess.call(["python", "setup.py"]+setupArgs)
	os.chdir(oDir)


def main():
	subNames, setupArgs = parseCmdLine()
	for subName in subNames:
		procOne(subName, setupArgs)


if __name__=="__main__":
	main()
