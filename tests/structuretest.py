"""
Tests for structures (i.e. instances of structure-decorated classes).
"""

from cStringIO import StringIO
import unittest

from gavo import base 
from gavo.base import structure
from gavo.base import xmlstruct
from gavo.base.attrdef import *

import testhelpers


# Some test struct defs
class Color(structure.ParseableStructure):
	name_ = "color"
	_r = IntAttribute("r", 255, copyable=True)
	_g = IntAttribute("g", 255, copyable=True)
	_b = IntAttribute("b", 255, copyable=True)

class CopyableColor(Color):
	_orig = base.OriginalAttribute(forceType=Color)

class Foo(structure.ParseableStructure):
	name_ = "foo"
	_color = base.StructAttribute("color", childFactory=Color, copyable=True)
	_name = UnicodeAttribute("name", base.Undefined)
	_content = structure.DataContent(copyable=True)

class Foos(structure.ParseableStructure):
	name_ = "foos"
	_content = base.StructListAttribute("plups", Foo)

class Bla(structure.ParseableStructure):
	name_ = "bla"
	_att1 = base.ListOfAtomsAttribute("items",
		itemAttD=IntAttribute("item"), copyable=True)

class PaletteBase(structure.ParseableStructure):
	name_ = "pal"
	_colors = base.StructListAttribute("colors", childFactory=CopyableColor,
		copyable=True)
	_foo = base.StructListAttribute("foos", childFactory=Foo, copyable=True)

class Palette(PaletteBase):
	_ref = structure.RefAttribute(forceType=PaletteBase)

class PalCollection(structure.ParseableStructure):
	name_ = "pals"
	_pals = base.StructListAttribute("pals", childFactory=Palette)
# End of test struct defs


class SimpleStructureTest(unittest.TestCase):
	"""tests for very basic structures.
	"""
	def _getStruct(self):
		class Bla(structure.ParseableStructure):
			_att1 = UnicodeAttribute("att1", "default")
		return Bla

	def testSimpleAttSetting(self):
		class Bla(structure.ParseableStructure):
			_att1 = UnicodeAttribute("att1")
		s1 = Bla(None)
		self.assertEqual(s1.att1, None)
		s1._att1.feed(None, s1, "value")
		self.assertEqual(s1.att1, "value")
	
	def testDefaultAtt(self):
		Bla = self._getStruct()
		s1 = Bla(None)
		self.assertEqual(s1.att1, "default")
	
	def testNoInterference(self):
		Bla = self._getStruct()
		s1, s2 = Bla(None), Bla(None)
		s2._att1.feed(None, s2, "Foo")
		self.assertEqual(s1.att1, "default")
		self.assertEqual(s2.att1, "Foo")

	def testDefault(self):
		Bla = self._getStruct()
		s1 = Bla(None, att1="no default")
		self.assertEqual(s1.att1, "no default")


class AtomListStructureTest(unittest.TestCase):
	"""tests for structures with lists.
	"""
	def testBasic(self):
		s1 = Bla(None)
		self.assertEqual(s1.items, [])
		s1._att1.feed(None, s1, "2")
		self.assertEqual(s1.items, [2])
		s1._att1.feedObject(s1, 1)
		self.assertEqual(s1.items, [2, 1])
	
	def testNoInterference(self):
		s1, s2 = Bla(None), Bla(None)
		s1._att1.feedObject(s1, 3)
		s2._att1.feedObject(s2, 1)
		self.assertEqual(s1.items, [3])
		self.assertEqual(s2.items, [1])
	
	def testRaises(self):
		s1 = Bla(None)
		try:
			s1._att1.feed(None, s1, "x4")
		except LiteralParseError, msg:
			self.assertEqual(msg.attName, "item")
			self.assertEqual(msg.attVal, "x4")
		else:
			self.fail("Bad integer literal doesn't raise correct exc. in list")


class MiscAttributeTest(unittest.TestCase):
	"""tests for various predefined attribute types.
	"""
	def testEnumUnicode(self):
		class En(structure.ParseableStructure):
			_att1 = EnumeratedUnicodeAttribute("att1", "left",
				["left", "right"])
		e = En(None)
		self.assertEqual(e.att1, "left")
		e._att1.feed(None, e, "right")
		self.assertEqual(e.att1, "right")
		self.assertRaises(base.LiteralParseError, e._att1.feed, None, e, "center")
		self.assertEqual(e._att1.typeDesc_, "One of: right, left")


def _feedInto(baseStruct, eventList):
	ep = structure.EventProcessor(baseStruct, base.ParseContext())
	for ev in eventList:
		ep.feed(*ev)
	return ep.result


