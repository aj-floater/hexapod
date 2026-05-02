#ifndef graphics_body_h
#define graphics_body_h

#include "body.h"
#include "graphicsLeg.h"

#include <Magnum/Math/Color.h>
#include <Magnum/ImGuiIntegration/Context.hpp>

using namespace Magnum;
using namespace Math::Literals;
// using namespace Math;

// Forward declarations
extern SceneGraph::DrawableGroup3D _drawables;
extern Scene3D _scene;

#define FIRST 1
#define SECOND 2
#define THIRD 3

#define IDLE 0
#define SCHEDULED 1
#define ENGAGED 2

class Phase {
public:
  int first; // Encoded status 
  int second; // Encoded status 
  int third; // Encoded status 

  // Default constructor that initializes name and status to default values
  Phase() : first(IDLE), second(IDLE), third(IDLE) {}  // Common convention for default values
  // Function to get a human-readable string for the status
  static const char* GetStatusString(int status) {
    switch (status) {
      case IDLE: return "Idle";
      case SCHEDULED: return "Scheduled";
      case ENGAGED: return "Engaged";
      default: return "Unknown";
    }
  }
};

Vector3 LegColors[] = {
    Vector3(255, 0, 0),     // Red
    Vector3(0, 255, 0),     // Green
    Vector3(0, 0, 255),     // Blue
    Vector3(255, 255, 0),   // Yellow
    Vector3(255, 0, 255),   // Magenta
    Vector3(0, 255, 255)    // Cyan
};

// Create GraphicsBody class that inherits from Body
class GraphicsBody : public Body {
public:
  // Constructor
  GraphicsBody(Color3 color) : Body() {
    _color = color;
    _scale = Vector3(10.1f);

    _position = Vector3(0.0f, 0.8f, 0.0f);

    // Initialize legs using arrays
    for (int i = 0; i < numLegs; i++) {
      legs[i] = new GraphicsLeg(LegColors[i] * Vector3(0.75f));
      initLeg(i);
    }

    initMeshDrawObject(std::string(MODELS_DIR) + "/body.stl");
    _meshrotation = Quaternion::rotation(-90.0_degf, Vector3::xAxis());
  }

  int jointAngles[18];

  void getAllJointAngles() {
    // Create a dynamically allocated array to store the joint angles

    jointAngles[0] = -1 * round(legs[2]->BaseJoint->_angle * (180.0 / M_PI));
    jointAngles[1] = round(legs[2]->SecondJoint->_angle * (180.0 / M_PI));
    jointAngles[2] = round(legs[2]->ThirdJoint->_angle * (180.0 / M_PI));

    jointAngles[3] = -1 * round(legs[1]->BaseJoint->_angle * (180.0 / M_PI));
    jointAngles[4] = round(legs[1]->SecondJoint->_angle * (180.0 / M_PI));
    jointAngles[5] = round(legs[1]->ThirdJoint->_angle * (180.0 / M_PI));

    jointAngles[6] = -1 * round(legs[0]->BaseJoint->_angle * (180.0 / M_PI));
    jointAngles[7] = round(legs[0]->SecondJoint->_angle * (180.0 / M_PI));
    jointAngles[8] = round(legs[0]->ThirdJoint->_angle * (180.0 / M_PI));

    jointAngles[9] =  180 - round(legs[5]->BaseJoint->_angle * (180.0 / M_PI));
    jointAngles[10] = round(legs[5]->SecondJoint->_angle * (180.0 / M_PI));
    jointAngles[11] = round(legs[5]->ThirdJoint->_angle * (180.0 / M_PI));

    jointAngles[12] = round(legs[4]->BaseJoint->_angle * (180.0 / M_PI));
    if (jointAngles[12] > 0)
      jointAngles[12] = 180 - jointAngles[12];
    else if (jointAngles[12] < 0)
      jointAngles[12] = -180 - jointAngles[12];
    
    jointAngles[13] = round(legs[4]->SecondJoint->_angle * (180.0 / M_PI));
    jointAngles[14] = round(legs[4]->ThirdJoint->_angle * (180.0 / M_PI));

    jointAngles[15] = -180 - round(legs[3]->BaseJoint->_angle * (180.0 / M_PI));
    jointAngles[16] = round(legs[3]->SecondJoint->_angle * (180.0 / M_PI));
    jointAngles[17] = round(legs[3]->ThirdJoint->_angle * (180.0 / M_PI));

    // Debug{} << legs[0]->BaseJoint->_angle;
  }

  std::string intArrayToString(int values[], int numValues) {
    std::stringstream ss;
      ss << "<";
      for (int i = 0; i < numValues; i++) {
          ss << values[i]; // Insert integer into stringstream
          if (i < numValues - 1) {
              ss << ":";
          }
      }
      ss << ">\n";
      return ss.str(); // Convert stringstream to string and return
  }

