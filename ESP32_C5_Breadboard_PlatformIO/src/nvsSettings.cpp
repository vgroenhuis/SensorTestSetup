#include "nvsSettings.h"
#include <Preferences.h>

#include "nvs.h"
#include "nvs_flash.h"
#include <vector>
#include <algorithm>

bool serialOutputEnabled = false;
bool includePotentiometerValue = true;

void loadSerialSettingsFromNvs() {
    Serial.println("Loading settings from NVS");
    Preferences preferences;
    if (!preferences.begin(SERIAL_SETTINGS_NAMESPACE, true)) {
        Serial.println("ERROR: NVS open failed for reading serial settings - Saving defaults");
        if (!saveSerialSettingsToNvs()) {
            Serial.println("ERROR: NVS also failed for writing serial settings");
            return;
        }
        return;
    }

    serialOutputEnabled = preferences.getBool(KEY_SERIAL_ENABLED, serialOutputEnabled);
    includePotentiometerValue = preferences.getBool(KEY_INCLUDE_POT, includePotentiometerValue);
    Serial.printf("Loaded serial settings - enabled: %s, includePot: %s\n", 
                  serialOutputEnabled ? "true" : "false", 
                  includePotentiometerValue ? "true" : "false");
    preferences.end();
}

bool saveSerialSettingsToNvs() {
    Preferences preferences;
    if (!preferences.begin(SERIAL_SETTINGS_NAMESPACE, false)) {
        Serial.println("ERROR: NVS open failed for writing serial settings");
        return false;
    }

    bool okSerial = preferences.putBool(KEY_SERIAL_ENABLED, serialOutputEnabled) > 0;
    bool okPot = preferences.putBool(KEY_INCLUDE_POT, includePotentiometerValue) > 0;
    
    if (!okSerial || !okPot) {
        Serial.printf("ERROR: Serial NVS write failed - Enabled: %s, Pot: %s\n", 
                      okSerial ? "OK" : "FAIL", okPot ? "OK" : "FAIL");
    } else {
        Serial.println("Serial settings saved to NVS");
    }
    
    preferences.end();
    return okSerial && okPot;
}



// Function to list NVS entries with their values.
// Pass a namespace string (e.g., "my-app") to filter, or leave NULL to list everything.
void listNVSEntries(const char* targetNamespace) {
    nvs_iterator_t it = nullptr;
    
    // NVS_DEFAULT_PART_NAME is usually "nvs"
    esp_err_t res = nvs_entry_find(NVS_DEFAULT_PART_NAME, targetNamespace, NVS_TYPE_ANY, &it);
    
    if (res == ESP_OK) {
        Serial.println("\n--- NVS Entry List ---");
        do {
            nvs_entry_info_t info;
            nvs_entry_info(it, &info);
            
            Serial.printf("Namespace: %-15s | Key: %-15s | Type: 0x%02X | Value: ", 
                          info.namespace_name, info.key, (int)info.type);
            
            // Open namespace and read value based on type
            nvs_handle_t handle;
            esp_err_t open_res = nvs_open(info.namespace_name, NVS_READONLY, &handle);
            if (open_res == ESP_OK) {
                switch (info.type) {
                    case NVS_TYPE_U8: {
                        uint8_t value = 0;
                        if (nvs_get_u8(handle, info.key, &value) == ESP_OK) {
                            Serial.printf("%u (u8)", value);
                        }
                        break;
                    }
                    case NVS_TYPE_I8: {
                        int8_t value = 0;
                        if (nvs_get_i8(handle, info.key, &value) == ESP_OK) {
                            Serial.printf("%d (i8)", value);
                        }
                        break;
                    }
                    case NVS_TYPE_U16: {
                        uint16_t value = 0;
                        if (nvs_get_u16(handle, info.key, &value) == ESP_OK) {
                            Serial.printf("%u (u16)", value);
                        }
                        break;
                    }
                    case NVS_TYPE_I16: {
                        int16_t value = 0;
                        if (nvs_get_i16(handle, info.key, &value) == ESP_OK) {
                            Serial.printf("%d (i16)", value);
                        }
                        break;
                    }
                    case NVS_TYPE_U32: {
                        uint32_t value = 0;
                        if (nvs_get_u32(handle, info.key, &value) == ESP_OK) {
                            Serial.printf("%u (u32)", value);
                        }
                        break;
                    }
                    case NVS_TYPE_I32: {
                        int32_t value = 0;
                        if (nvs_get_i32(handle, info.key, &value) == ESP_OK) {
                            Serial.printf("%d (i32)", value);
                        }
                        break;
                    }
                    case NVS_TYPE_U64: {
                        uint64_t value = 0;
                        if (nvs_get_u64(handle, info.key, &value) == ESP_OK) {
                            Serial.printf("%llu (u64)", value);
                        }
                        break;
                    }
                    case NVS_TYPE_I64: {
                        int64_t value = 0;
                        if (nvs_get_i64(handle, info.key, &value) == ESP_OK) {
                            Serial.printf("%lld (i64)", value);
                        }
                        break;
                    }
                    case NVS_TYPE_STR: {
                        size_t len = 0;
                        if (nvs_get_str(handle, info.key, nullptr, &len) == ESP_OK) {
                            char* str_value = new char[len];
                            if (nvs_get_str(handle, info.key, str_value, &len) == ESP_OK) {
                                Serial.printf("\"%s\" (str)", str_value);
                            }
                            delete[] str_value;
                        }
                        break;
                    }
                    case NVS_TYPE_BLOB: {
                        size_t len = 0;
                        if (nvs_get_blob(handle, info.key, nullptr, &len) == ESP_OK) {
                            Serial.printf("<blob %zu bytes>", len);
                        }
                        break;
                    }
                    default:
                        Serial.printf("<unknown type>");
                        break;
                }
                nvs_close(handle);
            } else {
                Serial.printf("<failed to open namespace>");
            }
            Serial.println();
                          
        } while (nvs_entry_next(&it) == ESP_OK);
        
        // Always release the iterator when finished to avoid memory leaks
        nvs_release_iterator(it);
        Serial.println("-----------------------\n");
    } else if (res == ESP_ERR_NVS_NOT_FOUND) {
        Serial.println("No matching NVS entries found.");
    } else {
        Serial.printf("Failed to query NVS. Error code: 0x%X\n", res);
    }
}

