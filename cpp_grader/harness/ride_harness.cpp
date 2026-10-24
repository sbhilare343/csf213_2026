// Fixed, independent-per-process regression tests derived from the official
// CS F213 OOP Lab Midsem rubric. The Python runner invokes one ID per process.
// The two marked lines are adapted for header-based or monolithic student code.
/*__STUDENT_SOURCE_INJECTION__*/
#include "grader_api_adapter.hpp"
#include <cmath>
#include <exception>
#include <iostream>
#include <stdexcept>
#include <string>

static void require(bool ok, const std::string& message) {
    if (!ok) throw std::runtime_error(message);
}
static void require_fare(Ride* ride, double expected, const std::string& message) {
    require(ride != nullptr, message + ": ride is null");
    const double actual = grader_ride_fare(ride);
    require(std::isfinite(actual) && std::fabs(actual - expected) <= 1e-9,
            message + ": expected fare " + std::to_string(expected) + ", got " + std::to_string(actual));
}
static User* user(const std::string& name = "U") { return grader_make_user(name); }
static Driver* driver(int number, double rating) {
    Driver* d = grader_make_driver("D" + std::to_string(number), rating);
    grader_add_driver(d);
    return d;
}
static Ride* request(User* u, int distance, double min_rating) {
    return grader_request_ride(u, distance, min_rating);
}
static void reset() { grader_clear_drivers(); }

#define CHECK_CASE(ID, BODY) \
static void test_##ID() { reset(); BODY; }

