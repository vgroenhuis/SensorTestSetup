#include "ultrasonicSensor.h"

constexpr int trigPin = 6; // Trigger Pin of Ultrasonic Sensor
constexpr int echoPin = 10; // Echo Pin of Ultrasonic Sensor

void initUltrasonicSensor() {
    Serial.println("Initializing ultrasonic sensor...");
    pinMode(trigPin, OUTPUT);
    pinMode(echoPin, INPUT);
    Serial.println("Ultrasonic sensor initialized.");
}

float readUltrasonicSensor() {
    // Send a 10 microsecond pulse to trigger the ultrasonic sensor
    digitalWrite(trigPin, LOW);
    delayMicroseconds(2);
    digitalWrite(trigPin, HIGH);
    delayMicroseconds(10);
    digitalWrite(trigPin, LOW);

    // Read the duration of the echo pulse
    long duration = pulseIn(echoPin, HIGH);

    // Calculate distance in millimeters (speed of sound is ~343 m/s)
    float distance_mm = (duration * 0.343) / 2.0;

    return distance_mm;
}