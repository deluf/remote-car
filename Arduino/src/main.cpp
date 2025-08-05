
#include <Arduino.h>

#define BAUD_RATE 115200

#define STEER_PWM_PIN 8
#define STEER_RIGHT_PIN 9
#define STEER_LEFT_PIN 10
#define MARCH_BACKWARDS_PIN 11
#define MARCH_FORWARD_PIN 12
#define MARCH_PWM_PIN 13

void setup() 
{
	Serial.begin(BAUD_RATE);

	pinMode(STEER_PWM_PIN, OUTPUT);
	pinMode(STEER_RIGHT_PIN, OUTPUT);  
  	pinMode(STEER_LEFT_PIN, OUTPUT);
  	pinMode(MARCH_BACKWARDS_PIN, OUTPUT);
	pinMode(MARCH_FORWARD_PIN, OUTPUT);
	pinMode(MARCH_PWM_PIN, OUTPUT);

	analogWrite(STEER_PWM_PIN, 0);
	digitalWrite(STEER_RIGHT_PIN, LOW);
	digitalWrite(STEER_LEFT_PIN, LOW);

	analogWrite(MARCH_PWM_PIN, 0);
	digitalWrite(MARCH_BACKWARDS_PIN, LOW);
	digitalWrite(MARCH_FORWARD_PIN, LOW);
}

enum COMMAND 
{
	MARCH,
	STEER
};

enum DIRECTION 
{
	FORWARD,
	BACKWARDS,
	RIGHT,
	LEFT
};

uint8_t buffer[3];

void loop() 
{
	int available_bytes = Serial.available();
	if (available_bytes < 3) { return; }
	Serial.readBytes(buffer, 3);

	// <command> <direction> <speed>
	COMMAND command = (COMMAND)buffer[0];
	DIRECTION direction = (DIRECTION)buffer[1];
	uint8_t speed = buffer[2];

	if (command == MARCH) 
	{
		analogWrite(MARCH_PWM_PIN, speed);
		digitalWrite(MARCH_FORWARD_PIN, direction == FORWARD);
		digitalWrite(MARCH_BACKWARDS_PIN, direction == BACKWARDS);
	}
	else if (command == STEER) 
	{
		analogWrite(STEER_PWM_PIN, speed);
		digitalWrite(STEER_RIGHT_PIN, direction == RIGHT);
		digitalWrite(STEER_LEFT_PIN, direction == LEFT);
	}
}

// DO NOT TOUCH
//while (Serial.availableForWrite() < available_bytes) { ; }
//Serial.write(block_buffer, available_bytes);
