#include <Arduino.h>
#include <NimBLEDevice.h>
#include <string>

// Set this to 'false' later if you want the serial monitor to ONLY 
// print the distance strings (useful if feeding this into a Python script)
#define DEBUG_PRINTS true 

// Paste your 3 Tag MAC addresses here. 
const char* tagMACs[3] = {
  //"dc:b4:d9:22:3b:b9", // Old T0, the board is a bit wonky, please remember this
  "d8:85:ac:a1:0c:01", //T0
  "dc:b4:d9:22:3a:55", // T1
  "dc:b4:d9:31:8f:59"  // T2
};

static const NimBLEUUID serviceUUID("DEADBEEF-0000-0000-0000-000000000000");
static const NimBLEUUID charUUID("DEADBEEF-0000-0000-0000-000000000001");

NimBLEClient* pClients[3] = {nullptr, nullptr, nullptr};

// Data Receiving
// This triggers instantly every time a tag broadcasts a new distance string
void notifyCallback(NimBLERemoteCharacteristic* pChar, uint8_t* pData, size_t length, bool isNotify) {
    String msg = "";
    for (size_t i = 0; i < length; i++) {
        msg += (char)pData[i];
    }
    // Print the clean data string directly to the PC Serial Port
    Serial.println(msg);
}

// How to connect
bool connectToTag(int index) {
    // NimBLE requires the address type (0 = BLE_ADDR_PUBLIC)
    NimBLEAddress addr(std::string(tagMACs[index]), 0);
    
    if (pClients[index] == nullptr) {
        pClients[index] = NimBLEDevice::createClient();
        // Removed the callback class entirely to avoid v2 signature conflicts.
        // The loop() will handle disconnections beautifully on its own.
    }

    // If already connected, skip
    if (pClients[index]->isConnected()) {
        return true; 
    }

    if (DEBUG_PRINTS) Serial.printf("[*] Attempting to connect to %s...\n", tagMACs[index]);
    
    // Connect directly to the MAC address
    if (pClients[index]->connect(addr)) {
        if (DEBUG_PRINTS) Serial.printf("[+] Connected to %s!\n", tagMACs[index]);
        
        NimBLERemoteService* pSvc = pClients[index]->getService(serviceUUID);
        if (pSvc) {
            NimBLERemoteCharacteristic* pChr = pSvc->getCharacteristic(charUUID);
            if (pChr && pChr->canNotify()) {
                // Subscribe to the data stream
                pChr->subscribe(true, notifyCallback);
                return true;
            }
        }
        if (DEBUG_PRINTS) Serial.println("[-] Failed to find correct UUIDs.");
        pClients[index]->disconnect();
        return false;
    }
    
    if (DEBUG_PRINTS) Serial.println("[-] Connection failed.");
    return false;
}

void setup() {
    Serial.begin(115200);
    
    // Give the serial port a moment to initialize after plug-in
    delay(3000); 
    if (DEBUG_PRINTS) Serial.println("--- XIAO ESP32-C6 BLE Dongle Started ---");
    
    NimBLEDevice::init("");
    NimBLEDevice::setPower(ESP_PWR_LVL_P9); // Maximize Bluetooth antenna power
    NimBLEDevice::setMTU(512);              // Prevent long strings from being truncated
    
    // Initial staggered connections to avoid radio packet collisions
    for(int i = 0; i < 3; i++) {
        connectToTag(i);
        delay(3000); // Allows the antenna to stabilize the connection
    }
}

void loop() {
    // Infinite background watchdog
    // If any tag drops offline, it catches it and attempts to plug it back in
    for(int i = 0; i < 3; i++) {
        if (pClients[i] != nullptr && !pClients[i]->isConnected()) {
            connectToTag(i);
            delay(3000); // Stagger reconnection handshakes
        }
    }
    delay(1000);
}