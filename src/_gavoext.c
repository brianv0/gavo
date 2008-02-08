/* A wrapper for (for now) wcscon */

#include <Python.h>

extern void fk524(double *ra, double *dec);

static PyObject *fk524wrap(PyObject *self, PyObject *args)
{
	double ra, dec;

	if (!PyArg_ParseTuple(args, "dd", &ra, &dec)) {
		return NULL;
	}
	fk524(&ra, &dec);
	return Py_BuildValue("dd", ra, dec);
}

static PyMethodDef gavoextMethods[] = {
	{"fk524", fk524wrap, METH_VARARGS, 
		"converts from J2000 to B1950 coordinates."},
	{NULL, NULL, 0, NULL},
};


void init_gavoext(void)
{
	Py_InitModule("_gavoext", gavoextMethods);
}
