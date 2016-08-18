import os
import sys

#import ez_setup
#ez_setup.use_setuptools()

from setuptools import setup, find_packages, Extension

VERSION = "0.9.7"


install_requires = []
# Theoretically, we could define dependencies here, more or less like this:
# install_requires = ["pyfits", "numpy", "psycopg2"]
# -- but we don't, since in practice it seems it's more trouble than it's
# worth.

SETUP_ARGS = {
	"name": "gavodachs",
	"description": "ZAH GAVO data center complete package",
	"url": "http://vo.ari.uni-heidelberg.de/soft",
	"license": "GPL",
	"author": "Markus Demleitner",
	"author_email": "gavo@ari.uni-heidelberg.de",
	"packages": find_packages(),
	# We're not zip-safe because the XSD validator accesses dist files by path
	"zip_safe": False,
	"include_package_data":  True,
	"install_requires": install_requires,
	"entry_points": {
		'console_scripts': [
			'gavo = gavo.user.cli:main',
		]
	},
	"version": VERSION,
}

if __name__=="__main__":
	setup(**SETUP_ARGS)
