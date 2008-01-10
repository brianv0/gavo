/* A skeleton for an ingestion booster.
 */

#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <ctype.h>
#include <assert.h>
#include <math.h>
#include <endian.h> 
#include <stdlib.h>
#include <errno.h>
#include <arpa/inet.h>
#include "boosterskel.h"

#define USAGE "Usage: don't."

#define INPUT_LINE_MAX 2000

void die(char *format, ...)
{
	va_list ap;
	va_start(ap, format);
	(void)fprintf(stderr, "importbooster: ");
	(void)vfprintf(stderr, format, ap);
	va_end(ap);
	(void)fprintf(stderr, "\n");
	exit(1);
}

#define DATA_OUT(data, nbytes, destination) \
	fwrite(data, 1, nbytes, (FILE*)destination)

void linearTransform(Field *field, double offset, double factor)
{
	switch (field->type) {
		case VAL_FLOAT:
			field->val.c_float = offset+field->val.c_float*factor;
			break;
		case VAL_DOUBLE:
			field->val.c_double = offset+field->val.c_double*factor;
			break;
		case VAL_INT:
			field->val.c_int32 = offset+field->val.c_int32*factor;
			break;
		default:
			/* should we raise error for other Non-NULL types? */
			break;
	}
}

void stripWhitespace(char *str)
{
	char *cp=str, *dp;

	while (*cp && isspace(*cp)) {
		cp++;
	}
	if (!*cp) {
		*str = 0;
		return;
	}
	for (dp=str; *cp;) {
		*dp++ = *cp++;
	}
	*dp-- = 0;
	while (isspace(*dp)) {
		*dp-- = 0;
	}
}

char* copyString(char *src, char *dest, int start, int len)
{
	strncpy(dest, src+start, len);
	dest[len] = 0;
	stripWhitespace(dest);
	if (!*dest) {
		return NULL;
	}
	return dest;
}


int isWhitespaceOnly(char *str)
{
	while (*str) {
		if (! isspace(*str++)) {
			return 0;
		}
	}
	return 1;
}


#define scanfWithWhitespace(input, format, field, expType) \
	if (1!=sscanf(input, format, (expType*)&(field->val))) { \
		if (!isWhitespaceOnly(input)) { \
			die("Invalid literal for %s: '%s'", STRINGIFY(expType), input); \
		} else { \
			field->type = VAL_NULL; \
		} \
	} 


void parseFloatWithMagicNULL(char *src, Field *field, int start, int len,
		char *magicVal)
{
	char input[len+1];

	copyString(src, input, start, len);
	if (!strcmp(input, magicVal)) {
		field->type = VAL_NULL;
		return;
	}
	field->type = VAL_FLOAT;
	scanfWithWhitespace(input, "%f", field, float);
}

void parseDouble(char *src, Field *field, int start, int len)
{
	char input[len+1];

	copyString(src, input, start, len);
	field->type = VAL_DOUBLE;
	scanfWithWhitespace(input, "%lf", field, double);
}

void parseInt(char *src, Field *field, int start, int len)
{
	char input[len+1];

	copyString(src, input, start, len);
	field->type = VAL_INT;
	scanfWithWhitespace(input, "%d", field, int);
}

void parseBlankBoolean(char *src, Field *field, int srcInd)
{
	field->type = VAL_BOOL;

	if (isspace(src[srcInd])) {
		field->val.c_int8 = 0;
	} else {
		field->val.c_int8 = 1;
	}
}

void parseString(char *src, Field *field, int start, int len, char *space)
{
	copyString(src, space, start, len);
	field->length = len;
	field->type = VAL_TEXT;
	field->val.c_ptr = space;
}

void parseChar(char *src, Field *field, int srcInd)
{
	field->type = VAL_CHAR;
	if (isspace(src[srcInd])) {
		field->type = VAL_NULL;
	} else {
		field->val.c_int8 = src[srcInd];
	}
}

void writeHeader(void *destination)
{
	char *header = "PGCOPY\n\377\r\n\0";
	int32_t flags = 0;
	int32_t headerLength = 0;

	DATA_OUT(header, 11, destination);
	DATA_OUT(&flags, 4, destination);
	DATA_OUT(&headerLength, 4, destination);
}

void writeBoolean(Field *field, void *destination)
{
	char *head="\0\0\0\001";
	DATA_OUT(head, 4, destination);
	DATA_OUT(&(field->val.c_int8), 1, destination);
}

