// Adapter for the reference-based C++ API found in the uploaded Ride Booking
// System submissions. Keep the wrapper names unchanged: the harness calls these
// rather than assuming the student's object/reference conventions directly.
#include "User.h"
#include "Driver.h"
#include "Ride.h"
#include "RideService.h"
#include <string>

inline User* grader_make_user(const std::string& name) {
    return new User(name);
}
inline Driver* grader_make_driver(const std::string& name, double rating) {
    return new Driver(name, rating);
}
inline Ride* grader_make_ride(User* user, int distance, Driver* driver) {
    return new Ride(*user, distance, *driver);
}
// Each testcase runs in a separate process, so the static registry begins clean.
inline void grader_clear_drivers() {}
inline void grader_add_driver(Driver* driver) {
    RideService::addDriver(*driver);
}
inline Ride* grader_request_ride(User* user, int distance, double min_rating) {
    return RideService::requestRide(*user, distance, min_rating);
}
inline void grader_complete_ride(Ride* ride) {
    if (ride != nullptr) RideService::completeRide(*ride);
}
inline Driver* grader_ride_driver(Ride* ride) {
    return ride == nullptr ? nullptr : &ride->getDriver();
}
inline double grader_ride_fare(Ride* ride) {
    return ride->calculateFare();
}
inline bool grader_driver_available(Driver* driver) {
    return driver->isAvailable();
}
