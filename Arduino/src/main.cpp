
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

// Given the current battery configuration, the smallest possible
//  PWM signal duty cycle [0-255] that makes the motors move
#define PWM_MIN 128
#define PWM_MAX 255

/**
 * Commands are encoded in a single byte:
 * - not used -		[200+]
 * STEER LEFT 		[150-199]
 * STEER RIGHT 		[100-149]
 * MARCH BACKWARD 	[050-099]
 * MARCH FORWARD 	[000-049]
 */
#define FORWARD_BACKWARD_SPLIT_POINT 50
#define RIGHT_LEFT_SPLIT_POINT 150
// Maximum intensity of each movement
#define INTENSITY_MAX 50 

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
	if (available_bytes < 1) { return; }
	uint8_t cmd_byte = Serial.read();

	// 0 <-> (INTENSITY_MAX - 1) remapped to PWM_MIN <-> PWM_MAX
	uint8_t intensity = (cmd_byte % INTENSITY_MAX);
	float intensity_percent = (float)intensity / (INTENSITY_MAX - 1);

	uint8_t	pwm_speed = (intensity == 0) ? 0 : round(intensity_percent * (PWM_MAX - PWM_MIN)) + PWM_MIN;
	if (cmd_byte < 100) {
		// 0 <= cmd_byte < 100
		analogWrite(MARCH_PWM_PIN, pwm_speed);
		digitalWrite(MARCH_FORWARD_PIN, cmd_byte < FORWARD_BACKWARD_SPLIT_POINT);
		digitalWrite(MARCH_BACKWARDS_PIN, cmd_byte >= FORWARD_BACKWARD_SPLIT_POINT);
	}
	else if (cmd_byte < 200) {
		// 100 <= cmd_byte < 200
		analogWrite(STEER_PWM_PIN, pwm_speed);
		digitalWrite(STEER_RIGHT_PIN, cmd_byte < RIGHT_LEFT_SPLIT_POINT);
		digitalWrite(STEER_LEFT_PIN, cmd_byte >= RIGHT_LEFT_SPLIT_POINT);
	}
}
