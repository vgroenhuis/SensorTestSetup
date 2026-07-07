#pragma once

void initLoadcell();

// Returns force in N
// May return NAN if loadcell is not ready
float readLoadcell();
