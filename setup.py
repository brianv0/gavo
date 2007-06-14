from setuptools import setup, find_packages

setup(name="gavo",
	description="ZAH Gavo support modules",
	url="http://www.g-vo.org",
	author="Markus Demleitner",
	author_email="msdemlei@ari.uni-heidelberg.de",
	packages=["gavo", "gavo/parsing", "gavo/web", "gavo/web/querulator"],
	entry_points={
		'console_scripts': [
			'gavoimp = gavo.parsing.commandline:main',
		]
	},
	version="0.2")