// Function to list all available NVS namespaces in sorted order
void listNvsNamespaces() {
    nvs_iterator_t it = nullptr;
    
    // Collect all unique namespace names
    std::vector<String> namespaces;
    
    esp_err_t res = nvs_entry_find(NVS_DEFAULT_PART_NAME, NULL, NVS_TYPE_ANY, &it);
    
    if (res == ESP_OK) {
        do {
            nvs_entry_info_t info;
            nvs_entry_info(it, &info);
            
            // Check if this namespace is already in the list
            bool found = false;
            for (const auto& ns : namespaces) {
                if (ns == info.namespace_name) {
                    found = true;
                    break;
                }
            }
            
            if (!found) {
                namespaces.push_back(String(info.namespace_name));
            }
                          
        } while (nvs_entry_next(&it) == ESP_OK);
        
        nvs_release_iterator(it);
        
        // Sort namespaces in ascending order
        std::sort(namespaces.begin(), namespaces.end(), 
                  [](const String& a, const String& b) { return a < b; });
        
        // Print sorted namespaces
        Serial.println("\n--- NVS Namespaces (sorted) ---");
        for (size_t i = 0; i < namespaces.size(); i++) {
            Serial.printf("%d. %s\n", i + 1, namespaces[i].c_str());
        }
        Serial.println("-------------------------------\n");
    } else if (res == ESP_ERR_NVS_NOT_FOUND) {
        Serial.println("No NVS namespaces found.");
    } else {
        Serial.printf("Failed to query NVS. Error code: 0x%X\n", res);
    }
}

// Function to list all NVS entries grouped by namespace in sorted order
void listAllNvsEntries() {
    nvs_iterator_t it = nullptr;
    
    // Collect all unique namespace names
    std::vector<String> namespaces;
    
    esp_err_t res = nvs_entry_find(NVS_DEFAULT_PART_NAME, NULL, NVS_TYPE_ANY, &it);
    
    if (res == ESP_OK) {
        do {
            nvs_entry_info_t info;
            nvs_entry_info(it, &info);
            
            // Check if this namespace is already in the list
            bool found = false;
            for (const auto& ns : namespaces) {
                if (ns == info.namespace_name) {
                    found = true;
                    break;
                }
            }
            
            if (!found) {
                namespaces.push_back(String(info.namespace_name));
            }
                          
        } while (nvs_entry_next(&it) == ESP_OK);
        
        nvs_release_iterator(it);
        
        // Sort namespaces in ascending order
        std::sort(namespaces.begin(), namespaces.end(), 
                  [](const String& a, const String& b) { return a < b; });
        
        // List entries for each namespace in sorted order
        Serial.println("\n========== ALL NVS ENTRIES (grouped by namespace) ==========");
        for (const auto& ns : namespaces) {
            listNVSEntries(ns.c_str());
        }
        Serial.println("===========================================================\n");
    } else if (res == ESP_ERR_NVS_NOT_FOUND) {
        Serial.println("No NVS entries found.");
    } else {
        Serial.printf("Failed to query NVS. Error code: 0x%X\n", res);
    }
}

// Function to print NVS statistics (total, used, and available sizes)
void printNvsStatistics() {
    nvs_stats_t nvs_stats;
    esp_err_t err = nvs_get_stats(NVS_DEFAULT_PART_NAME, &nvs_stats);
    
    if (err == ESP_OK) {
        size_t totalSize = nvs_stats.total_entries * 32;  // Each entry is 32 bytes in NVS
        size_t usedSize = nvs_stats.used_entries * 32;
        size_t availableSize = nvs_stats.free_entries * 32;
        double percentUsed = (nvs_stats.used_entries > 0) ? 
            (100.0 * nvs_stats.used_entries / nvs_stats.total_entries) : 0.0;
        
        Serial.println("\n========== NVS Statistics ==========");
        Serial.printf("Total Entries:     %d\n", nvs_stats.total_entries);
        Serial.printf("Used Entries:      %d\n", nvs_stats.used_entries);
        Serial.printf("Free Entries:      %d\n", nvs_stats.free_entries);
        Serial.printf("Total Size:        %.2f KB\n", totalSize / 1024.0);
        Serial.printf("Used Size:         %.2f KB\n", usedSize / 1024.0);
        Serial.printf("Available Size:    %.2f KB\n", availableSize / 1024.0);
        Serial.printf("Utilization:       %.1f%%\n", percentUsed);
        Serial.println("====================================\n");
    } else {
        Serial.printf("Failed to get NVS statistics. Error code: 0x%X\n", err);
    }
}