class AtomicFeedTest(testhelpers.VerboseTest):
	"""tests for feeding into atomic structures.
	"""
	def _getPlainStructure(self):
		class Bla(structure.ParseableStructure):
			name_ = "bla"
			_foo = UnicodeAttribute("foo", "default")
			_bar = IntAttribute("bar", 0)
		return Bla

	def testSomeAtoms(self):
		Bla = self._getPlainStructure()
		s1 = _feedInto(Bla, [
			("start", "bla"),
			("start", "foo"),
			("value", "foo", "no default"),
			("end", "foo"),
			("value", "bar", 3),])
		self.assertEqual(s1.foo, "no default")
		self.assertEqual(s1.bar, 3)

	def testRaising(self):
		Bla = self._getPlainStructure()
		self.assertRaisesWithMsg(structure.StructureError, 
			"Bla objects cannot have xxx children", _feedInto, 
			(Bla, [("start", "bla"), ("start", "xxx")]))


class StructAttTest(unittest.TestCase):
	"""tests for building structures out of event streams.
	"""
	def testMixedParse(self):
		f = _feedInto(Foo, [
			("start", "foo"),
			("start", "color"),
			("value", "r", "10"),
			("start", "g"),
			("value", None, "20"),
			("end", "g"),
			("end", "color"),
			("start", "name"),
			("value", None, "blue"),
			("end", "name"),])
		self.assertEqual(f.color.r, 10)
		self.assertEqual(f.color.g, 20)
		self.assertEqual(f.color.b, 255)
		self.assertEqual(f.name, "blue")


class XMLParseTest(testhelpers.VerboseTest):
	"""tests for building structures out of XML documents.
	"""
	def testSimpleParse(self):
		f = xmlstruct.parseFromStream(Foo, StringIO("""<foo name="red">
			<color g="0" b="0"/></foo>"""))
		self.assertEqual(f.color.r, 255)
		self.assertEqual(f.color.g, 0)
		self.assertEqual(f.color.b, 0)
		self.assertEqual(f.name, "red")

	def testIdSet(self):
		f = xmlstruct.parseFromStream(Foos, StringIO("""<foos>
			<foo name="red" id="x"><color g="0" b="0"/></foo>
			<foo name="blue"><color g="0" r="0" id="y"/></foo></foos>"""))
		self.assertEqual(f.plups[0].id, "x")
		self.assertEqual(f.plups[1].color.id, "y")

	def testWrongRootElement(self):
		self.assertRaisesWithMsg(structure.StructureError, 
			"At <internal source>, unknown position: "
			"Expected root element color, found foo",
			xmlstruct.parseFromStream, (Color, StringIO("""<foo name="red">
			<color g="0" b="0"/></foo>""")))

	def testBadChild(self):
		self.assertRaisesWithMsg(structure.StructureError,
			"At <internal source>, unknown position: "
				"color elements have no noAtt attributes",
			xmlstruct.parseFromString, (Color, '<color noAtt="30"/>'))
		self.assertRaisesWithMsg(structure.StructureError,
			"At <internal source>, unknown position: "
				"Color objects cannot have noAtt children",
			xmlstruct.parseFromString, (Color, '<color><noAtt>30</noAtt></color>'))

	def testAtomListParse(self):
		f = xmlstruct.parseFromStream(Bla, StringIO('<bla item="0"><item>1</item>'
			'<item>2</item></bla>'))
		self.assertEqual(f.items, [0, 1, 2])

	def testStructContent(self):
		f = xmlstruct.parseFromString(Foo, '<foo name="xy">Some content</foo>')
		self.assertEqual(f.content_, "Some content")
		self.assertRaisesWithMsg(structure.StructureError,
			"At <internal source>, last known position: 1, 19: "
			"color elements must not have character data content "
				"(found 'Some content')",
			xmlstruct.parseFromString, (Color, '<color>Some content</color>'))