  void initLeg(int i) {
    legs[i]->_position = _position + legOffsetPositions[i];
    legs[i]->_endPose = legDesiredPoses[i];
    // legs[i]->_desiredPose = legDesiredPoses[i];
  }

  void updateLeg(int i){
    legs[i]->_position = _position + _rotation.transformVector(legOffsetPositions[i]);
    legs[i]->_rotation = _rotation;
  }

  bool CheckIfAnimationsFinished(){
    for (int i = 0; i < 6; i++){
      // Debug{} << legs[i]->_animationPlaying;
      if (legs[i]->_animationPlaying){
        return false;
      }
    }
    // if (_animationPlaying) return false;

    return true;
  }

  bool joysticksCentered = false;

  Phase phase;

  Quaternion deltaRotation;
  Vector3 deltaPosition;
  
  Quaternion phantomRotation;
  Vector3 phantomPosition;

  void WalkingMode(){
    if (controllerPointer->CheckIfJoysticksCentered()){
      joysticksCentered = true;
      // reset
      if (phase.first == SCHEDULED || phase.second == SCHEDULED){
        phase.first = IDLE;
        phase.second = IDLE;
        phase.third = SCHEDULED;
      }
    }
    else if (phase.first == IDLE && phase.second == IDLE && phase.third == IDLE){
      phase.first = SCHEDULED;
    }

    if (phase.first != IDLE || phase.second != IDLE || phase.third != IDLE) {
      joysticksCentered = false;

      // First Phase --------------
      if (phase.first == SCHEDULED){
        // Calculate desired positions of the first set based off currentPosition using the phantomPosition and phantomRotation
        // Store the phantom as deltaPosition and deltaRotation - in delta -
        float rotationMultiplier = 2 * asinf(_stepSize / 4.0f);
        deltaRotation = Quaternion::rotation(Rad(-rotationMultiplier * controllerPointer->rightJoystick.x()), Vector3::yAxis());
        deltaPosition = Vector3(
          controllerPointer->leftJoystick.x() * _stepSize, 
          0, 
          controllerPointer->leftJoystick.y() * _stepSize
        );
        // the idea is to treat the new rotation from the controller seperately and add it to the previous rotation
        deltaRotation = deltaRotation * _rotation;
        // while transforming the position using the new rotation and adding the current position (ignoring the height the body is off the ground)
        deltaPosition = deltaRotation.transformVector(deltaPosition) + Vector3(_position.x(), 0, _position.z());
        // Move first set to calculated desired positions
        for (int i = 0; i < 6; i++){
          if (_gaitOrder[i] == _gaitToggle){
            // apply the new rotation to the desired leg positions
            // then add the transformed position
            legs[i]->NewAnimation( deltaRotation.transformVector(legDesiredPoses[i]) + deltaPosition );
          }
        }
        phase.first = ENGAGED;
      }
      
      // Second Phase -------------
      if (phase.second == SCHEDULED){
        // Loop   --------
        // Calculate desired positions of the "toggle" set based off the delta and new phantom
        float rotationMultiplier = 2 * asinf(_stepSize / 4.0f);
        phantomRotation = Quaternion::rotation(Rad(-rotationMultiplier * controllerPointer->rightJoystick.x()), Vector3::yAxis());
        phantomPosition = Vector3(
          controllerPointer->leftJoystick.x() * _stepSize, 
          0, 
          controllerPointer->leftJoystick.y() * _stepSize
        );
        phantomPosition = (_rotation * phantomRotation).transformVector(phantomPosition);
        // Move "toggle" set to calculated desired positions
        for (int i = 0; i < 6; i++){
          if (_gaitOrder[i] == _gaitToggle){
            legs[i]->NewAnimation( deltaRotation.transformVector(legDesiredPoses[i]) + deltaPosition + phantomPosition);
          }
        }

        Math::Vector3<Rad> eulerAngles = phantomRotation.normalized().toEuler();
        eulerAngles[1] = eulerAngles[1] / 2;
        Quaternion a =
          Quaternion::rotation(eulerAngles[2], Vector3::zAxis())*
          Quaternion::rotation(eulerAngles[1], Vector3::yAxis())*
          Quaternion::rotation(eulerAngles[0], Vector3::xAxis());
        this->NewAnimation(Vector3(deltaPosition.x() + phantomPosition.x()/2, _position.y(), deltaPosition.z() + phantomPosition.z()/2), deltaRotation);

        phase.second = ENGAGED;
      }
      // Third Phase -------------
      if (phase.third == SCHEDULED){
        Vector3 _groundPosition = Vector3(
          _position.x(),
          0,
          _position.z()
        );
        for (int i = 0; i < 6; i++){
          if (_gaitOrder[i] == _gaitToggle){
            legs[i]->NewAnimation( _rotation.transformVector(legDesiredPoses[i]) + _groundPosition );
          }
        }

        phase.third = ENGAGED;
      }
      
      { // Phase Handler
        int counter = 0;
        for (int i = 0; i < 6; i++){
          if (legs[i]->_animationPlaying)
            counter++;
        }
        if (counter == 0){
          if (phase.first == ENGAGED){
            phase.second = SCHEDULED;
            phase.first = IDLE;

            _gaitToggle = 2;
          }
          if (phase.second == ENGAGED){
            phase.second = SCHEDULED;

            // _position = Vector3(deltaPosition.x() + phantomPosition.x()/2, _position.y(), deltaPosition.z() + phantomPosition.z()/2);
            deltaPosition += phantomPosition;

            deltaRotation = deltaRotation * phantomRotation;

            if (_gaitToggle==1) _gaitToggle = 2;
            else if (_gaitToggle==2) _gaitToggle = 1;
          }
          if (phase.third == ENGAGED){
            Vector3 _groundPosition = Vector3(
              _position.x(),
              0,
              _position.z()
            );
            counter = 0;
            for (int i = 0; i < 6; i++){
              Vector3 desiredPosition = _rotation.transformVector(legDesiredPoses[i]) + _groundPosition;
              if ((legs[i]->_endPose - desiredPosition).length() < 0.05f)
                counter++;
            }
            if (counter <= 5){
              phase.third = SCHEDULED;

              if (_gaitToggle==1) _gaitToggle = 2;
              else if (_gaitToggle==2) _gaitToggle = 1;
            }
            else phase.third = IDLE;
          }
        }
      }
    }
  }

