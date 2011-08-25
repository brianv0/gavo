"""
Tests for function definitions and applications.
"""

from gavo.helpers import testhelpers

from gavo import base
from gavo.base import macros
from gavo.rscdef import procdef



class TestApp(procdef.ProcApp):
	name_ = "testApp"
	requiredType = "t_t"
	formalArgs = "source, dest"


class Foo(base.Structure, macros.MacroPackage):
	name_ = "foo"
	_apps = base.StructListAttribute("apps", childFactory=TestApp)
	_defs = base.StructListAttribute("defs", childFactory=procdef.ProcDef)

	def __init__(self, parent, **kwargs):
		base.Structure.__init__(self, parent, **kwargs)
		self.source, self.dest = {}, {}

	def onElementComplete(self):
		self._cApps = [a.compile() for a in self.apps]
		self._onElementCompleteNext(Foo)

	def runApps(self):
		for a in self._cApps:
			a(self.source, self.dest)

	def macro_foobar(self):
		return "Foobar"
	def macro_mesmerize(self, arg):
		return "".join(reversed(list(arg)))


class NoDefTest(testhelpers.VerboseTest):
	"""tests for ProcApps without procDefs.
	"""
	def testVerySimple(self):
		f = base.parseFromString(Foo, "<foo><testApp name='x'/></foo>")
		f.runApps()
		self.assertEqual(f.dest, {})
	
	def testDoesSomething(self):
		f = base.parseFromString(Foo, "<foo><testApp name='x'><code>"
			"\t\tdest['fobba'] = source</code></testApp></foo>")
		f.runApps()
		self.assertEqual(f.dest, {"fobba": {}})
	
	def testMultiline(self):
		f = base.parseFromString(Foo, "<foo><testApp name='x'><code>\n"
			"\t\tfor i in range(source['count']):\n"
			"\t\t\tdest[i] = 42-i</code></testApp></foo>")
		f.source["count"] = 2
		f.runApps()
		self.assertEqual(f.dest, {0: 42, 1: 41})
	
	def testWithParSetup(self):
		f = base.parseFromString(Foo, "<foo><testApp name='x'><code>\n"
			"\t\tfor i in range(count):\n"
			"\t\t\tdest[i] = 42-i</code>\n"
			"<setup><par key='count'>2</par></setup>"
			"</testApp></foo>")
		f.runApps()
		self.assertEqual(f.dest, {0: 42, 1: 41})

	def testWithParAndBinding(self):
		f = base.parseFromString(Foo, "<foo><testApp name='x'><code>\n"
			"\t\tfor i in range(count):\n"
			"\t\t\tdest[i] = 42-i</code>\n"
			"<setup><par key='count'/></setup><bind key='count'>2</bind>"
			"</testApp></foo>")
		f.runApps()
		self.assertEqual(f.dest, {0: 42, 1: 41})

	def testUnboundFails(self):
		self.assertRaisesWithMsg(base.StructureError, 
			'At (4, 33):'
			" Parameter count is not defaulted in x and thus must be bound.",
			base.parseFromString, (Foo, "<foo><testApp name='x'><code>\n"
			"\t\tfor i in range(count):\n"
			"\t\t\tdest[i] = 42-i</code>\n"
			"<setup><par key='count'/></setup>"
			"</testApp></foo>"))

	def testBadKeyFails(self):
		self.assertRaisesWithMsg(base.StructureError, 
			"At (1, 43): '' is not a valid value for name",
			base.parseFromString, (Foo, "<foo><testApp name='x'>"
			"<setup><par key=''/></setup>"
			"</testApp></foo>"))
		self.assertRaisesWithMsg(base.StructureError, 
			"At (1, 48): 'a key' is not a valid value for name",
			base.parseFromString, (Foo, "<foo><testApp name='x'>"
			"<setup><par key='a key'/></setup>"
			"</testApp></foo>"))
	
	def testWithMacros(self):
		f = base.parseFromString(Foo, "<foo><testApp name='x'><code>\n"
			r"dest[\foobar] = weird+'\\\\n'</code>"
			r"<setup><par key='weird'>'\mesmerize{something}'</par>"
			"<par key='Foobar'>'res'</par></setup>"
			"</testApp></foo>")
		f.runApps()
		self.assertEqual(f.dest, {'res': r'gnihtemos\n'})
	
	def testParentPresent(self):
		f = base.parseFromString(Foo, "<foo><testApp name='x'><code>"
			"\t\tdest['isRight'] = 'runApps' in dir(parent)</code></testApp></foo>")
		f.runApps()
		self.assertEqual(f.dest, {"isRight": True})


