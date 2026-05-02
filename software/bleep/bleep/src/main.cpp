#include <Magnum/GL/DefaultFramebuffer.h>
#include <Magnum/GL/Renderer.h>
#include <Magnum/ImGuiIntegration/Context.hpp>

#include <Magnum/Platform/Sdl2Application.h>
#include <Magnum/SceneGraph/Scene.h>
#include <Magnum/SceneGraph/TranslationRotationScalingTransformation3D.h>
#include <Magnum/SceneGraph/AbstractTranslationRotationScaling3D.h>
#include <Magnum/SceneGraph/Camera.h>
#include <Magnum/SceneGraph/Drawable.h>

#include <Magnum/Primitives/Cube.h>
#include <Magnum/Primitives/Grid.h>
#include <Magnum/MeshTools/Compile.h>
#include <Magnum/Shaders/PhongGL.h>
#include <Magnum/Math/Color.h>
#include <Magnum/GL/Mesh.h>
#include <Magnum/Trade/MeshData.h>

#include "ArcBall.h"
#include "ArcBallCamera.h"

#include "controller.h"
#include "cubeDrawable.h"
#include "meshDrawable.h"

float _stepTime = 0.3f;
float _stepSize = 0.4f;
float _stepHeight = 0.3f;

#include "graphicsBody.h"

#include "MacSerialPort/SerialPort/SerialPort.hpp"
#include "MacSerialPort/TypeAbbreviations/TypeAbbreviations.hpp"

using namespace Magnum;
using namespace Math::Literals;

typedef SceneGraph::Object<SceneGraph::TranslationRotationScalingTransformation3D> Object3D;
typedef SceneGraph::Scene<SceneGraph::TranslationRotationScalingTransformation3D> Scene3D;
class GridDrawable: public SceneGraph::Drawable3D {
  public:
    explicit GridDrawable(Object3D& object, SceneGraph::DrawableGroup3D* group, int subdivisions, Color3 color):
      SceneGraph::Drawable3D{object, group},
      _color(color)
    {
      _mesh = MeshTools::compile(Primitives::grid3DWireframe(Vector2i(subdivisions)));
    }

  private:
    void draw(const Matrix4& transformationMatrix, SceneGraph::Camera3D& camera) override {
      using namespace Math::Literals;

      _shader.setAmbientColor(_color)
        .setTransformationMatrix(transformationMatrix)
        .setNormalMatrix(transformationMatrix.normalMatrix())
        .setProjectionMatrix(camera.projectionMatrix())
        .draw(_mesh);
    }

    GL::Mesh _mesh;
    Shaders::PhongGL _shader;
    Color3 _color;
};

Object3D* grid;

Color3 color;

SceneGraph::DrawableGroup3D _drawables;
Scene3D _scene;

bool playing = false;

class MyApplication: public Platform::Application {
public:
  explicit MyApplication(const Arguments& arguments);

  void viewportEvent(ViewportEvent& event) override;

  void anyEvent(SDL_Event& event) override;

  void keyPressEvent(KeyEvent& event) override;
  void keyReleaseEvent(KeyEvent& event) override;

  void mousePressEvent(MouseEvent& event) override;
  void mouseReleaseEvent(MouseEvent& event) override;
  void mouseMoveEvent(MouseMoveEvent& event) override;
  void mouseScrollEvent(MouseScrollEvent& event) override;
  void textInputEvent(TextInputEvent& event) override;

  Timeline _timeline;

private:
  ImGuiIntegration::Context _imgui{NoCreate};

  void renderGUI();
  void drawEvent() override;
  

  Vector2i _lastPosition;

  Containers::Optional<ArcBallCamera> _arcballCamera;
  GraphicsLeg* debuggingLeg;
  GraphicsBody* body;
  Cube* cube;
  Controller* controller;
};