void writeInteger(Field *field, void *destination)
{
	char *head="\0\0\0\004";
	uint32_t val=htonl(field->val.c_int32);

	DATA_OUT(head, 4, destination);
	DATA_OUT(&val, 4, destination);
}


/* Complete insanity: Experimentally, it turns out that postgres wants
 * the floats in inverse byte sequence compared to what you get on
 * intel machines.  This isn't really defined by IEEE, so this might
 * not work for you.
 */
void mirrorBytes(char *mem, int numBytes)
{
	char *start = mem;
	char *end = mem+numBytes-1;

	if (__BYTE_ORDER==__BIG_ENDIAN) {
		return;
	}
	while (start<end) {
		char tmp=*start;
		*start++ = *end;
		*end-- = tmp;
	}
}

void writeFloat(Field *field, void *destination)
{
	uint32_t size=htonl(sizeof(float));
	float val=field->val.c_float;

	mirrorBytes((char*)&val, sizeof(float));
	DATA_OUT(&size, 4, destination);
	DATA_OUT(&val, sizeof(float), destination);
}

void writeDouble(Field *field, void *destination)
{
	uint32_t size=htonl(sizeof(double));
	double val=field->val.c_double;

	mirrorBytes((char*)&val, sizeof(double));
	DATA_OUT(&size, 4, destination);
	DATA_OUT(&val, sizeof(double), destination);
}

void writeText(Field *field, void *destination)
{
	int len=strlen(field->val.c_ptr);
	uint32_t size=htonl(len);
	DATA_OUT(&size, 4, destination);
	DATA_OUT(field->val.c_ptr, len, destination);
}

double round(double val)
{
	return floor(val+0.5);
}

/* This one's bad.  Pq's dump has the number of days since the epoch 2000-1-1
 * in the dump format.  We estimate this from a julian float like this.  It's
 * not ideal but should work well enough.  I dread other date formats.
 */
void writeJdate(Field *field, void *destination)
{
	int32_t daysSinceEpoch=htonl(
		(int32_t)(round((field->val.c_float-2000)*365.25)));
	uint32_t size=htonl(sizeof(int32_t));
	
	DATA_OUT(&size, 4, destination);
	DATA_OUT(&daysSinceEpoch, sizeof(int32_t), destination);
}

void writeField(Field *field, void *destination)
{
	int32_t nullValue = htonl(-1);

	switch (field->type) {
		case VAL_NULL:
			DATA_OUT(&nullValue, 4, destination);
			break;
		case VAL_BOOL:
			writeBoolean(field, destination);
			break;
		case VAL_CHAR:
			writeBoolean(field, destination);
			break;
		case VAL_INT:
			writeInteger(field, destination);
			break;
		case VAL_FLOAT:
			writeFloat(field, destination);
			break;
		case VAL_DOUBLE:
			writeDouble(field, destination);
			break;
		case VAL_TEXT:
			writeText(field, destination);
			break;
		case VAL_JDATE:
			writeJdate(field, destination);
			break;
		default:
			die("Unknown type code: %d\n", field->type);
	}
}

void writeTuple(Field *fields, int numFields, void *destination)
{
	Field *curField;
	int16_t fieldCount=htons(numFields);
	
	DATA_OUT(&fieldCount, 2, destination);
	for (curField=fields; curField-fields<numFields; curField++) {
		writeField(curField, destination);
	}
}

void createDumpfile(int argc, char **argv)
{
	FILE *inF;
	FILE *destination=stdout;
	char inputLine[INPUT_LINE_MAX];
	int lncount = 0;

	if (argc!=2) {
		die(USAGE);
	}
	if (!(inF = fopen(argv[1], "r"))) {
		die(strerror(errno));
	}
	
	writeHeader(destination);
	while (fgets(inputLine, INPUT_LINE_MAX, inF)) {
		Field *tuple;
		tuple = getTuple(inputLine);
		if (!tuple) {
			die("Bad input line: '%s'", inputLine);
		}
		writeTuple(tuple, QUERY_N_PARS, destination);
		lncount ++;
		if (!(lncount%1000)) {
			fprintf(stderr, "%08d\r", lncount);
			fflush(stderr);
		}
	}
	fprintf(stderr, "%08d records done.\n", lncount);
}

int main(int argc, char **argv)
{
	createDumpfile(argc, argv);
	return 0;
}