class WithDefTest(testhelpers.VerboseTest):
	def testSimpleDef(self):
		f = base.parseFromString(Foo, "<foo><procDef type='t_t' id='b'>"
			"<code>dest['par']='const'</code></procDef>"
			"<testApp name='x' procDef='b'/>"
			"</foo>")
		f.runApps()
		self.assertEqual(f.dest, {"par": 'const'})

	def testPDDefaulting(self):
		f = base.parseFromString(Foo, "<foo><procDef type='t_t' id='b'>"
			"<setup><par key='par'>'const'</par></setup>"
			"<code>dest['par']=par</code></procDef>"
			"<testApp name='x' procDef='b'/>"
			"</foo>")
		f.runApps()
		self.assertEqual(f.dest, {"par": 'const'})

	def testPDRebinding(self):
		f = base.parseFromString(Foo, "<foo><procDef type='t_t' id='b'>"
			"<setup><par key='par'>'const'</par></setup>"
			"<code>dest['par']=par</code></procDef>"
			"<testApp name='x' procDef='b'><bind key='par'>'noconst'</bind>"
			"</testApp></foo>")
		f.runApps()
		self.assertEqual(f.dest, {"par": 'noconst'})

	def testFilling(self):
		f = base.parseFromString(Foo, "<foo><procDef type='t_t' id='b'>"
			"<setup><par key='par'/></setup>"
			"<code>dest['par']=par</code></procDef>"
			"<testApp name='x' procDef='b'><bind key='par'>'noconst'</bind>"
			"</testApp></foo>")
		f.runApps()
		self.assertEqual(f.dest, {"par": 'noconst'})

	def testNoFillRaises(self):
		self.assertRaisesWithMsg(base.StructureError,
			'At (1, 131):'
			" Parameter par is not defaulted in x and thus must be bound.",
			base.parseFromString, (Foo, "<foo><procDef type='t_t' id='b'>"
			"<setup><par key='par'/></setup>"
			"<code>dest['par']=par</code></procDef>"
			"<testApp name='x' procDef='b'>"
			"</testApp></foo>"))

	def testFillRandomRaises(self):
		self.assertRaisesWithMsg(base.StructureError,
			'At (1, 190):'
			" May not bind non-existing parameter(s) random.",
			base.parseFromString, (Foo, "<foo><procDef type='t_t' id='b'>"
			"<setup><par key='par'/></setup>"
			"<code>dest['par']=par</code></procDef>"
			"<testApp name='x' procDef='b'><bind key='random'>'noconst'</bind>"
			"<bind key='par'>4</bind>"
			"</testApp></foo>"))


class OriginalTest(testhelpers.VerboseTest):
	"""tests for ProcApp's setup inheritance.
	"""
	def testSCSCondDesc(self):
		from gavo import api, svcs
		base.caches.getRD("__system__/scs")
		core = base.parseFromString(svcs.DBCore, 
			'<dbCore queriedTable="data/test#adql"><condDesc original='
			'"//scs#humanInput"/></dbCore>')
		self.failUnless("genQuery", core.condDescs[0].phraseMaker.getFuncCode())
		self.failUnless("genQuery", core.condDescs[0].phraseMaker.getSetupCode())


class SetupTest(testhelpers.VerboseTest):
# Tests going after combining setup parameters and code
	def testMultiSetupPars(self):
		f = base.parseFromString(Foo, """<foo><procDef type='t_t' id='b'>
				<setup><par name="unk1">"def1"</par></setup>
				<setup><par name="unk2">"def2"</par></setup>
				</procDef></foo>""")
		pars = f.defs[0].getSetupPars()
		pars.sort(key=lambda p: p.name)
		self.assertEqual(pars[0].name, "unk1")
		self.assertEqual(pars[1].content_, '"def2"')

	def testOverridingJoin(self):
		f = base.parseFromString(Foo, """<foo><procDef type='t_t' id='b'>
					<setup><par name="unk1">"def1"</par></setup>
					<setup><par name="unk2">"def2"</par></setup></procDef>
				<procDef type="t_t" id="u" original="b">
					<setup><par name="unk1">"overridden"</par></setup></procDef></foo>""")
		pars = f.defs[1].getSetupPars()
		pars.sort(key=lambda p: p.name)
		self.assertEqual(len(pars), 2)
		self.assertEqual(pars[0].name, "unk1")
		self.assertEqual(pars[0].content_, '"overridden"')
		self.assertEqual(pars[1].content_, '"def2"')

	def testApplyJoin(self):
		f = base.parseFromString(Foo, """<foo><procDef type='t_t' id='b'>
					<setup><par name="unk1">"def1"</par></setup>
					<setup><par name="unk2">"def2"</par></setup></procDef>
				<testApp procDef="b">
					<setup><par name="unk1">"overridden"</par></setup></testApp></foo>""")
		pars = f.apps[0].getSetupPars()
		pars.sort(key=lambda p: p.name)
		self.assertEqual(len(pars), 2)
		self.assertEqual(pars[0].name, "unk1")
		self.assertEqual(pars[0].content_, '"overridden"')
		self.assertEqual(pars[1].content_, '"def2"')

	def testInheritedSetup(self):
		f = base.parseFromString(Foo, """<foo><procDef type='t_t' id='b'>
			<setup><par name="unk1">"def1"</par>
			<code>def f1(i): return unk1*i</code></setup>
			<setup><par name="unk2">4</par>
			<code>def f2(s): return s*unk2</code></setup>
			<setup><par name="c"/><par name="n"/></setup>
			<code>
				return f2(c)+f1(n)
			</code></procDef>
			<testApp procDef="b"><bind key="c">"a"</bind>
				<bind name="n">2</bind></testApp></foo>""")
		func = f.apps[0].compile()
		self.assertEqual(func(None, None), "aaaadef1def1")
	
	def testMultiLateSetup(self):
		f = base.parseFromString(Foo, """<foo><procDef type='t_t' id='b'>
			<setup><par late="True" name="unk1">"def1"</par>
			<code>def f1(a, i): return a*i</code></setup>
			</procDef>
			<testApp procDef="b">
				<setup><par late="True" name="unk1">"over"</par></setup>
				<code>return f1(unk1, 2)</code></testApp></foo>""")
		func = f.apps[0].compile()
		self.assertEqual(func(None, None), "overover")


if __name__=="__main__":
	testhelpers.main(SetupTest)