MyApplication::MyApplication(const Arguments& arguments):
  Platform::Application{arguments, Configuration{}
    .setTitle("Bleep")
    .setWindowFlags(Configuration::WindowFlag::Resizable)}
{
  using namespace Math::Literals;
  init_gamepad();
  controller->init();

  _imgui = ImGuiIntegration::Context(Vector2{windowSize()}/dpiScaling(), windowSize(), framebufferSize());

  ImGuiIO &io = ImGui::GetIO();
  io.IniFilename = "/Users/archiejames/coding/bleep-prime/imgui.ini";

  GL::Renderer::enable(GL::Renderer::Feature::DepthTest);
  GL::Renderer::setBlendEquation(GL::Renderer::BlendEquation::Add,
    GL::Renderer::BlendEquation::Add);
  GL::Renderer::setBlendFunction(GL::Renderer::BlendFunction::SourceAlpha,
    GL::Renderer::BlendFunction::OneMinusSourceAlpha);

  /* Configure camera */
  {
    /* Setup the arcball after the camera objects */
    const Vector3 eye = Vector3::zAxis(-10.0f);
    const Vector3 center{};
    const Vector3 up = Vector3::yAxis();
    _arcballCamera.emplace(_scene, eye, center, up, 45.0_degf,
      windowSize(), framebufferSize());
  }

  /* TODO: Prepare your objects here and add them to the scene */
  grid = new Object3D{&_scene};
  (*grid)
    // .translate(Vector3::yAxis(-0.3f))
    .rotateX(90.0_degf)
    .translate(Vector3(0.5f, 0.0f, 0.5f))
    .scale(Vector3(20.0f));
  new GridDrawable{*grid, &_drawables, 40, Color3(0.3f, 0.3f, 0.3f)};

  controller = new Controller();

  debuggingLeg = new GraphicsLeg(Vector3(0.75f));
  debuggingLeg->showDebuggingWindow = true;
  debuggingLeg->showMeshes = true;
  debuggingLeg->_position = Vector3(5.0f, 0.0f, 0.0f);
  debuggingLeg->_finalAnimationPose = Vector3(6.5f, 0.0f, 0.8f);
  debuggingLeg->_endPose = Vector3(7.0f, 0.0f, 0.0f);

  body = new GraphicsBody(Color3(0.75f, 0.75f, 0.75f));

  body->controllerPointer = controller;

  setMinimalLoopPeriod(16);

  _timeline.start();
}

bool showLegInfoWindow = false; // A flag to track whether to show the leg info window or not

std::vector<std::string> ports;
std::string selectedPort;
int selectedBaudRate = 9600;

// Define some constants
constexpr size_t MAX_DATA_LENGTH = 256;

// Variables to store user input and received data
char sendBuffer[MAX_DATA_LENGTH] = "";
char receiveBuffer[MAX_DATA_LENGTH] = "";

bool sendSimData = false;

// Function to send data over serial
static void sendData() {
    size_t length = strlen(sendBuffer);
    ssize_t bytesSent = writeSerialData(sendBuffer, length);
    if (bytesSent != static_cast<ssize_t>(length)) {
        // Handle error
    }
}

std::string out = "<0:0:0:0:0:0:0:0:0:0:0:0:0:0:0:0:0:0>";
void updateStringFromValues(int values[]) {
    out = "<";
    for (int i = 0; i < 18; ++i) {
        out += std::to_string(values[i]);
        if (i < 17) {
            out += ":";
        }
    }
    out += ">\n";
}

int values[18];

std::string receivedData;
bool serialConnected = false;