  Vector3 defaultPosition;
  Quaternion defaultRotation;

  void StandingMode(){
    if (controllerPointer->CheckIfJoysticksCentered()){
      joysticksCentered = true;
      // Debug{} << _position.data()[0] << _position.data()[1] << _position.data()[2];
      _position.data()[0] = defaultPosition.x();
      _position.data()[2] = defaultPosition.z();

      // _rotation = defaultRotation;
    }
    else {
      Vector3 leftJoystick = Vector3(controllerPointer->leftJoystick.x(), 0.0f, controllerPointer->leftJoystick.y());
      Quaternion rightJoystick = 
          Quaternion::rotation(Rad(-controllerPointer->rightJoystick.y() * 0.28), Vector3::xAxis())
         *Quaternion::rotation(Rad(-controllerPointer->rightJoystick.x() * 0.28), Vector3::yAxis())
         *Quaternion::rotation(Rad(0), Vector3::zAxis());

      _position.data()[0] = defaultPosition.x() + defaultRotation.transformVector(leftJoystick).x() * 0.65;
      _position.data()[2] = defaultPosition.z() + defaultRotation.transformVector(leftJoystick).z() * 0.65;
      // Debug{} << controllerPointer->leftJoystick.x();

      _rotation = defaultRotation * rightJoystick;
    }
  }

  void update(Float deltaTime) {
    HandleAnimation(deltaTime);

    if (mode == WALKING) WalkingMode();
    if (mode == STANDING) StandingMode();

    // Update leg positions and rotations using arrays
    for (int i = 0; i < numLegs; i++) {
        updateLeg(i);
        legs[i]->update(deltaTime);
    }

    // Update the draw object for visualization
    updateDrawObject();
  }

  // Function to initialize the MeshDrawable for visualization
  void initMeshDrawObject(std::string meshFile) {
    _meshobject = new Object3D{&_scene};
    (*_meshobject)
      .setRotation(_rotation)
      .setTranslation(_position)
      .scale(_scale);

    // Create the MeshDrawable with the specified meshFile
    _meshdrawable = new MeshDrawable{*_meshobject, &_drawables, &_color, meshFile};
  }
  
  // Function to update the visual representation of the joint
  void updateDrawObject() {
    (*_meshobject)
      .setRotation(_rotation * _meshrotation)
      .setTranslation(_position + _rotation.transformVector(_meshposition))
      .setScaling(_scale);
  }

  float rotation[3] = {0.0f, 0.0f, 0.0f};
  float position[3] = {0.0f, 0.0f, 0.0f};

