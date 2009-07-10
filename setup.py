import os
import sys

import ez_setup
ez_setup.use_setuptools()

from setuptools import setup, find_packages, Extension

install_requires = ["pyfits", "pyPgSQL", "VOTable", 
	"numarray", "elementtree", "pyparsing", "egenix-mx-base"]
if "develop" in sys.argv:
	# No stinkin' wrapper scripts, please
	install_requires = []

setup(name="gavo",
	description="ZAH GAVO data center complete package",
	url="http://www.g-vo.org",
	license="GPL",
	author="Markus Demleitner",
	author_email="msdemlei@ari.uni-heidelberg.de",
	packages=find_packages(),
	py_modules=["ez_setup"],
	package_data = {
		'gavo': ["resources/*"],
	},
	install_requires=install_requires,
	dependency_links=["http://vo.ari.uni-heidelberg.de/soft/python",
		"http://sourceforge.net/project/showfiles.php?group_id=16528",
		"http://sourceforge.net/project/showfiles.php?group_id=1369",
		"http://www.stsci.edu/resources/software_hardware/pyfits/Download"],
	entry_points={
		'console_scripts': [
			'gavoimp = gavo.commandline:main',
			'gavodrop = gavo.commandline:dropCLI',
			'gavocred = gavo.protocols.creds:main',
			'gavomkrd = gavo.user.mkrd:main',
			'gavopublish = gavo.protocols.servicelist:main',
			'gavomkboost = gavo.grammars.directgrammar:main',
			'gavoconfig = gavo.base.config:main',
			'gavogendoc = gavo.user.docgen:main',
			'gavostc = gavo.stc.cli:main',
		]
	},
	version="0.3")
