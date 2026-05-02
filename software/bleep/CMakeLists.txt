cmake_minimum_required(VERSION 3.5)
project(MyApplication)

set(CMAKE_C_FLAGS_DEBUG "-g -DDEBUG")
set(CMAKE_CXX_FLAGS_DEBUG "-g -DDEBUG")
set(CMAKE_MODULE_PATH "${PROJECT_SOURCE_DIR}/modules/" ${CMAKE_MODULE_PATH})

# Add Corrade as a subproject
add_subdirectory(corrade EXCLUDE_FROM_ALL)

# Add Magnum as a subproject, enable Sdl2Application
if (WIN32)
    set(CMAKE_PREFIX_PATH ${PROJECT_SOURCE_DIR}/SDL2-2.0.10 ${CMAKE_PREFIX_PATH})
endif()
set(MAGNUM_WITH_SDL2APPLICATION ON CACHE BOOL "" FORCE)
set(MAGNUM_WITH_ANYIMAGEIMPORTER ON CACHE BOOL "" FORCE)
set(MAGNUM_WITH_ANYSCENEIMPORTER ON CACHE BOOL "" FORCE)
add_subdirectory(magnum EXCLUDE_FROM_ALL)

# Disable Assimp tests, tools and exporter functionality
set(ASSIMP_BUILD_ASSIMP_TOOLS OFF CACHE BOOL "" FORCE)
set(ASSIMP_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(ASSIMP_NO_EXPORT ON CACHE BOOL "" FORCE)
# If you won't be accessing Assimp outside of the plugin, build it as static to
# have the plugin binary self-contained
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
# The following is important to avoid Assimp appending `d` to all your
# binaries. You need Assimp >= 5.0.0 for this to work, also note that after
# 5.0.1 this option is prefixed with ASSIMP_, so better set both variants.
set(INJECT_DEBUG_POSTFIX OFF CACHE BOOL "" FORCE)
set(ASSIMP_INJECT_DEBUG_POSTFIX OFF CACHE BOOL "" FORCE)
add_subdirectory(assimp EXCLUDE_FROM_ALL)

set(MAGNUM_WITH_ASSIMPIMPORTER ON CACHE BOOL "" FORCE)
add_subdirectory(magnum-plugins EXCLUDE_FROM_ALL)

# Add Magnum integration as a subproject, enable Sdl2Application
set(IMGUI_DIR ${CMAKE_CURRENT_SOURCE_DIR}/imgui)
set(MAGNUM_WITH_IMGUI ON CACHE BOOL "" FORCE)
add_subdirectory(magnum-integration EXCLUDE_FROM_ALL)

add_subdirectory(bleep)