#pragma once
#include <Arduino.h>
#include <vector>

// Route entry structure
struct RouteEntry {
    uint8_t id;           // Unique route ID
    String name;          // Custom name for the route
    String inputType;     // e.g., "gpio_digital", "gpio_analog", "mcp23017_a", "mcp23017_b", "mcp3008"
    uint8_t inputPin;     // Pin/channel ID
    String outputType;    // e.g., "gpio_digital", "gpio_analog", "pwm", "mcp23017_a", "mcp23017_b"
    uint8_t outputPin;    // Pin/channel ID
    bool enabled;         // Route active/inactive
    bool invert;          // Invert input signal (1 - inputValue)
    float threshold;      // Threshold for digital output (0.0-1.0), default 0.5
};

// Matrix management functions
void initMatrix();
bool addRoute(const RouteEntry& entry);
bool updateRoute(uint8_t id, const RouteEntry& entry);
bool deleteRoute(uint8_t id);
void clearAllRoutes();
RouteEntry* getRoute(uint8_t id);
std::vector<RouteEntry> getAllRoutes();
void processAllRoutes();

// NVS persistence
void saveMatrixToNvs();
void loadMatrixFromNvs();