class CopyTest(testhelpers.VerboseTest):
	"""tests for copying structures.
	"""
	def testCopyStruct(self):
		f = xmlstruct.parseFromStream(Foo, StringIO("""<foo name="red">
			<color g="0" b="0"/></foo>"""))
		f2 = f.copy(None)
		f.color.g = 27
		self.assertEqual(f2.color.g, 0)
	
	def testCopyAtomList(self):
		f = xmlstruct.parseFromStream(Bla, StringIO('<bla item="0"><item>1</item>'
			'<item>2</item></bla>'))
		f2 = f.copy(None)
		f2.items.append(3)
		self.assertEqual(f.items, [0, 1, 2])
		self.assertEqual(f2.items, [0, 1, 2, 3])

	def testCopyStructList(self):
		f = xmlstruct.parseFromStream(Palette, StringIO('<pal><color/>'
			'<color g="0"/></pal>'))
		f2 = f.copy(None)
		f2.colors.append(Color(f2, r=0))
		self.assertEqual(len(f.colors), 2)
		self.assertEqual(len(f2.colors), 3)
	
	def testOriginal(self):
		f = xmlstruct.parseFromStream(Palette, StringIO('<pal><color id="x">'
			'<r>7</r></color><color g="0" original="x"/></pal>'))
		self.assertEqual(f.colors[0].g, 255)
		self.assertEqual(f.colors[1].g, 0) 
		f.colors[1].r = 8
		self.assertEqual(f.colors[1].r, 8) 
		self.assertEqual(f.colors[0].r, 7) 

	def testTypecheck(self):
		self.assertRaisesWithMsg(base.StructureError, 
			"At <internal source>, last known position: 1, 19: "
			"Reference to 'xy' yielded object of type Foo, expected Color", 
			xmlstruct.parseFromString, (Palette, '<pal><foo id="xy"/>'
			'<color original="xy"/></pal>'))

	def testElementRefusal(self):
		self.assertRaisesWithMsg(base.StructureError, 
			"At <internal source>, last known position: 1, 19:"
			" original is only allowed as an attribute",
			xmlstruct.parseFromString, (Palette, '<pal><foo id="xy"/>'
			'<foo><original>xy</original></foo></pal>'))

	def testBadId(self):
		self.assertRaisesWithMsg(base.StructureError, 
			"At <internal source>, unknown position:"
			" Reference to unknown item 'xy'.  Note that elements"
				" referenced must occur lexically before the referring element",
			xmlstruct.parseFromString, (Palette, '<pal><color original="xy"/>'
			'</pal>'))


class RefTest(testhelpers.VerboseTest):
	"""tests for ref in structures.
	"""
	def testListRef(self):
		f = xmlstruct.parseFromString(PalCollection, 
			'<pals><pal id="pal1"><color r="0"/><color g="0"/></pal>'
			'<pal ref="pal1"/></pals>')
		self.assert_(f.pals[0].colors[0] is f.pals[1].colors[0])

	def testChangeRefusal(self):
		self.assertRaisesWithMsg(base.StructureError,
			"At <internal source>, last known position: 1, 21: "
			"Referenced elements cannot have attributes or children",
			xmlstruct.parseFromString, (PalCollection, 
				'<pals><pal id="foo"/><pal ref="foo"><color/></pal></pals>'))

	def testTypecheck(self):
		self.assertRaisesWithMsg(base.StructureError,
			"At <internal source>, last known position: 1, 49: "
				"Reference to 'pal1' yielded object of type CopyableColor,"
				" expected PaletteBase",
			xmlstruct.parseFromString, (PalCollection, 
				'<pals><pal><color r="0" id="pal1"/><color g="0"/></pal>'
				'<pal ref="pal1"/></pals>'))


class FeedFromTest(testhelpers.VerboseTest):
	"""tests for working of feedFrom hackery.
	"""
	def testBasic(self):
		f = xmlstruct.parseFromString(PaletteBase, 
			'<pal id="pal1"><foo><color r="0"/>content</foo></pal>')
		f2 = xmlstruct.parseFromString(PaletteBase, 
			'<pal id="pal2"/>')
		f2.feedFrom(f)
		self.assertEqual(f2.foos[0].content_, "content",
			"Copyable attribute was not copied")
		self.assertEqual(f2.id, "pal2", "Non-copyable attribute was copied")


class BeforeTest(testhelpers.VerboseTest):
	"""tests for sorting of children.
	"""
	def testWorkingSort(self):
		class Foo(base.Structure):
			_att1 = base.UnicodeAttribute("b", before="a")
			_att2 = base.UnicodeAttribute("a")
		self.assertEqual([a.name_ for a in Foo.attrSeq], ["b", "a", "id"])
	
	def testBailOnCycle(self):
		def defineBadStruct():
			class Foo(base.Structure):
				_att1 = base.UnicodeAttribute("b", before="a")
				_att2 = base.UnicodeAttribute("a", before="c")
				_att3 = base.UnicodeAttribute("c", before="b")
		self.assertRaises(ValueError, defineBadStruct)



if __name__=="__main__":
	testhelpers.main(BeforeTest)
