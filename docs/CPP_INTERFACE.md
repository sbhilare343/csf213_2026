# C++ Adapter and Submission Interface

The provided submission export contains both Java and C++ bundles. I inspected multiple C++ default branches; they share the reference-based API summarized below. The included adapter matches that API, but the instructor should still compare it with the official C++ starter/reference implementation before assigning marks. An adapter mismatch can make a correct submission fail to compile.

## Observed header-based API

The common C++ API uses references for arguments and `Ride::getDriver()`:

```cpp
User user("U");
Driver driver("D1", 4.5);
Ride ride(user, 5, driver);
double fare = ride.calculateFare();
Driver& rideDriver = ride.getDriver();
bool available = driver.isAvailable();
driver.setAvailability(false);
RideService::addDriver(driver);
Ride* requested = RideService::requestRide(user, 10, 4.0);
if (requested != nullptr) RideService::completeRide(*requested);
```

The observed service also declares `static void clearDrivers()`. The grader does not depend on that helper because each testcase is run in a fresh process, so the static registry starts empty.

## Adapter wrapper names

Keep these wrapper names unchanged because the harness depends on them:

- `grader_make_user(name)`
- `grader_make_driver(name, rating)`
- `grader_make_ride(user, distance, driver)`
- `grader_clear_drivers()` (no-op; each testcase process is fresh)
- `grader_add_driver(driver)`
- `grader_request_ride(user, distance, min_rating)`
- `grader_complete_ride(ride)`
- `grader_ride_driver(ride)`
- `grader_ride_fare(ride)`
- `grader_driver_available(driver)`

Edit `config/ride_api_adapter.hpp` for header-based projects or `config/ride_api_adapter_monolithic.hpp` for a single-file solution. Wrappers bridge the harness's pointer-owned test objects to student methods that take references. Do not change the official behavior or test-case marks to make an implementation pass.

## Header mode and monolithic mode

`harness.source_mode: auto` chooses header mode when the four configured headers are present; when exactly one C++ source file exists and those headers are absent, it includes that source file into the generated harness after temporarily renaming `main`. In header mode, the grader omits `main.cpp` and common test-directory/test-name sources from the link, because the harness supplies its own `main` and unit tests. Set `headers` or `monolithic` explicitly when auto-detection is not appropriate. Multi-file projects should expose class declarations in headers or use a custom adapter.

## Known limitations

Projects with namespaces, different constructor signatures, non-static service methods, or a custom build system may require adapter changes. The importer grades the source checkout on the bundle's default/HEAD branch and does not preserve Git history. The C++ automated tests cover the 60 functional marks only; use the original bundles separately for commit-history/Git-usage review and handle Java submissions with the Java grader. If the instructor-controlled reference solution does not compile with the adapter, do not use the grader to assign real marks.
