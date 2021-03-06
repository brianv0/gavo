/* Program to generate ground truth from SLALIB.  Used by stcsphertest.py. */

#include <stdio.h>
#include <string.h>
#define GNU_SOURCE
#include <math.h>

#include <slalib.h>
#include <sofa.h>

#define DEG(x) (x)/M_PI*180.
#define RAD(x) (x)*M_PI/180.


typedef struct _spherCoo {
	double alpha;
	double delta;
} spherCoo;


typedef struct _spherCooWithPM {
	double alpha;
	double delta;
	double parallax; // slalib likes this in arcsec
	double pma;      // slalib wants this in rad/trop. yr
	double pmd;      // slalib wants this in rad/trop. yr
	double rv;       // slalib likes this in km/s, positive receding
} spherCooWithPM;


void generateCases(spherCoo testCases[], char *varName, char *system,
	double ep1, double ep2)
{
	spherCoo *coo;
	char *epochSpec=strcmp(system, "FK5")?"B":"J";

	printf("%s = ([\n", varName);
	for (coo=testCases; coo->alpha!=-1; coo++) {
		double alpha = coo->alpha;
		double delta = coo->delta;
		printf("\t((%.10f, %.10f), ", alpha, delta);
		alpha *= M_PI/180.;
		delta *= M_PI/180.;
		slaPreces(system, ep1, ep2, &alpha, &delta);
		printf("(%.10f, %.10f)),\n", DEG(alpha), DEG(delta));
	}
	printf("], 'Position %s %s%f', 'Position %s %s%f')\n", system,
		epochSpec, ep1, system, epochSpec, ep2);
}

void generateEquCase(char *system, double ep1, double ep2)
{
	spherCoo testCases[] = {
		{0, 0},
		{0.1, -0.1},
		{0, 90},
		{45, 45},
		{359.9, 30},
		{359.9, -30},
		{181, -30},
		{-1, 0},
	};
	char varName[30];

	sprintf(varName, "%s%dTo%d", system, (int)ep1, (int)ep2);
	if (strcmp(system, "FK5")) {
		printf("# %s, %f -> %f\n", system, slaEpb2d(ep1)+2400000.5, 
			slaEpb2d(ep2)+2400000.5);
	} else {
		printf("# %s, %f -> %f\n", system, slaEpj2d(ep1)+2400000.5, 
			slaEpj2d(ep2)+2400000.5);
	}
	generateCases(testCases, varName, system, ep1, ep2);
}

void generateFromGalCase(void)
{
	spherCoo testCases[] = {
		{0, 0},
		{90, 0},
		{266.404996, -28.936172},
		{276.337270, 60.188552},
		{-1, 0},
	};
	spherCoo *coo;

	printf("# Gal -> J2000.0\n");
	printf("GalToJ2000 = ([\n");
	for (coo=testCases; coo->alpha!=-1; coo++) {
		double alpha, delta;
		printf("\t((%.10f, %.10f), ", coo->alpha, coo->delta);
		slaGaleq(RAD(coo->alpha), RAD(coo->delta), &alpha, &delta);
		printf("(%.10f, %.10f)),\n", DEG(alpha), DEG(delta));
	}
	printf("], 'Position GALACTIC', 'Position J2000')\n");
}


void generateToGalCase(void)
{
	spherCoo testCases[] = {
		{0, 0},
		{90, 0},
		{318.0043908771, 48.3296430519},
		{276.3372700000, 60.1885520000},
		{-1, 0},
	};
	spherCoo *coo;

	printf("# J2000.0 -> Gal\n");
	printf("J2000ToGal = ([\n");
	for (coo=testCases; coo->alpha!=-1; coo++) {
		double alpha, delta;
		printf("\t((%.10f, %.10f), ", coo->alpha, coo->delta);
		slaEqgal(RAD(coo->alpha), RAD(coo->delta), &alpha, &delta);
		printf("(%.10f, %.10f)),\n", DEG(alpha), DEG(delta));
	}
	printf("], 'Position J2000', 'Position GALACTIC')\n");
}