CHECK_CASE(F1, {
    Driver* d = grader_make_driver("FareDriver", 4.5);
    Ride* r = grader_make_ride(user(), 5, d);
    require_fare(r, 180.0, "F1");
})
CHECK_CASE(F2, {
    Driver* d = grader_make_driver("FareDriver", 4.5);
    require_fare(grader_make_ride(user(), 1, d), 100.0, "F2");
})
CHECK_CASE(F3, {
    Driver* d = grader_make_driver("FareDriver", 4.5);
    require_fare(grader_make_ride(user(), 25, d), 580.0, "F3");
})
CHECK_CASE(F4, {
    Driver* d = grader_make_driver("FareDriver", 4.5);
    require_fare(grader_make_ride(user(), 100, d), 2080.0, "F4");
})
CHECK_CASE(Q1, {
    Driver* a = driver(1, 4.5); Ride* r = request(user(), 10, 4.0);
    require(r && grader_ride_driver(r) == a, "Q1: eligible first driver not returned");
    require(!grader_driver_available(a), "Q1: assigned driver still available");
})
CHECK_CASE(Q2, {
    require(request(user(), 10, 4.0) == nullptr, "Q2: expected null when no drivers exist");
})
CHECK_CASE(Q3, {
    Driver* a = driver(1, 4.1);
    require(request(user(), 10, 4.5) == nullptr, "Q3: low-rated driver was assigned");
    require(grader_driver_available(a), "Q3: failed request changed availability");
})
CHECK_CASE(Q4, {
    Driver* a = driver(1, 4.3); Ride* r = request(user(), 10, 4.3);
    require(r && grader_ride_driver(r) == a, "Q4: equal rating should qualify");
    require(!grader_driver_available(a), "Q4: assigned driver still available");
})
CHECK_CASE(Q5, {
    Driver* a = driver(1, 4.29);
    require(request(user(), 10, 4.3) == nullptr, "Q5: below-minimum rating qualified");
    require(grader_driver_available(a), "Q5: low-rated driver availability changed");
})
CHECK_CASE(Q6, {
    Driver* a = driver(1, 4.1); Driver* b = driver(2, 4.5);
    Ride* r = request(user(), 10, 4.3);
    require(r && grader_ride_driver(r) == b, "Q6: did not skip low-rated first driver");
    require(grader_driver_available(a), "Q6: skipped driver should stay available");
})
CHECK_CASE(O1, {
    Driver* a = driver(1, 4.5); (void)driver(2, 4.9);
    Ride* r = request(user(), 10, 4.0);
    require(r && grader_ride_driver(r) == a, "O1: must pick first eligible driver, not highest-rated");
})
CHECK_CASE(O2, {
    Driver* a = driver(1, 4.9); (void)driver(2, 4.5);
    Ride* r = request(user(), 10, 4.0);
    require(r && grader_ride_driver(r) == a, "O2: must pick first eligible driver, not lowest-rated");
})
CHECK_CASE(O3, {
    (void)driver(1, 4.0); Driver* b = driver(2, 4.5); (void)driver(3, 4.6);
    Ride* r = request(user(), 10, 4.4);
    require(r && grader_ride_driver(r) == b, "O3: must pick first qualifying driver in insertion order");
})
CHECK_CASE(S1, {
    Driver* a = driver(1, 4.5); Ride* r = request(user(), 10, 4.0);
    require(r && !grader_driver_available(a), "S1: assigned driver must become unavailable");
})
CHECK_CASE(S2, {
    Driver* a = driver(1, 4.1); Driver* b = driver(2, 4.2);
    require(request(user(), 10, 4.5) == nullptr, "S2: expected failed request");
    require(grader_driver_available(a) && grader_driver_available(b), "S2: failed request changed driver state");
})
CHECK_CASE(S3, {
    Driver* a = driver(1, 4.9); Driver* b = driver(2, 4.8);
    Ride* r1 = request(user(), 10, 4.0); Ride* r2 = request(user(), 10, 4.0);
    require(r1 && grader_ride_driver(r1) == a, "S3: first request should receive driver 1");
    require(r2 && grader_ride_driver(r2) == b, "S3: second request should skip busy driver 1");
})
CHECK_CASE(S4, {
    (void)driver(1, 4.5); (void)driver(2, 4.5);
    Ride* r1 = request(user(), 10, 4.0); Ride* r2 = request(user(), 10, 4.0); Ride* r3 = request(user(), 10, 4.0);
    require(r1 && r2 && r3 == nullptr, "S4: expected ride, ride, null for three requests and two drivers");
})
CHECK_CASE(S5, {
    Driver* a = driver(1, 4.9); Driver* b = driver(2, 4.0);
    Ride* occupying = request(user("OccupyingUser"), 10, 4.5);
    require(occupying && grader_ride_driver(occupying) == a, "S5 setup: high-rated driver should become busy");
    require(request(user(), 10, 4.5) == nullptr, "S5: busy high-rated driver must not be assigned");
    require(grader_driver_available(b), "S5: low-rated free driver state should be untouched");
})
CHECK_CASE(S6, {
    Driver* a = driver(1, 4.9); (void)driver(2, 4.2); Driver* c = driver(3, 4.6);
    Ride* occupying = request(user("OccupyingUser"), 10, 4.5);
    require(occupying && grader_ride_driver(occupying) == a, "S6 setup: high-rated driver should become busy");
    Ride* r = request(user(), 10, 4.5);
    require(r && grader_ride_driver(r) == c, "S6: must check availability and minimum rating");
})
CHECK_CASE(C1, {
    Driver* a = driver(1, 4.5); Driver* b = driver(2, 4.5);
    Ride* r1 = request(user(), 3, 4.0); Ride* r2 = request(user(), 12, 4.0);
    require(r1 && r2 && grader_ride_driver(r1) == a && grader_ride_driver(r2) == b, "C1: expected two separate rides");
    require_fare(r1, 140.0, "C1 first ride"); require_fare(r2, 320.0, "C1 second ride");
})
CHECK_CASE(M1, {
    Driver* a = driver(1, 4.5); Ride* r = request(user(), 10, 4.0);
    require(r != nullptr, "M1: request unexpectedly failed"); grader_complete_ride(r);
    require(grader_driver_available(a), "M1: completing ride did not free its driver");
})
CHECK_CASE(M2, {
    Driver* a = driver(1, 4.5); Ride* r = request(user(), 10, 4.0);
    require(r != nullptr, "M2: first request unexpectedly failed"); grader_complete_ride(r);
    Ride* next = request(user(), 5, 4.0);
    require(next && grader_ride_driver(next) == a, "M2: completed driver cannot be booked again");
})
CHECK_CASE(M3, {
    Driver* a = driver(1, 4.5); Driver* b = driver(2, 4.5);
    Ride* r1 = request(user(), 10, 4.0); Ride* r2 = request(user(), 10, 4.0);
    require(r1 && r2 && grader_ride_driver(r1) == a && grader_ride_driver(r2) == b, "M3: expected separate drivers");
    grader_complete_ride(r1);
    require(grader_driver_available(a), "M3: first driver's ride not completed");
    require(!grader_driver_available(b), "M3: second driver should remain unavailable");
})
CHECK_CASE(M4, {
    Driver* a = driver(1, 4.5); Driver* b = driver(2, 4.5);
    Ride* r1 = request(user(), 10, 4.0); Ride* r2 = request(user(), 10, 4.0);
    require(r1 && r2, "M4: expected two rides"); grader_complete_ride(r1); grader_complete_ride(r2);
    require(grader_driver_available(a) && grader_driver_available(b), "M4: both completed drivers should be available");
})
CHECK_CASE(E1, {
    (void)driver(1, 4.1); Driver* b = driver(2, 4.5); (void)driver(3, 4.2); (void)driver(4, 4.3);
    Ride* r = request(user(), 25, 4.24);
    require(r && grader_ride_driver(r) == b, "E1: expected driver with rating 4.5"); require_fare(r, 580.0, "E1");
    grader_complete_ride(r); require(grader_driver_available(b), "E1: completed driver should be available");
})
CHECK_CASE(E2, {
    Driver* a = driver(1, 4.5); Driver* b = driver(2, 4.5);
    Ride* r1 = request(user("U1"), 10, 4.0); Ride* r2 = request(user("U2"), 10, 4.0); Ride* r3 = request(user("U3"), 10, 4.0);
    require(r1 && grader_ride_driver(r1) == a, "E2: first user should get driver 1");
    require(r2 && grader_ride_driver(r2) == b, "E2: second user should get driver 2");
    require(r3 == nullptr, "E2: third request should initially be refused");
    grader_complete_ride(r1); Ride* r4 = request(user("U3"), 10, 4.0);
    require(r4 && grader_ride_driver(r4) == a, "E2: third user should get driver 1 after completion");
})

