set(CMAKE_MODULE_PATH
  "${PROJECT_SOURCE_DIR}/third_party/corrade/modules"
  "${PROJECT_SOURCE_DIR}/third_party/magnum/modules"
  "${PROJECT_SOURCE_DIR}/third_party/magnum-integration/modules"
  ${CMAKE_MODULE_PATH})

set(SDL_ATOMIC OFF CACHE BOOL "" FORCE)
set(SDL_AUDIO OFF CACHE BOOL "" FORCE)
set(SDL_CPUINFO OFF CACHE BOOL "" FORCE)
set(SDL_FILE OFF CACHE BOOL "" FORCE)
set(SDL_FILESYSTEM OFF CACHE BOOL "" FORCE)
set(SDL_HAPTIC OFF CACHE BOOL "" FORCE)
set(SDL_LOCALE OFF CACHE BOOL "" FORCE)
set(SDL_POWER OFF CACHE BOOL "" FORCE)
set(SDL_RENDER OFF CACHE BOOL "" FORCE)
set(SDL_SENSOR OFF CACHE BOOL "" FORCE)
set(SDL_SHARED OFF CACHE BOOL "" FORCE)
set(SDL_STATIC ON CACHE BOOL "" FORCE)

set(CORRADE_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(CORRADE_WITH_INTERCONNECT OFF CACHE BOOL "" FORCE)
set(CORRADE_WITH_PLUGINMANAGER ON CACHE BOOL "" FORCE)
set(CORRADE_WITH_UTILITY ON CACHE BOOL "" FORCE)
set(CORRADE_WITH_TESTSUITE ON CACHE BOOL "" FORCE)

set(MAGNUM_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(MAGNUM_BUILD_GL_TESTS OFF CACHE BOOL "" FORCE)
set(MAGNUM_BUILD_STATIC ON CACHE BOOL "" FORCE)
set(MAGNUM_WITH_GL ON CACHE BOOL "" FORCE)
set(MAGNUM_WITH_DEBUGTOOLS ON CACHE BOOL "" FORCE)
set(MAGNUM_WITH_MESHTOOLS ON CACHE BOOL "" FORCE)
set(MAGNUM_WITH_PRIMITIVES ON CACHE BOOL "" FORCE)
set(MAGNUM_WITH_SCENEGRAPH ON CACHE BOOL "" FORCE)
set(MAGNUM_WITH_SHADERS ON CACHE BOOL "" FORCE)
set(MAGNUM_WITH_SDL2APPLICATION ON CACHE BOOL "" FORCE)

set(MAGNUM_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(MAGNUM_BUILD_GL_TESTS OFF CACHE BOOL "" FORCE)
set(MAGNUM_BUILD_STATIC ON CACHE BOOL "" FORCE)
set(MAGNUM_WITH_IMGUIINTEGRATION ON CACHE BOOL "" FORCE)
set(IMGUI_DIR "${PROJECT_SOURCE_DIR}/third_party/imgui" CACHE PATH "" FORCE)

add_subdirectory("${PROJECT_SOURCE_DIR}/third_party/SDL" "${PROJECT_BINARY_DIR}/third_party/SDL" EXCLUDE_FROM_ALL)
add_subdirectory("${PROJECT_SOURCE_DIR}/third_party/corrade" "${PROJECT_BINARY_DIR}/third_party/corrade" EXCLUDE_FROM_ALL)
add_subdirectory("${PROJECT_SOURCE_DIR}/third_party/magnum" "${PROJECT_BINARY_DIR}/third_party/magnum" EXCLUDE_FROM_ALL)
add_subdirectory("${PROJECT_SOURCE_DIR}/third_party/magnum-integration" "${PROJECT_BINARY_DIR}/third_party/magnum-integration" EXCLUDE_FROM_ALL)

add_library(ImGuizmo STATIC "${PROJECT_SOURCE_DIR}/third_party/ImGuizmo/ImGuizmo.cpp")
target_include_directories(ImGuizmo PUBLIC
  "${PROJECT_SOURCE_DIR}/third_party/ImGuizmo"
  "${PROJECT_SOURCE_DIR}/third_party/imgui"
  "${PROJECT_SOURCE_DIR}/third_party/magnum-integration/src"
  "${PROJECT_SOURCE_DIR}/third_party/corrade/src"
  "${PROJECT_BINARY_DIR}/third_party/corrade/src"
  "${PROJECT_BINARY_DIR}/third_party/magnum-integration/src")
target_compile_definitions(ImGuizmo
  PUBLIC IMGUI_DEFINE_MATH_OPERATORS
  PRIVATE IMGUI_USER_CONFIG=\"Magnum/ImGuiIntegration/visibility.h\")

add_library(simulation_core
  editor/ArcBall.cpp
  editor/EditorApplication.cpp
  editor/Persistence.cpp
  editor/SceneModel.cpp
  editor/ViewportRenderer.cpp)
target_include_directories(simulation_core PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}")
target_link_libraries(simulation_core
  PUBLIC
    Corrade::Utility
    Magnum::DebugTools
    Magnum::GL
    Magnum::MeshTools
    Magnum::Primitives
    Magnum::SceneGraph
    Magnum::Shaders
    Magnum::Sdl2Application
    MagnumIntegration::ImGui
    ImGuizmo)

add_executable(hexapod-simulation main.cpp)
target_link_libraries(hexapod-simulation PRIVATE simulation_core)