void MyApplication::renderGUI() {
  _imgui.newFrame();

  /* Enable text input, if needed */
  if(ImGui::GetIO().WantTextInput && !isTextInputActive())
      startTextInput();
  else if(!ImGui::GetIO().WantTextInput && isTextInputActive())
      stopTextInput();

  
  // ImGui::ShowDemoWindow();

  // ImGuiIO& io = ImGui::GetIO();
  if(ImGui::BeginMainMenuBar()){
    if(ImGui::BeginMenu("Scene Debugging")){
      ImGui::SeparatorText("Grid");
      {
        Float (&translation)[3] = grid->translation().data();
        if (ImGui::DragFloat3("Grid Translation", translation, 0.1f)){
          grid->setTranslation(Vector3::from(translation));
        };
      }
      ImGui::SeparatorText("Debugging Leg");
      if (ImGui::RadioButton("Show leg", debuggingLeg->showDebuggingWindow))
        debuggingLeg->showDebuggingWindow = !debuggingLeg->showDebuggingWindow;

      ImGui::EndMenu();
    }

    // debuggingLeg->showDebugging();

    body->showGUI();

    ImGui::EndMainMenuBar();
  }

  { // Leg Debugging
    ImGui::Begin("Leg Debugging");
    
    float desiredpose[3] = {
    debuggingLeg->_finalAnimationPose.x(),
    debuggingLeg->_finalAnimationPose.y(),
    debuggingLeg->_finalAnimationPose.z()
    };
    if (ImGui::DragFloat3("Position", desiredpose, 0.01f)){
      debuggingLeg->_finalAnimationPose = Vector3(
        desiredpose[0],
        desiredpose[1],
        desiredpose[2]
      );
    }

    if (ImGui::Button("Play")){
      debuggingLeg->NewAnimation(Vector3(desiredpose[0], desiredpose[1], desiredpose[2]));
    };

    ImGui::End();
  }

  {
    // Begin Serial Control
    ImGui::Begin("Serial Control");

    if (ImGui::Button("Refresh")) {
      // Handle refresh button click action here
      ports = parseSerialPorts(getSerialPorts());
    }
    // Dropdown menu for selecting baud rates
    ImGui::SameLine(); // Ensure the dropdown is on the same line

    const char* baudRates[] = { "9600", "19200", "38400", "57600", "115200" };
    static int selectedBaudRateIndex = 0; // Index of the selected baud rate
    if (ImGui::BeginCombo("##baudrate", baudRates[selectedBaudRateIndex])) // ## is an identifier with no label and no display
    {
        for (int i = 0; i < IM_ARRAYSIZE(baudRates); i++)
        {
            bool isSelected = (selectedBaudRateIndex == i);
            if (ImGui::Selectable(baudRates[i], isSelected))
            {
                selectedBaudRateIndex = i;
                selectedBaudRate = std::stoi(std::string(baudRates[i])); // Set the selected baud rate as a string
            }

            // Set the initial focus when opening the combo (scrolling + keyboard navigation focus)
            if (isSelected)
                ImGui::SetItemDefaultFocus();
        }
        ImGui::EndCombo();
    }

    // Calculate the desired height for the port buttons section
    const float maxHeight = ImGui::GetTextLineHeightWithSpacing() * 5;

    ImGui::BeginChild("PortButtons", ImVec2(0, maxHeight), true);

    static int selected = -1;
    int n = 0;
    for (const auto& port : ports) {
      n++;
      char buf[32];
      sprintf(buf, port.c_str());
      if (ImGui::Selectable(buf, selected == n)){
        selected = n;
        selectedPort = port;
      }
    }

    ImGui::EndChild();

    ImGui::SetNextItemWidth(ImGui::GetContentRegionAvail().x);
    if (ImGui::Button("Connect")) 
    {
        //* Open port, and connect to a device
      std::string devicePathStr = "/dev/tty." + selectedPort;
      const char* devicePath = devicePathStr.c_str();
      const int baudRate = selectedBaudRate;
      int sfd = openAndConfigureSerialPort(devicePath, baudRate);
      if (sfd < 0) {
        if (sfd == -1) {
            printf("Unable to connect to serial port.\n");
        }
        else { //sfd == -2
            printf("Error setting serial port attributes.\n");
        }
        serialConnected = false;
      }
      else {
        serialConnected = true;
      }
    }
    // Right column: Text
    ImGui::SameLine(); // Move to the next column
    ImGui::Text("%s", selectedPort.c_str()); // Display your text here
    ImGui::SameLine(); // Move to the next column
    ImGui::Text("%i", selectedBaudRate); // Display your text here

    ImGui::BeginChild("ScrollingRegion", ImVec2(0, 100), true, ImGuiWindowFlags_AlwaysHorizontalScrollbar | ImGuiWindowFlags_AlwaysVerticalScrollbar);
    ImGui::Text("%s", receivedData.c_str());
    ImGui::EndChild();

    ImGui::InputText("##Input", sendBuffer, 256);
    ImGui::SameLine();
    // Check if there's enough space to add a newline character
    if (ImGui::Button(">>")) {
      // Assuming sendBuffer is defined as const char[256]
      // Copy contents of sendBuffer to modifiableBuffer
      // Get the length of the current contents in modifiableBuffer
      char modifiableBuffer[256]; // Create a modifiable buffer
      strcpy(modifiableBuffer, sendBuffer);
      size_t currentLength = strlen(modifiableBuffer);

      if (currentLength < sizeof(modifiableBuffer) - 1) {
          // Add the newline character
          modifiableBuffer[currentLength] = '\n';
          modifiableBuffer[currentLength + 1] = '\0'; // Null-terminate the string
          Debug{} << modifiableBuffer; // Print or debug as needed
          writeSerialData(modifiableBuffer, strlen(modifiableBuffer)); // Send the data
      }
      else {
        Debug{} << "too big";
      }
    }

    //
    if(ImGui::RadioButton("Send Sim Data", sendSimData)){
      sendSimData=!sendSimData;
    }

    ImGui::End();

    ImGui::Begin("Number Input Fields");
    for (int i = 0; i < 18; ++i) {
        if (ImGui::DragInt((std::to_string(i)).c_str(), &values[i])){
          updateStringFromValues(values);
        }
    }
    ImGui::Text("String: %s", out.c_str());
    ImGui::End();
  }

  controller->showGUI();

  /* Update application cursor */
  _imgui.updateApplicationCursor(*this);

  /* Set appropriate states. If you only draw ImGui, it is sufficient to
      just enable blending and scissor debuggingLeg in the constructor. */
  GL::Renderer::enable(GL::Renderer::Feature::Blending);
  GL::Renderer::enable(GL::Renderer::Feature::ScissorTest);
  GL::Renderer::disable(GL::Renderer::Feature::FaceCulling);
  GL::Renderer::disable(GL::Renderer::Feature::DepthTest);

  _imgui.drawFrame();

  /* Reset state. Only needed if you want to draw something else with
      different state after. */
  GL::Renderer::enable(GL::Renderer::Feature::DepthTest);
  GL::Renderer::enable(GL::Renderer::Feature::FaceCulling);
  GL::Renderer::disable(GL::Renderer::Feature::ScissorTest);
  GL::Renderer::disable(GL::Renderer::Feature::Blending);
}

