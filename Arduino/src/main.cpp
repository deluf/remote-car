
#include <Arduino.h>

#define BAUD_RATE 115200

#define STEER_PWM_PIN 5 		// Gray wire
#define STEER_RIGHT_PIN 6		// Orange wire
#define STEER_LEFT_PIN 7		// Yellow wire
#define MARCH_BACKWARDS_PIN 8	// Green wire
#define MARCH_FORWARD_PIN 9		// Blue wire
#define MARCH_PWM_PIN 10		// Purple wire

#define CLACSON_PIN 2
bool clacson_toggled = false;

#define NEON_PIN_1 12	// Blue wires
#define NEON_PIN_2 13
bool neon_toggled = false;

#define CAR_BATTERY_PIN A0	// Orange wire
#define ELECTRONICS_BATTERY_PIN A1	// Yellow wire
#define VOLTAGE_UPDATE_INTERVAL_MS 1000
#define ADC_RESOLUTION 10	// bits
const float ADC_VREF = 5.0;	// Volt
const float ADC_STEPS = (1 << ADC_RESOLUTION) - 1;

const float R1_CAR = 5079 + 1990;	// Ohm | From battery + to ADC pin
const float R2_CAR = 9945;			// Ohm | From ADC pin to GND
const float RESISTOR_RATIO_CAR = (R1_CAR + R2_CAR) / R2_CAR;

const float R1_ELECTRONICS = 5088 + 1994;	// Ohm | From battery + to ADC pin
const float R2_ELECTRONICS = 9935;			// Ohm | From ADC pin to GND
const float RESISTOR_RATIO_ELECTRONICS = (R1_ELECTRONICS + R2_ELECTRONICS) / R2_ELECTRONICS;

// Given the current battery configuration, the smallest possible
//  PWM signal duty cycle [0-255] that makes the motors move
#define PWM_MIN 55
#define PWM_MAX 255

/**
 * Commands are encoded in a single byte:
 * TOGGLE_NEON		[202]
 * TOGGLE_CLACSON 	[201]
 * SWITCH_CAMERA	[200] (android-only)
 * STEER LEFT 		[150-199]
 * STEER RIGHT 		[100-149]
 * MARCH BACKWARD 	[050-099]
 * MARCH FORWARD 	[000-049]
 */
#define CMD_TOGGLE_CLACSON 201
#define CMD_TOGGLE_NEON 202
#define FORWARD_BACKWARD_SPLIT_POINT 50
#define RIGHT_LEFT_SPLIT_POINT 150
#define INTENSITY_MAX 50 // Maximum intensity of each movement

unsigned long time_since_voltage_reading;
int last_steer_pin;

float read_car_battery_voltage()
{
	float adc_reading = analogRead(CAR_BATTERY_PIN);
	float adc_reading_volt = adc_reading / ADC_STEPS * ADC_VREF;
	return adc_reading_volt * RESISTOR_RATIO_CAR;
}

float read_electronics_battery_voltage()
{
	float adc_reading = analogRead(ELECTRONICS_BATTERY_PIN);
	float adc_reading_volt = adc_reading / ADC_STEPS * ADC_VREF;
	return adc_reading_volt * RESISTOR_RATIO_ELECTRONICS;
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
	
	pinMode(CLACSON_PIN, OUTPUT);
	pinMode(NEON_PIN_1, OUTPUT);
	pinMode(NEON_PIN_2, OUTPUT);

	analogWrite(STEER_PWM_PIN, 0);
	digitalWrite(STEER_RIGHT_PIN, LOW);
	digitalWrite(STEER_LEFT_PIN, LOW);

	analogWrite(MARCH_PWM_PIN, 0);
	digitalWrite(MARCH_BACKWARDS_PIN, LOW);
	digitalWrite(MARCH_FORWARD_PIN, LOW);

	digitalWrite(CLACSON_PIN, LOW);
	digitalWrite(NEON_PIN_1, LOW);
	digitalWrite(NEON_PIN_2, LOW);
}

