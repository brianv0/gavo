#include <arpa/inet.h>  /* for typedefs */

#define DEGTORAD(x) ((x)/360.*2*M_PI)
#define F(x) (vals+x)

typedef enum valType_e {
	VAL_NULL,
	VAL_BOOL,
	VAL_CHAR,
	VAL_INT,
	VAL_FLOAT,
	VAL_DOUBLE,
	VAL_TEXT,
	VAL_JDATE,
} valType;

#define STRINGIFY(x) #x

typedef struct Field_s {
	valType type;
	int length; /* ignored for anything but VAL_TEXT */
	union {
		char *c_ptr;
		double c_double;
		float c_float;
		int32_t c_int32;
		int8_t c_int8;
	} val;
} Field;


Field *getTuple(char *inputLine);
void die(char *format, ...);
void linearTransform(Field *field, double offset, double factor);
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