static SDL_GameController *findController() {
    for (int i = 0; i < SDL_NumJoysticks(); i++) {
        if (SDL_IsGameController(i)) {
            return SDL_GameControllerOpen(i);
        }
    }

    return nullptr;
}

SDL_GameController *ps3controller;

double timeSinceLastSend;

void MyApplication::drawEvent() {
  GL::defaultFramebuffer.clear(GL::FramebufferClear::Color|GL::FramebufferClear::Depth);

  controller->update();

  // debuggingLeg->NewAnimation();
  float deltaTime = _timeline.currentFrameDuration();
 
  debuggingLeg->update(deltaTime);

  body->update(deltaTime);

  _arcballCamera->update();
    _arcballCamera->draw(_drawables);

  renderGUI();

  ps3controller = findController();

  if (SDL_GameControllerGetButton(ps3controller, SDL_GameControllerButton::SDL_CONTROLLER_BUTTON_DPAD_UP)) {
    if (body->_position.y() < 1.5f){
      body->_position += Vector3(0, deltaTime * 2.0f, 0);
    }
  }
  if (SDL_GameControllerGetButton(ps3controller, SDL_GameControllerButton::SDL_CONTROLLER_BUTTON_DPAD_DOWN)) {
    if (body->_position.y() > 0.25f){
      body->_position -= Vector3(0, deltaTime * 2.0f, 0);
    }
  }

  body->getAllJointAngles();
  out = body->intArrayToString(body->jointAngles, 18);

  // updateStringFromValues(values);
  // Debug{} << out.c_str();

  // Debug{} << deltaTime;
  if (serialConnected){
    if (sendSimData){
      if (timeSinceLastSend >= 0.05){
        // writeSerialData(out.c_str(), strlen(out.c_str()));
        // Debug{} << out.c_str();
        writeSerialData(out.c_str(), strlen(out.c_str()));
        
        timeSinceLastSend = 0;
      }
      else {
        timeSinceLastSend += deltaTime;
      }
      // std::string height = std::to_string(body->_position.y()) + "\n";
      // writeSerialData(height.c_str(), strlen(height.c_str()));
    }

    char readBuffer[256]; // Create a modifiable buffer
    if (readSerialData(readBuffer, 256) != -1){
      // Find the position of newline terminator in readBuffer
      char* nlTerminatorPos = strchr(readBuffer, '\n');
      if (nlTerminatorPos != nullptr) {
          // Calculate the length of characters up to newline terminator
          // size_t charsToAdd = nlTerminatorPos - readBuffer + 1; // Add 1 to include newline character

          // Append characters up to newline terminator to receivedDat
          // receivedData.append(readBuffer, charsToAdd);
          receivedData += readBuffer;
          // Debug{} << receivedData;
      }
    }
  }

  swapBuffers();
  redraw();
  _timeline.nextFrame();
}

