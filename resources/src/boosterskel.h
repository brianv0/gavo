#define _XOPEN_SOURCE
#include <time.h>
#include <arpa/inet.h>  /* for typedefs */

#define DEGTORAD(x) ((x)/360.*2*M_PI)
#define F(x) (vals+x)

typedef enum valType_e {
	VAL_NULL,
	VAL_BOOL,
	VAL_CHAR,
	VAL_SHORT,
	VAL_INT,
	VAL_FLOAT,
	VAL_DOUBLE,
	VAL_TEXT,
	VAL_JDATE,  /* a julian date */
	VAL_DATE,   /* date expressed as a time_t */
	VAL_DATETIME, /* date and time expressed as a time_t */
} valType;

#define STRINGIFY(x) #x
#define STRINGIFY_VAL(arg) STRINGIFY(arg)

typedef struct Field_s {
	valType type;
	int length; /* ignored for anything but VAL_TEXT */
	union {
		char *c_ptr;
		double c_double;
		float c_float;
		int32_t c_int32;
		int16_t c_int16;
		int8_t c_int8;
		time_t time;
	} val;
} Field;


#define MAKE_NULL(fi) F(fi)->type=VAL_NULL
#define MAKE_DOUBLE(fi, value) {\
	F(fi)->type=VAL_DOUBLE; F(fi)->val.c_double = value;}
#define MAKE_FLOAT(fi, value) {\
	F(fi)->type=VAL_FLOAT; F(fi)->val.c_float = value;}
#define MAKE_SHORT(fi, value) {\
	F(fi)->type=VAL_SHORT; F(fi)->val.c_int16 = value;}
#define MAKE_CHAR(fi, value) {\
	F(fi)->type=VAL_CHAR; F(fi)->val.c_int8 = value;}
#define MAKE_CHAR_NULL(fi, value, nullvalue) {\
	if ((value)==(nullvalue)) { MAKE_NULL(fi); } else {MAKE_CHAR(fi, value);}}

#define MAKE_WITH_NULL(type, fi, value, nullvalue) {\
	if ((value)==(nullvalue)) { MAKE_NULL(fi); } else {\
		MAKE_##type(fi, value);}}

#define AS2DEG(field) linearTransform(F(field), 0, 1/3600.)
#define MAS2DEG(field) linearTransform(F(field), 0, 1/3600./1000.)

#define fieldscanf(str, fieldName, type, ...) \
	real_fieldscanf((str), vals+(fieldName), type, STRINGIFY(fieldName),\
		## __VA_ARGS__)

Field *getTuple(char *inputLine);
void die(char *format, ...);
void linearTransform(Field *field, double offset, double factor);
int julian2unixtime(double julian, time_t *result);
void makeTimeFromJd(Field *field);
void stripWhitespace(char *str);
char* copyString(char *src, char *dest, int start, int len);
int isWhitespaceOnly(char *str);
void parseFloatWithMagicNULL(char *src, Field *field, int start, int len,
		char *magicVal);
void parseDouble(char *src, Field *field, int start, int len);
void parseInt(char *src, Field *field, int start, int len);
void parseBlankBoolean(char *src, Field *field, int srcInd);
void parseString(char *src, Field *field, int start, int len, char *space);
void parseChar(char *src, Field *field, int srcInd);
void real_fieldscanf(char *str, Field *f, valType type, char *fieldName, ...);
