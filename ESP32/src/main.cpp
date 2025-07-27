
#include <SPI.h>
#include <RF24.h>
#include <nRF24L01.h>

/* Only change these three settings */
#define CE_PIN 2
#define CSN_PIN 4
#define RECEIVER

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
	radio.setPayloadSize(BLOCK_SIZE);		
	radio.setChannel(100);                 	// Between 0 and 125, ~> 100 to avoid WiFi frequencies

#ifdef TRANSMITTER
	radio.openWritingPipe(address);
	radio.stopListening();
#else
	radio.openReadingPipe(0, address);
	radio.startListening();
#endif
}

void loop() 
{
#ifdef TRANSMITTER
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
			if (failures >= 20) {
				Serial.println("Too many failures detected. Aborting");
				break;
			}
        }
        // Else the TX FIFO is full => just continue loop
    }
    //unsigned long end_timer = micros();
#else
	if (!radio.available()) { return; }
	radio.read(&serial_buffer, BLOCK_SIZE);
	
	while (Serial.availableForWrite() < BLOCK_SIZE) { ; }
	Serial.write(serial_buffer, BLOCK_SIZE);
#endif
}