void MyApplication::viewportEvent(ViewportEvent& event) {
  GL::defaultFramebuffer.setViewport({{}, event.framebufferSize()});

  _arcballCamera->reshape(event.windowSize(), event.framebufferSize());

  _imgui.relayout(Vector2{event.windowSize()}/event.dpiScaling(),
      event.windowSize(), event.framebufferSize());
}

void MyApplication::keyPressEvent(KeyEvent& event) {
    if (_imgui.handleKeyPressEvent(event))
        return;

    switch (event.key()) {
        case KeyEvent::Key::W:
            controller->leftMovement.y() = -1.0f;
            break;
        case KeyEvent::Key::S:
            controller->leftMovement.y() = 1.0f;
            break;
        case KeyEvent::Key::A:
            controller->leftMovement.x() = -1.0f;
            break;
        case KeyEvent::Key::D:
            controller->leftMovement.x() = 1.0f;
            break;
        case KeyEvent::Key::Up:
            controller->rightMovement.y() = -1.0f;
            break;
        case KeyEvent::Key::Down:
            controller->rightMovement.y() = 1.0f;
            break;
        case KeyEvent::Key::Left:
            controller->rightMovement.x() = -1.0f;
            break;
        case KeyEvent::Key::Right:
            controller->rightMovement.x() = 1.0f;
            break;
        default:
            break;
    }
}

float value;