int main(int argc, char** argv) {
    if (argc != 2) { std::cerr << "Usage: ride_harness TEST_ID\n"; return 64; }
    const std::string id(argv[1]);
    try {
#define DISPATCH_CASE(ID) if (id == #ID) { test_##ID(); std::cout << "__CPP_GRADER_RESULT__:PASS:" #ID "\n"; return 0; }
        DISPATCH_CASE(F1) DISPATCH_CASE(F2) DISPATCH_CASE(F3) DISPATCH_CASE(F4)
        DISPATCH_CASE(Q1) DISPATCH_CASE(Q2) DISPATCH_CASE(Q3) DISPATCH_CASE(Q4) DISPATCH_CASE(Q5) DISPATCH_CASE(Q6)
        DISPATCH_CASE(O1) DISPATCH_CASE(O2) DISPATCH_CASE(O3)
        DISPATCH_CASE(S1) DISPATCH_CASE(S2) DISPATCH_CASE(S3) DISPATCH_CASE(S4) DISPATCH_CASE(S5) DISPATCH_CASE(S6)
        DISPATCH_CASE(C1) DISPATCH_CASE(M1) DISPATCH_CASE(M2) DISPATCH_CASE(M3) DISPATCH_CASE(M4) DISPATCH_CASE(E1) DISPATCH_CASE(E2)
#undef DISPATCH_CASE
        std::cerr << "Unknown test ID: " << id << "\n"; return 64;
    } catch (const std::exception& e) {
        std::cout << "__CPP_GRADER_RESULT__:FAIL:" << id << "\n";
        std::cerr << e.what() << "\n";
        return 1;
    } catch (...) {
        std::cout << "__CPP_GRADER_RESULT__:FAIL:" << id << "\n";
        std::cerr << "unknown exception\n";
        return 1;
    }
}
