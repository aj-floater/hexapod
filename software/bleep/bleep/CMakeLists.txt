# Set the path to your models directory
set(MODELS_DIR "${CMAKE_CURRENT_SOURCE_DIR}/models")

# Copy the contents of the models directory to the build directory during build
file(COPY ${MODELS_DIR} DESTINATION ${CMAKE_BINARY_DIR})

include_directories(include)

add_subdirectory(src)