void MyApplication::anyEvent(SDL_Event& event) {
  // Debug{} << event.type;
  switch(event.type)
  {  
    case SDL_CONTROLLERDEVICEADDED:
      if (!ps3controller) {
          ps3controller = SDL_GameControllerOpen(event.cdevice.which);
      }
      break;
    case SDL_CONTROLLERDEVICEREMOVED:
      if (ps3controller && event.cdevice.which == SDL_JoystickInstanceID(
              SDL_GameControllerGetJoystick(ps3controller))) {
          SDL_GameControllerClose(ps3controller);
          ps3controller = findController();
      }
      break;
    case SDL_JOYAXISMOTION:  /* Handle Joystick Motion */
      value = event.jaxis.value;
      switch (event.jaxis.axis){
        case SDL_CONTROLLER_AXIS_LEFTX:
          controller->leftJoystick.x() = value / 32767.0f;
          break;
        case SDL_CONTROLLER_AXIS_LEFTY:
          controller->leftJoystick.y() = value / 32767.0f;
          break;
        case SDL_CONTROLLER_AXIS_RIGHTX:
          controller->rightJoystick.x() = value / 32767.0f;
          break;
        case SDL_CONTROLLER_AXIS_RIGHTY:
          controller->rightJoystick.y() = value / 32767.0f;
          break;
        case SDL_CONTROLLER_AXIS_TRIGGERLEFT:
          _stepTime = 0.5f - (value / 32767.0f + 1) * 0.1;
          break;
        case SDL_CONTROLLER_AXIS_TRIGGERRIGHT:
          _stepSize = 0.4f + (value / 32767.0f + 1) * 0.2f;
          break;
      }
      break;
    case 1540:
      switch (event.cbutton.button) {
      case SDL_GameControllerButton::SDL_CONTROLLER_BUTTON_X:
          // std::cerr << "X pressed!" << std::endl;
          body->mode = WALKING;
          break;
      case SDL_GameControllerButton::SDL_CONTROLLER_BUTTON_B:
          // std::cerr << "B pressed!" << std::endl;
          body->mode = STANDING;
          body->defaultPosition = body->_position;
          body->defaultRotation = body->_rotation;
          break;
      }
      break;
    // default:
    //   Debug{} << event.type;
    //   break;
  }
}

void MyApplication::keyReleaseEvent(KeyEvent& event) {
    if (_imgui.handleKeyReleaseEvent(event))
        return;

    switch (event.key()) {
        case KeyEvent::Key::W:
        case KeyEvent::Key::S:
            controller->leftMovement.y() = 0.0f;
            break;
        case KeyEvent::Key::A:
        case KeyEvent::Key::D:
            controller->leftMovement.x() = 0.0f;
            break;
        case KeyEvent::Key::Up:
        case KeyEvent::Key::Down:
            controller->rightMovement.y() = 0.0f;
            break;
        case KeyEvent::Key::Left:
        case KeyEvent::Key::Right:
            controller->rightMovement.x() = 0.0f;
            break;
        default:
            break;
    }
}

void MyApplication::mousePressEvent(MouseEvent& event) {
    if (_imgui.handleMousePressEvent(event)) return;
    /* Enable mouse capture so the mouse can drag outside of the window */
    /** @todo replace once https://github.com/mosra/magnum/pull/419 is in */
    SDL_CaptureMouse(SDL_TRUE);

    _arcballCamera->initTransformation(event.position());

    event.setAccepted();
    redraw(); /* camera has changed, redraw! */
}

void MyApplication::mouseReleaseEvent(MouseEvent& event) {
    if (_imgui.handleMouseReleaseEvent(event)) return;
    /* Disable mouse capture again */
    /** @todo replace once https://github.com/mosra/magnum/pull/419 is in */

    SDL_CaptureMouse(SDL_FALSE);
}

void MyApplication::mouseMoveEvent(MouseMoveEvent& event) {
    if (_imgui.handleMouseMoveEvent(event)) return;

    if(!event.buttons()) return;

    if (event.buttons() == MouseMoveEvent::Button::Right) {
        _arcballCamera->translate(event.position());
    } else if (event.modifiers() & MouseMoveEvent::Modifier::Shift) {
        _arcballCamera->translate(event.position());
    } else {
        _arcballCamera->rotate(event.position());
    }

    event.setAccepted();
    redraw(); /* camera has changed, redraw! */
}

void MyApplication::mouseScrollEvent(MouseScrollEvent& event) {
    if (_imgui.handleMouseScrollEvent(event)) return;

    const Float delta = event.offset().y();
    if(Math::abs(delta) < 1.0e-2f) return;

    _arcballCamera->zoom(delta);

    event.setAccepted();
    redraw(); /* camera has changed, redraw! */
}

void MyApplication::textInputEvent(TextInputEvent& event) {
    if(_imgui.handleTextInputEvent(event)) return;
}

MAGNUM_APPLICATION_MAIN(MyApplication)