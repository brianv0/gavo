"""
"User-interface"-type code.
"""

from gavo.user import useless
from gavo.user import plainui

interfaces = {
	"deluge": useless.DelugeUI,
	"null": useless.NullUI,
	"stingy": plainui.StingyPlainUI,
	"plain": plainui.PlainUI,
}
