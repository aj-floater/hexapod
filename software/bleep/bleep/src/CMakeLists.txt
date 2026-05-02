set(CMAKE_MODULE_PATH "${PROJECT_SOURCE_DIR}/magnum/modules/" ${CMAKE_MODULE_PATH})
set(CMAKE_MODULE_PATH "${PROJECT_SOURCE_DIR}/magnum-integration/modules/" ${CMAKE_MODULE_PATH})

find_package(Corrade REQUIRED Main)
find_package(Magnum REQUIRED
    GL
    MeshTools
    Primitives
    SceneGraph
    Shaders
    Trade
    Sdl2Application)
find_package(MagnumIntegration REQUIRED ImGui)

find_package(MagnumPlugins REQUIRED AssimpImporter)

set_directory_properties(PROPERTIES CORRADE_USE_PEDANTIC_FLAGS ON)

add_executable(bleep

ArcBall.cpp
main.cpp
../include/MacSerialPort/SerialPort/SerialPort.cpp
    )


add_dependencies(bleep
    Magnum::AnyImageImporter
    Magnum::AnySceneImporter
    MagnumPlugins::AssimpImporter)

if(APPLE)
    find_library(CoreFoundation CoreFoundation)
    find_library(IOKit IOKit)
    target_link_libraries(bleep PRIVATE 
        "-framework CoreFoundation -framework IOKit"
        Corrade::Main
        Magnum::Application
        Magnum::GL
        Magnum::Magnum
        Magnum::MeshTools
        Magnum::Primitives
        Magnum::SceneGraph
        Magnum::Shaders
        Magnum::Trade
        MagnumIntegration::ImGui
        )
elseif()
    target_link_libraries(bleep PRIVATE 
        Corrade::Main
        Magnum::Application
        Magnum::GL
        Magnum::Magnum
        Magnum::MeshTools
        Magnum::Primitives
        Magnum::SceneGraph
        Magnum::Shaders
        Magnum::Trade
        MagnumIntegration::ImGui
    )
endif()

if(CORRADE_TARGET_APPLE)
    set_target_properties(bleep PROPERTIES
        MACOSX_BUNDLE ON
        MACOSX_BUNDLE_BUNDLE_NAME "My Application"
        MACOSX_BUNDLE_BUNDLE_IDENTIFIER "cz.mosra.magnum.my-application")
endif()

install(TARGETS bleep DESTINATION ${MAGNUM_BINARY_INSTALL_DIR})

target_compile_definitions(bleep PRIVATE -DMODELS_DIR="${MODELS_DIR}")