"""
Coordinate systems.

We follow the VOTable practice of defining coordinate systems.

"""

from gavo import base


class CooSys(base.Structure):
	name_ = "cooSys"
	_equ = base.UnicodeAttribute("equ", default=base.Undefined,
		description="Equinox (like J2000.0, B1950.0 or similar)")
	_epoch = base.FloatAttribute("epoch", default=None,
		description="Epoch (as a float in julian years)")
	_system = base.UnicodeAttribute("system", default=None,
		description="System for coordinates (like ICRS, eq_FK5)")

