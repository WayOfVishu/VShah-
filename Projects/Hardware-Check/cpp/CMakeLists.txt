# Build system for libsysdiag / the sysdiag_engine binary.
#
# This file is written out in full — CMake syntax itself isn't the point of
# this project (Instructions.md/project-charter.md Section 2 never lists it
# as a learning objective), and getting FetchContent + sanitizer flags right
# from scratch with zero prior CMake exposure would eat time that belongs to
# the actual C++ memory-management work. Read through it once so you're not
# flying blind, but you're not expected to have derived it yourself.
#
# Build (from the hardware-check/ repo root, inside WSL2 — see
# docs/project-charter.md Section 5 for why WSL2):
#
#   cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Debug
#   cmake --build cpp/build
#
# With sanitizers on (do this constantly while building the memory sandbox,
# not just once at the end — project-charter.md Section 10 risk table):
#
#   cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Debug -DENABLE_ASAN=ON
#   cmake --build cpp/build
#   ./cpp/build/sysdiag_engine
#
# Valgrind runs against any build (ASan and Valgrind can conflict if both
# active at once — use one or the other per run, not simultaneously):
#
#   valgrind --leak-check=full ./cpp/build/sysdiag_engine

cmake_minimum_required(VERSION 3.20)
project(sysdiag LANGUAGES CXX)

# C++20, per project decision (2026-08-25) — see project-charter.md Section 7.
# Locked in over C++17 as too old for a project starting in 2026, and over
# C++23 as a deliberate "not yet" — the plan is to land a working v1 on 20,
# then evaluate a 23 upgrade after the beta-testing phase (weeks 7-8), once
# there's a working baseline to diff against rather than a moving target.
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Debug)
endif()

# AddressSanitizer toggle. Off by default (it has real runtime overhead);
# turn it on while you're actively working on memory_sandbox.cpp.
option(ENABLE_ASAN "Build with AddressSanitizer + UndefinedBehaviorSanitizer" OFF)
if(ENABLE_ASAN)
  add_compile_options(-fsanitize=address,undefined -fno-omit-frame-pointer -g)
  add_link_options(-fsanitize=address,undefined)
endif()

add_compile_options(-Wall -Wextra)

# --- third-party: nlohmann/json (header-only, MIT license, $0 — BOM Section 9) ---
# Fetched at configure time rather than vendored, so the repo doesn't carry a
# ~25k-line header it didn't write. Pinned to a specific tag for reproducible
# builds (a moving "main" branch dependency is its own kind of bug).
include(FetchContent)
FetchContent_Declare(
  json
  GIT_REPOSITORY https://github.com/nlohmann/json.git
  GIT_TAG v3.11.3
)
FetchContent_MakeAvailable(json)

# --- libsysdiag: the actual logic, as a static library ---
# Split from main.cpp so it's independently testable if you add a test
# executable later, and so main.cpp stays a thin CLI wrapper.
add_library(sysdiag_core STATIC
  src/system_info.cpp
  src/memory_sandbox.cpp
  src/telemetry_json.cpp
)
target_include_directories(sysdiag_core PUBLIC include)
target_link_libraries(sysdiag_core PUBLIC nlohmann_json::nlohmann_json)

# --- sysdiag_engine: the CLI binary netdiag.py invokes as a subprocess ---
add_executable(sysdiag_engine src/main.cpp)
target_link_libraries(sysdiag_engine PRIVATE sysdiag_core)
