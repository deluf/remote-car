
#include <SPI.h>
#include <RF24.h>
#include <nRF24L01.h>

#define CE_PIN 2
#define CSN_PIN 4
#define BLOCK_SIZE 32
#define BAUD_RATE 2000000

RF24 radio(CE_PIN, CSN_PIN);

uint8_t address[] = "00001";
uint8_t serial_buffer[BLOCK_SIZE];

void setup() 
{
	Serial.begin(BAUD_RATE);

	// Initialize the radio
	if (!radio.begin()) 
	{
		Serial.println("nRF24L01+ module not detected. Check wiring!");
		while (true) { ; } // Stop the execution
	}

	radio.setPALevel(RF24_PA_LOW);        	// FIXME: Set to MAX for production
	radio.setDataRate(RF24_2MBPS);         	// Options: RF24_250KBPS, RF24_1MBPS, RF24_2MBPS
	radio.setPayloadSize(BLOCK_SIZE);		// Maximum is 32 bytes
	radio.setChannel(100);                 	// Between 0 and 124
	
	radio.openReadingPipe(0, address);
	radio.startListening();
	//Serial.println("nRF24L01+ module initialized as receiver");
}

void loop()
{
	if (!radio.available()) { return; }
	radio.read(&serial_buffer, BLOCK_SIZE);
	
	while (Serial.availableForWrite() < BLOCK_SIZE) { ; }
	Serial.write(serial_buffer, BLOCK_SIZE);
}