void loop()
{
	unsigned long current_time = millis();
	if (current_time - time_since_voltage_reading > VOLTAGE_UPDATE_INTERVAL_MS)
	{
		unsigned int available_bytes = Serial.availableForWrite();
		if (available_bytes >= 2) 
		{
			float car_battery_volt = read_car_battery_voltage();
			float electronics_battery_volt = read_electronics_battery_voltage();
			time_since_voltage_reading = millis();

			/**
			 * The theoretical maximum voltage for a 2S lithium ion battery is 8.4 volts
			 * This means that we can send the measured voltage in centivolts (1 decimal 
			 *  place of precision) using only one byte and still have the most significant
			 *  bit free (0-84 is well within the range of 7 bits).
			 * The MSB is therefore used to encode the measured battery (0 = car, 1 = electronics)
			 */
			uint8_t car_battery_centivolt = int(car_battery_volt * 10);
			uint8_t electronics_battery_centivolt = 0x80 | int(electronics_battery_volt * 10);

			Serial.write(&car_battery_centivolt, 1);
			Serial.write(&electronics_battery_centivolt, 1);
		}
	}

	int available_bytes = Serial.available();
	if (available_bytes < 1) { return; }
	uint8_t cmd_byte = Serial.read();

	if (cmd_byte == CMD_TOGGLE_CLACSON) 
	{
		clacson_toggled = !clacson_toggled;
		digitalWrite(CLACSON_PIN, clacson_toggled ? HIGH : LOW);
		return;
	}
	
	if (cmd_byte == CMD_TOGGLE_NEON) {
		neon_toggled = !neon_toggled;
		digitalWrite(NEON_PIN_1, neon_toggled ? HIGH : LOW);
		digitalWrite(NEON_PIN_2, neon_toggled ? HIGH : LOW);
		return;
	}

	// 0 <-> (INTENSITY_MAX - 1) remapped to PWM_MIN <-> PWM_MAX
	uint8_t intensity = (cmd_byte % INTENSITY_MAX);
	float intensity_percent = (float)intensity / (INTENSITY_MAX - 1);

	uint8_t	pwm_speed = (intensity == 0) ? 0 : round(intensity_percent * (PWM_MAX - PWM_MIN)) + PWM_MIN;
	if (cmd_byte < 100) 
	{
		// 0 <= cmd_byte < 100 : MARCH
		analogWrite(MARCH_PWM_PIN, pwm_speed);
		digitalWrite(MARCH_FORWARD_PIN, cmd_byte < FORWARD_BACKWARD_SPLIT_POINT ? HIGH : LOW);
		digitalWrite(MARCH_BACKWARDS_PIN, cmd_byte >= FORWARD_BACKWARD_SPLIT_POINT ? HIGH : LOW);
	}
	else if (cmd_byte < 200) 
	{
		// 100 <= cmd_byte < 200 : STEER
		// For physical constraints of the steering mechanism, we currently always steer all the way
		if (pwm_speed > 0) 
		{
			analogWrite(STEER_PWM_PIN, 255);
			last_steer_pin = cmd_byte < RIGHT_LEFT_SPLIT_POINT ? STEER_RIGHT_PIN : STEER_LEFT_PIN;
			digitalWrite(last_steer_pin, HIGH);
		}
		else 
		{
			// If the desired speed is 0 (drive straight) briefly counter steer
			//  to mitigate the imperfections of the steering mechanism
			digitalWrite(last_steer_pin, LOW);
			int counter_steer_pin = last_steer_pin == STEER_RIGHT_PIN ? STEER_LEFT_PIN : STEER_RIGHT_PIN;
			digitalWrite(counter_steer_pin, HIGH);
			delay(10);
			digitalWrite(counter_steer_pin, LOW);
			analogWrite(STEER_PWM_PIN, 0);
		}
	}
}
