
#include <SPI.h>
#include <RF24.h>
#include <nRF24L01.h>

#define BAUD_RATE 115200
uint8_t block_buffer[32];

void setup() 
{
	Serial.begin(BAUD_RATE);	
}

void loop() 
{
	int available_bytes = Serial.available();
	if (available_bytes <= 0) { return; }

	Serial.readBytes(block_buffer, available_bytes);

	// Echo
	while (Serial.availableForWrite() < available_bytes) { ; }
	Serial.write(block_buffer, available_bytes);
}
