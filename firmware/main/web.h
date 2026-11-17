// The web server: the pages (gzipped into the firmware, see tools/pack_web.py), /api/state, and one WebSocket /ws.
//
// /ws text frames from a page:
//   {"sub":["pot","mcp3008"]}     the topics this client wants (replaces the previous list); the device then sends
//                                 {"t":"<topic>",...} at each topic's rate
//   "stream"                      the CloSer server's live relay: the "status" topic
//   {"access":...}                control (closer_access.h); the answer comes back to that client
//   "ping:<x>"                    comes back as "pong:<x>"
//
// Topics: status (2 Hz), pot, mh, mcp3008 (20 Hz). A reading whose sensor doesn't answer has "ok":false.
#pragma once

void web_start(void);
int web_clients(void);     // WebSocket clients subscribed to anything