void generateSixCase(char *fromSystem, char *toSystem, char * label,
	void (*trafo)(double, double, double, double, double, double,
		double*, double*, double*, double*, double*, double*))
{
	spherCooWithPM testCases[] = {
		{0, 0, 0.01, 0, 0, 0},
		{0, 0, 0.01, 1e-7, 1e-7, 0},
		{0, 0, 0.01, -1e-7, 1e-7, 0},
		{0, 0, 0.01, -1e-7, -1e-7, 0},
		{0, 0, 0.01, 1e-7, -1e-7, 0},
		{0, 0, 1, 1e-7, -1e-7, 0},
		{0, 0, 1, -1e-7, 1e-7, -300},
		{0, 0, 1, 1e-7, 1e-7, 300},
		{120, 45, 0.01, 0, 0, 0},
		{130, 45, 1, 1e-7, 1e-7, 300},
		{190, -45, 1, 1e-7, 1e-7, 300},
		{0, 82, 1, 1e-7, 1e-7, 300},
		{50, -83, 1, 1e-7, 1e-7, -300},
		{-1, 0, 0, 0, 0, 0},
	};
	spherCooWithPM *coo;

	printf("# %s -> %s.\n", fromSystem, toSystem);
	printf("Six%s = ([\n", label);
	for (coo=testCases; coo->alpha!=-1; coo++) {
		double alpha, delta, pmd, pma, parallax, rv;
		printf("\t((%.10f, %.10f, %.10f, %.10f, %.10f, %.10f), ", 
			coo->alpha, coo->delta, coo->parallax,
			coo->pma, coo->pmd, coo->rv);
		trafo(RAD(coo->alpha), RAD(coo->delta), coo->pma, coo->pmd,
			coo->parallax, coo->rv, &alpha, &delta, &pma, &pmd, &parallax,
			&rv);
		printf("(%.10f, %.10f, %.10f, %.10f, %.10f, %.10f)),\n", 
			DEG(alpha), DEG(delta), parallax, pma, pmd, rv);
	}
	printf("], 'Position %s SPHER3 unit deg deg arcsec"
		" VelocityInterval unit rad/yr rad/yr km/s', "
		"'Position %s SPHER3 unit deg deg arcsec"
		" VelocityInterval unit rad/yr rad/yr km/s')\n",
		fromSystem, toSystem);
}


#define ECL_FK5TEMPLATE "'Position FK5 J2000'"
#define ECL_ECLTEMPLATE "'Time TT MJD %f Position ECLIPTIC'"

void generateEclCase(double mjd, int reverse)
{
	spherCoo testCases[] = {
		{0, 0},
		{0.1, -0.1},
		{0, 90},
		{45, 45},
		{359.9, 30},
		{359.9, -30},
		{181, -30},
		{-1, 0},
	};
	spherCoo *coo;
	int idate=(int)mjd;
	void (*trafo)(double, double, double, double*, double*);

	if (reverse) {
		printf("J2000ToECL%d = ([\n", idate);
		trafo = slaEqecl;
	} else {
		printf("ECL%dToJ2000 = ([\n", idate);
		trafo = slaEcleq;
	}
	for (coo=testCases; coo->alpha!=-1; coo++) {
		double alpha, delta;
		printf("\t((%.10f, %.10f), ", coo->alpha, coo->delta);
		trafo(RAD(coo->alpha), RAD(coo->delta), mjd, &alpha, &delta);
		printf("(%.10f, %.10f)),\n", DEG(alpha), DEG(delta));
	}
	if (reverse) {
		printf("], " ECL_FK5TEMPLATE ", " ECL_ECLTEMPLATE ")\n", mjd);
	} else {
		printf("], " ECL_ECLTEMPLATE ", " ECL_FK5TEMPLATE ")\n", mjd);
	}
}


int main(void)
{
	printf("# Test cases automatically generated by makestctruth.c.\n");
	printf("# Do not edit.  See Makefile on how to regenerate it.\n");
	generateEquCase("FK5", 1980, 2000);
	generateEquCase("FK5", 2000, 1974);
	generateEquCase("FK5", 2000, 2025);
	generateEquCase("FK5", 2000, 2057);
	generateEquCase("FK5", 2050, 2025);
	generateEquCase("FK4", 1950, 2000);
	generateEquCase("FK4", 1920, 1950);
	generateEquCase("FK4", 1875, 1980);
	generateToGalCase();
	generateFromGalCase();
	generateSixCase("FK4 B1950", "FK5 J2000", "FK4ToFK5", slaFk425);
	generateSixCase("FK5 J2000", "FK4 B1950", "FK5ToFK4", slaFk524);
	generateEclCase(51544.5, 0);
	generateEclCase(71520.7, 0);
	generateEclCase(32110.2, 0);
	generateEclCase(51544.5, 1);
	generateEclCase(71520.7, 1);
	generateEclCase(32110.2, 1);
	generateSixCase("FK5", "ICRS", "FK5ToICRS", iauFk52h);
	generateSixCase("ICRS", "FK5", "ICRSToFK5", iauH2fk5);
	return 0;
}

/* vi:ts=2 
 */
