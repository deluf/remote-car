
#include <Arduino.h>

#define BAUD_RATE 115200

#define STEER_PWM_PIN 8
#define STEER_RIGHT_PIN 9
#define STEER_LEFT_PIN 10
#define MARCH_BACKWARDS_PIN 11
#define MARCH_FORWARD_PIN 12
#define MARCH_PWM_PIN 13

#define CAR_BATTERY_PIN A0
#define CAR_BATTERY_VOLTAGE_UPDATE_INTERVAL_MS 1000
#define ADC_RESOLUTION 10	// bits
const float R1 = 5088 + 1994;	// Ohm | From battery + to ADC pin
const float R2 = 9935;			// Ohm | From ADC pin to GND
const float RESISTOR_RATIO = (R1 + R2) / R2;
const float ADC_VREF = 5.0;	// Volt
const float ADC_STEPS = (1 << ADC_RESOLUTION) - 1;

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

uint8_t recv_buffer[3];
unsigned long time_since_reading;

float read_car_battery_voltage()
{
	float adc_reading = analogRead(CAR_BATTERY_PIN);
	float adc_reading_volt = adc_reading / ADC_STEPS * ADC_VREF;
	return adc_reading_volt * RESISTOR_RATIO;
}

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

void loop() 
{
	unsigned long current_time = millis();
	if (current_time - time_since_reading > CAR_BATTERY_VOLTAGE_UPDATE_INTERVAL_MS)
	{
		unsigned int available_bytes = Serial.availableForWrite();
		if (available_bytes >= 1) {
			time_since_reading = millis();
			float car_battery_volt = read_car_battery_voltage();
			// One byte is sufficient to store voltage in the range 0 - 25.5V
			uint8_t car_battery_centivolt = int(car_battery_volt * 10);
			Serial.write(&car_battery_centivolt, 1);
		}
	}

	int available_bytes = Serial.available();
	if (available_bytes < 3) { return; }
	Serial.readBytes(recv_buffer, 3);

	// <command> <direction> <speed>
	COMMAND command = (COMMAND)recv_buffer[0];
	DIRECTION direction = (DIRECTION)recv_buffer[1];
	uint8_t speed = recv_buffer[2];

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
