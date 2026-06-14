#pragma once
#include "RoamingWiFiManager.h"
#include "../../../../VincentLibraryTester/include/VincentCredentials.h"

/*
#if __has_include("../../../../VincentLibraryTester/include/VincentCredentials.h")
    #include "../../../../VincentLibraryTester/include/VincentCredentials.h"
#else
    #define WIFI_CREDENTIALS {{"ssid","pass"}}
    #define ADMIN_CREDENTIALS {"",""}
    #define ALIAS_URL ""
#endif
*/

const std::vector<NetworkCredentials> knownNetworks = WIFI_CREDENTIALS;;
const std::pair<String, String> adminCredentials = ADMIN_CREDENTIALS;;
const String aliasUrl = ALIAS_URL;
const bool showPasswordOnRootPage = true;
