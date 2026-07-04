#include "matrix.h"
#include "gpioExpanders.h"
#include "dcMotor.h"
#include "pwmServo.h"
#include <Preferences.h>
#include <vector>
#include <algorithm>

static const char *MATRIX_NAMESPACE = "matrix_cfg";
static const char *KEY_ROUTE_COUNT = "route_count";
static const char *KEY_ROUTE_PREFIX = "route_";

std::vector<RouteEntry> routes;
uint8_t nextRouteId = 1;

void loadMatrixFromNvs() {
    Serial.println("Loading matrix routes from NVS");
    Preferences prefs;
    if (!prefs.begin(MATRIX_NAMESPACE, true)) {
        Serial.println("ERROR: Failed to open NVS namespace for matrix");
        return;
    }
    
    routes.clear();
    uint16_t routeCount = prefs.getUShort(KEY_ROUTE_COUNT, 0);
    nextRouteId = 1;
    
    if (routeCount == 0) {
        Serial.println("No routes found in NVS");
        prefs.end();
        return;
    }
    
    for (uint16_t i = 0; i < routeCount; i++) {
        String key = String(KEY_ROUTE_PREFIX) + String(i);
        String routeJson = prefs.getString(key.c_str(), "");
        
        if (routeJson.length() > 0) {
            // Parse JSON route: format "id|name|inputType|inputPin|outputType|outputPin|enabled|invert|threshold"
            RouteEntry entry;
            int pos1 = routeJson.indexOf('|');
            int pos2 = routeJson.indexOf('|', pos1 + 1);
            int pos3 = routeJson.indexOf('|', pos2 + 1);
            int pos4 = routeJson.indexOf('|', pos3 + 1);
            int pos5 = routeJson.indexOf('|', pos4 + 1);
            int pos6 = routeJson.indexOf('|', pos5 + 1);
            int pos7 = routeJson.indexOf('|', pos6 + 1);
            int pos8 = routeJson.indexOf('|', pos7 + 1);
            
            if (pos1 > 0 && pos2 > 0 && pos3 > 0 && pos4 > 0 && pos5 > 0 && pos6 > 0) {
                entry.id = routeJson.substring(0, pos1).toInt();
                entry.name = routeJson.substring(pos1 + 1, pos2);
                entry.inputType = routeJson.substring(pos2 + 1, pos3);
                entry.inputPin = routeJson.substring(pos3 + 1, pos4).toInt();
                entry.outputType = routeJson.substring(pos4 + 1, pos5);
                entry.outputPin = routeJson.substring(pos5 + 1, pos6).toInt();
                entry.enabled = routeJson.substring(pos6 + 1, pos7 > 0 ? pos7 : routeJson.length()).equals("1");
                entry.invert = (pos7 > 0) ? routeJson.substring(pos7 + 1, pos8 > 0 ? pos8 : routeJson.length()).equals("1") : false;
                entry.threshold = (pos8 > 0) ? routeJson.substring(pos8 + 1).toFloat() : 0.5f;
                
                routes.push_back(entry);
                nextRouteId = std::max(nextRouteId, (uint8_t)(entry.id + 1));
            } else {
                Serial.printf("ERROR: Failed to parse route %d\n", i);
            }
        }
    }
    
    prefs.end();
    Serial.printf("Loaded %d routes from NVS\n", routes.size());
}

void saveMatrixToNvs() {
    Preferences prefs;
    if (!prefs.begin(MATRIX_NAMESPACE, false)) {
        Serial.println("ERROR: Failed to open NVS namespace for matrix (write)");
        return;
    }
    
    prefs.putUShort(KEY_ROUTE_COUNT, routes.size());
    
    for (size_t i = 0; i < routes.size(); i++) {
        const RouteEntry& entry = routes[i];
        String key = String(KEY_ROUTE_PREFIX) + String(i);
        String routeData = String(entry.id) + "|" + entry.name + "|" + entry.inputType + "|" + 
                          String(entry.inputPin) + "|" + entry.outputType + "|" + 
                          String(entry.outputPin) + "|" + (entry.enabled ? "1" : "0") + "|" +
                          (entry.invert ? "1" : "0") + "|" + String(entry.threshold, 2);
        
        size_t written = prefs.putString(key.c_str(), routeData);
        if (written == 0) {
            Serial.printf("ERROR: Failed to write route %d to NVS (insufficient space?)\n", i);
        }
    }
    
    prefs.end();
    Serial.printf("Saved %d routes to NVS\n", routes.size());
}

void initMatrix() {
    Serial.println("Initializing matrix routing system");
    loadMatrixFromNvs();
}

