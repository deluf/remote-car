
#include <SPI.h>
#include <RF24.h>
#include <nRF24L01.h>

/* \\\ Only change these settings /// */
#define CE_PIN 16		// 16 for ESP32, 9 for ARDUINO
#define CSN_PIN 17		// 17 for ESP32, 10 for ARDUINO
//#define TRANSMITTER 	// Comment if RECEIVER
//#define DEBUG			// Comment if PRODUCTION
/* /// Only change these settings \\\ */

#ifdef DEBUG
#define BAUD_RATE 115200
#else
#define BAUD_RATE 1000000
#endif

#define BLOCK_SIZE 32

RF24 radio(CE_PIN, CSN_PIN);

uint8_t address[] = "00001";
uint8_t block_buffer[BLOCK_SIZE];

void setup() 
{
	Serial.begin(BAUD_RATE);
	
	// Initialize the radio
	if (!radio.begin()) 
	{
#ifdef DEBUG
		Serial.println("nRF24L01+ module not detected");
#endif
		while (true) { ; } // Stop the execution
	}

	radio.setPALevel(RF24_PA_MIN);        	// FIXME: Set to MAX for production
	radio.setDataRate(RF24_2MBPS);         	// Options: RF24_250KBPS, RF24_1MBPS, RF24_2MBPS
	radio.setPayloadSize(BLOCK_SIZE);		
	radio.setChannel(120);                 	// Between 0 and 125, ~> 100 to avoid WiFi frequencies

#ifdef TRANSMITTER
	radio.openWritingPipe(address);
	radio.stopListening();
	#ifdef DEBUG
	Serial.println("nRF24L01+ module correctly initialized as TRANSMITTER");
	#endif
#else
	radio.openReadingPipe(0, address);
	radio.startListening();
	#ifdef DEBUG
	Serial.println("nRF24L01+ module correctly initialized as RECEIVER");
	#endif
#endif
}

#ifdef DEBUG
int block_number = 0;
#endif

void loop() 
{
	#ifdef DEBUG
	block_number++;
	#endif

#ifdef TRANSMITTER
    while (Serial.available() < BLOCK_SIZE) { ; }
	Serial.readBytes(block_buffer, BLOCK_SIZE);

	#ifdef DEBUG
	Serial.print("Received block #");
	Serial.print(block_number);
	Serial.print(" from the serial port [");
	Serial.print(block_buffer[0]);
	Serial.print(", ");
	Serial.print(block_buffer[1]);
	Serial.print(", ..., ");
	Serial.print(block_buffer[BLOCK_SIZE - 2]);
	Serial.print(", ");
	Serial.print(block_buffer[BLOCK_SIZE - 1]);
	Serial.println("]");
	#endif

	#ifdef DEBUG
	unsigned long start_timer = micros();
	#endif

	uint8_t failures = 0;
	while (!radio.writeFast(&block_buffer, BLOCK_SIZE)) 
	{
        uint8_t flags = radio.getStatusFlags();
        if (flags & RF24_TX_DF) 
		{
			radio.ce(LOW);
			radio.clearStatusFlags(RF24_TX_DF);
			radio.ce(HIGH);
			failures++;
			if (failures >= 100) 
			{
	#ifdef DEBUG
				Serial.print("Too many failures detected. Aborting block #");
				Serial.println(block_number);
	#endif
				return;
			}
        }
    }
	
	#ifdef DEBUG
	unsigned long end_timer = micros();
	
	Serial.print("Block #");
	Serial.print(block_number);
	Serial.print(" successfully forwarded via radio in ");
    Serial.print(end_timer - start_timer);
    Serial.print(" us with ");
    Serial.print(failures);
    Serial.println(" failures detected");
	#endif

#else
	if (!radio.available()) { return; }
	radio.read(&block_buffer, BLOCK_SIZE);

	#ifdef DEBUG
	Serial.print("Received block #");
	Serial.print(block_number);
	Serial.print(" from the radio module [");
	Serial.print(block_buffer[0]);
	Serial.print(", ");
	Serial.print(block_buffer[1]);
	Serial.print(", ..., ");
	Serial.print(block_buffer[BLOCK_SIZE - 2]);
	Serial.print(", ");
	Serial.print(block_buffer[BLOCK_SIZE - 1]);
	Serial.println("]");
	#endif
	
	while (Serial.availableForWrite() < BLOCK_SIZE) { ; }
	Serial.write(block_buffer, BLOCK_SIZE);

	#ifdef DEBUG
	Serial.print("\nBlock #");
	Serial.print(block_number);
	Serial.println(" successfully forwarded via serial");
	#endif
#endif
}
