add_executable(simulation_tests
  SceneModelTest.cpp)
target_link_libraries(simulation_tests
  PRIVATE
    simulation_core
    Corrade::TestSuite)
add_test(NAME simulation_tests COMMAND simulation_tests)