bool addRoute(const RouteEntry& entry) {
    RouteEntry newEntry = entry;
    newEntry.id = nextRouteId++;
    // Ensure threshold is valid (default to 0.5 if zero or invalid)
    if (newEntry.threshold <= 0.0f || newEntry.threshold > 1.0f) {
        newEntry.threshold = 0.5f;
    }
    routes.push_back(newEntry);
    saveMatrixToNvs();
    Serial.printf("Added route %d (%s): %s[%d] -> %s[%d]\n", newEntry.id, 
                 newEntry.name.c_str(),
                 newEntry.inputType.c_str(), newEntry.inputPin,
                 newEntry.outputType.c_str(), newEntry.outputPin);
    return true;
}

bool updateRoute(uint8_t id, const RouteEntry& entry) {
    for (auto& route : routes) {
        if (route.id == id) {
            route.inputType = entry.inputType;
            route.inputPin = entry.inputPin;
            route.outputType = entry.outputType;
            route.outputPin = entry.outputPin;
            route.enabled = entry.enabled;
            route.invert = entry.invert;
            route.threshold = entry.threshold;
            route.name = entry.name;
            saveMatrixToNvs();
            Serial.printf("Updated route %d\n", id);
            return true;
        }
    }
    return false;
}

bool deleteRoute(uint8_t id) {
    auto it = std::find_if(routes.begin(), routes.end(),
                          [id](const RouteEntry& e) { return e.id == id; });
    if (it != routes.end()) {
        routes.erase(it);
        saveMatrixToNvs();
        Serial.printf("Deleted route %d\n", id);
        return true;
    }
    return false;
}

void clearAllRoutes() {
    routes.clear();
    nextRouteId = 1;
    saveMatrixToNvs();
    Serial.println("Cleared all routes");
}

RouteEntry* getRoute(uint8_t id) {
    for (auto& route : routes) {
        if (route.id == id) {
            return &route;
        }
    }
    return nullptr;
}

std::vector<RouteEntry> getAllRoutes() {
    return routes;
}

void processAllRoutes() {
    for (const auto& route : routes) {
        if (!route.enabled) {
            continue;
        }
        
        // Read input based on type - normalized to 0.0-1.0 float
        float inputValue = 0.0f;
        if (route.inputType == "gpio_digital") {
            inputValue = digitalRead(route.inputPin) ? 1.0f : 0.0f;
        } else if (route.inputType == "gpio_analog") {
            // ESP32-C5 has 12-bit ADC (0-4095)
            int rawValue = analogRead(route.inputPin);
            inputValue = (rawValue + 0.5) / 4096.0f;
        } else if (route.inputType == "mcp23017_a") {
            uint8_t bankValue = getDigitalBankA();
            inputValue = ((bankValue >> route.inputPin) & 0x01) ? 1.0f : 0.0f;
        } else if (route.inputType == "mcp23017_b") {
            uint8_t bankValue = getDigitalBankB();
            inputValue = ((bankValue >> route.inputPin) & 0x01) ? 1.0f : 0.0f;
        } else if (route.inputType == "mcp3008") {
            // Read ADC voltage (0-3.3V) and normalize to 0-1
            float voltage = readAdcAnalogVolt(route.inputPin);
            inputValue = voltage / 3.3f;
            inputValue = constrain(inputValue, 0.0f, 1.0f);
        }
        
        // Apply input inversion if enabled
        if (route.invert) {
            inputValue = 1.0f - inputValue;
        }
        
        // Write output based on type - convert from 0-1 float to appropriate output range
        if (route.outputType == "gpio_digital") {
            // Use route-specific threshold
            digitalWrite(route.outputPin, inputValue >= route.threshold ? HIGH : LOW);
        } else if (route.outputType == "gpio_analog" || route.outputType == "pwm") {
            // Convert 0-1 to 0-255
            uint8_t pwmValue = (uint8_t)(inputValue * 255.0f);
            analogWrite(route.outputPin, pwmValue);
        } else if (route.outputType == "mcp23017_a") {
            uint8_t bankValue = getDigitalBankAOutput();
            if (inputValue >= route.threshold) {
                bankValue |= (1 << route.outputPin);
            } else {
                bankValue &= ~(1 << route.outputPin);
            }
            setDigitalBankA(bankValue);
        } else if (route.outputType == "mcp23017_b") {
            uint8_t bankValue = getDigitalBankBOutput();
            if (inputValue >= route.threshold) {
                bankValue |= (1 << route.outputPin);
            } else {
                bankValue &= ~(1 << route.outputPin);
            }
            setDigitalBankB(bankValue);
        } else if (route.outputType == "motorNormalized") {
            // Route input 0-1 directly to motor normalized control
            setMotorNormalizedAPI(inputValue);
        } else if (route.outputType == "motorDirection") {
            // Use threshold to determine forward (true) or reverse (false)
            setMotorDirectionAPI(inputValue >= route.threshold);
        } else if (route.outputType == "motorPwmNormalized") {
            // Route input 0-1 directly to motor PWM speed control
            setMotorPwmNormalizedAPI(inputValue);
        } else if (route.outputType == "pwmServo") {
            // Route input 0-1 to servo channel (normalized pulse width)
            setServoPwmNormalized(route.outputPin, inputValue);
        }
    }
}