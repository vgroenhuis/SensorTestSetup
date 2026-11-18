// The web server: the pages (gzipped into the firmware, see tools/pack_web.py), /api/state, and one WebSocket /ws.
//
// /ws text frames from a page:
//   {"sub":["pot","mcp3008"]}     the topics this client wants (replaces the previous list); the device then sends
//                                 {"t":"<topic>",...} at each topic's rate
//   "stream"                      the CloSer server's live relay: the "status" topic
//   {"access":...}                control (closer_access.h); the answer comes back to that client
//   "ping:<x>"                    comes back as "pong:<x>"
//
// Commands, only from the client in control (else the reply is {"need":1,"cmd":...}); reply {"cmd":...,"ok":bool}:
//   {"mcp23017":{"modeA":n,"pullupA":n,"outputA":n,"modeB":n,"pullupB":n,"outputB":n}}   (any subset)
//   {"pwm":{"ch":n,"us":1500}} | {"pwm":{"ch":n,"value":0.5}} | {"pwm":{"ch":n,"off":1}}
//   {"pwm_cfg":{"ch":n,"mode":"servo"|"raw","min":500,"max":2500}}    {"pwm_hz":50}    {"pressure_zero":0|1}
//
// Topics: status (2 Hz: also which parts answer, who has control, seconds left of a shown code), pot, mh, mcp3008,
// mcp23017, pressure (20 Hz), pwm (4 Hz). A reading whose part doesn't answer has "ok":false.
#pragma once

void web_start(void);
int web_clients(void);     // WebSocket clients subscribed to anything