  void showBodyControl(){
    ImGui::Begin("Serial Debugging");
    
    for (int i = 0; i < 18; i++){
        std::string jointAngle = std::to_string(jointAngles[i]);
        ImGui::Text("%i: %s", i, jointAngle.c_str());
        
        // Add separator every 3rd joint
        if ((i + 1) % 3 == 0 && i < 17) {
            ImGui::Separator();
        }
    }

    ImGui::End();

    ImGui::Begin("Body Control");

    ImGui::SeparatorText("Body Position/Rotation");
    ImGui::PushItemWidth(120);
    
    position[0] = _position.x();
    position[1] = _position.y();
    position[2] = _position.z();
    if (ImGui::DragFloat3("Position - Body", position, 0.01f)){
    _position = Vector3(
        position[0],
        position[1],
        position[2]
    );
    }

    if(ImGui::DragFloat3("Rotation - Body", rotation, 0.01f)){
      Quaternion combinedRotation;
      combinedRotation = combinedRotation * Quaternion::rotation(Rad(rotation[0]), Vector3::xAxis()); 
      combinedRotation = combinedRotation * Quaternion::rotation(Rad(rotation[1]), Vector3::yAxis()); 
      combinedRotation = combinedRotation * Quaternion::rotation(Rad(rotation[2]), Vector3::zAxis());

      _rotation = combinedRotation;
    }

    ImGui::SeparatorText("Control");
    ImGui::DragFloat("Step Time", &_stepTime, 0.01f);

    ImGui::DragFloat("Step Size", &_stepSize, 0.01f);

    ImGui::DragFloat("Step Height", &_stepHeight, 0.001f);


    if (ImGui::DragFloat("Desired X", &desiredX, 0.001f) || ImGui::DragFloat("Desired Z", &desiredZ, 0.001f)){
      legDesiredPoses[0] = Vector3(desiredX, 0.0f, desiredZ);
      legDesiredPoses[1] = Vector3(desiredX * 1.333, 0.0f, 0.001f);
      legDesiredPoses[2] = Vector3(desiredX, 0.0f, -desiredZ);
      legDesiredPoses[3] = Vector3(-desiredX, 0.0f, desiredZ);
      legDesiredPoses[4] = Vector3(-desiredX * 1.333, 0.0f, 0.001f);
      legDesiredPoses[5] = Vector3(-desiredX, 0.0f, -desiredZ);
    }

    ImGui::End();

    for (int i = 0; i < 6; i++){
      legs[i]->showDebugging();
    }
  }

  void showPhases() {
    // Create a window
    ImGui::Begin("Status");

    ImGui::SeparatorText("Phase Status");
    // Temporary array to store status colors
    ImVec4 statusColors[4];
    statusColors[IDLE] = ImVec4(1.0f, 0.65f, 0.0f, 1.0f); // Orange
    statusColors[SCHEDULED] = ImVec4(0.0f, 1.0f, 0.0f, 1.0f); // Green
    statusColors[ENGAGED] = ImVec4(1.0f, 0.0f, 0.0f, 1.0f); // Red
    statusColors[3] = ImVec4(1.0f, 1.0f, 1.0f, 1.0f); // White (Unknown)

    // Display the status of each phase with color
    for (int i = 0; i < 3; ++i) {
      const char* phaseName = (i == 0) ? "Phase 1" : (i == 1) ? "Phase 2" : "Phase 3";
      int status = (i == 0) ? phase.first : (i == 1) ? phase.second : phase.third;
      ImGui::PushStyleColor(ImGuiCol_Text, statusColors[status]);
      ImGui::Text("%s: %s", phaseName, Phase::GetStatusString(status));
      ImGui::PopStyleColor();
    }

    ImGui::Spacing();

    ImGui::Text("Gait Toggle: %i", _gaitToggle);

    ImGui::SeparatorText("Leg Animation Status");
    ImGui::Columns(2);
    for (int i = 0; i < 3; i++){
      ImGui::Text("Leg %i: %s", i, boolToString(legs[i]->_animationPlaying).c_str());
    }
    ImGui::NextColumn();
    for (int i = 3; i < 6; i++){
      ImGui::Text("Leg %i: %s", i, boolToString(legs[i]->_animationPlaying).c_str());
    }
    ImGui::Columns(1);

    ImGui::SeparatorText("Control Status");
    ImGui::TextColored(ImVec4(0.65f, 0.65f, 1.0f, 1.0f), "Mode: %s", GetModeString(mode));

    // End the window
    ImGui::End();
  }

  const char *GetModeString(int mode){
    switch (mode) {
      case WALKING: return "Walking";
      case STANDING: return "Standing";
      default: return "Unknown";
    }
  }

  std::string boolToString(bool value) {
      return value ? "true" : "false";
  }

  void showGUI(){
    showBodyControl();
    showPhases();
  }

private:
  GraphicsLeg* legs[numLegs];

  Vector3 _scale;
  Color3 _color;

  // Graphics-related members
  Object3D* _meshobject;
  MeshDrawable* _meshdrawable;
  Vector3 _meshposition;
  Quaternion _meshrotation;
  
  bool showDebuggingWindow = false;
};

#endif