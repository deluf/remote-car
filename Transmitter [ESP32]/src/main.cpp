
#include <Arduino.h>
#include <SPI.h>
#include <RF24.h>
#include <nRF24L01.h>

#define CE_PIN 9
#define CSN_PIN 10
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
		Serial.println("nRF24L01+ module not detected. Check wiring!\n");
		while (true) { ; } // Stop the execution
	}

	radio.setPALevel(RF24_PA_LOW);        	// FIXME: Set to MAX for production
	radio.setDataRate(RF24_2MBPS);         	// Options: RF24_250KBPS, RF24_1MBPS, RF24_2MBPS
	radio.setPayloadSize(BLOCK_SIZE);		// Maximum is 32 bytes
	radio.setChannel(100);                 	// Between 0 and 124

	radio.openWritingPipe(address);
	radio.stopListening();
	//Serial.println("nRF24L01+ module initialized as transmitter");
}

void loop() 
{
    while (Serial.available() < BLOCK_SIZE) { ; }
	Serial.readBytes(serial_buffer, BLOCK_SIZE);

	uint8_t failures = 0;
    //unsigned long start_timer = micros();
	while (!radio.writeFast(&serial_buffer, BLOCK_SIZE)) 
	{
        uint8_t flags = radio.getStatusFlags();
        if (flags & RF24_TX_DF) {
			failures++;
			// Now we need to reset the tx_df flag and the radio's CE pin
			radio.ce(LOW);
			radio.clearStatusFlags(RF24_TX_DF);
			radio.ce(HIGH);
			if (failures >= 5) {
				//Serial.println("Too many failures detected. Aborting");
				break;
			}
        }
        // Else the TX FIFO is full => just continue loop
    }
	//Serial.println("Succesfully sent a block!");
    //unsigned long end_timer = micros();
}
