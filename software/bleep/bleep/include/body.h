#ifndef body_h
#define body_h

#include <Magnum/Math/Quaternion.h>
#include <Magnum/Math/Vector3.h>

#include <iostream>
#include <string>
#include <sstream>
#include <cmath>

#include <sstream>
#include <iomanip>

#include "leg.h"

#include "controller.h"

using namespace Magnum;
using namespace Math::Literals;

#define WALKING 0
#define STANDING 1

class Body {
public:
  // Constructor
  Body() {
    _position = Vector3(0.0f, 0.8f, 0.0f);

    // Initialize legs using arrays
    for (int i = 0; i < numLegs; i++) {
      legs[i] = new Leg();
      initLeg(i);
    }
  }

  void initLeg(int i) {
    legs[i]->_position = _position + legOffsetPositions[i];
    legs[i]->_endPose = legDesiredPoses[i];
  }

  void updateLeg(int i){
    legs[i]->_position = _position + _rotation.transformVector(legOffsetPositions[i]);
    legs[i]->_rotation = _rotation;
  }

  void update(Float deltaTime) {
    HandleAnimation(deltaTime);

    // Update leg positions and rotations using arrays
    for (int i = 0; i < numLegs; i++) {
      updateLeg(i);
      legs[i]->update(deltaTime);
    }

  }

  void NewAnimation(Vector3 desiredPose, Quaternion desiredRotation){
      _finalPose = desiredPose;
      _startPose = _position;
      _finalQuaternion = desiredRotation;
      _startQuaternion = _rotation;

      _animationPosePlaying = true;
      _animationRotationPlaying = true;

      rotationTime = 0;
      vectorTime = 0;
  }

  // Function to calculate the raw difference between angles
  double rawDifference(Rad angle1, Rad angle2) {
    return fmod(float(angle1) - float(angle2), 2 * M_PI); // Normalize to range (-2*PI, 2*PI)
  }

  // Function to find the smallest positive difference between angles on a circle
  double smallestPositiveDifference(Rad angle1, Rad angle2) {
    double difference = rawDifference(angle1, angle2);
    if (difference < 0) {
      difference += 2 * M_PI;
    }
    return difference;
  }

  float rotationTime = 0;
  float vectorTime = 0;

  void HandleAnimation(Float deltaTime){
    // if the distance from the desiredpose to the previouspose is greater than the distance to the currentendpose
    // then the endpose has not reached the desiredpose yet
    
    if (_animationPosePlaying){
        // (this->_finalAnimationPose - this->_previousEndPose).length() >= (this->_finalAnimationPose - this->_endPose).length()
        if (vectorTime / _stepTime <= 1.3){
        // if (Math::lerp(_finalAnimationPose, _previousEndPose, 0) >= Math::lerp(_finalAnimationPose, _endPose, 0)){
            // update the endpose position so that it is always "infront" of the previouspose
            vectorTime += deltaTime;
            float phase = (vectorTime / _stepTime);
            _position = Math::lerp(_startPose, _finalPose, phase);
        }
        if (vectorTime / _stepTime >= 1) {
            _animationPosePlaying = false;
        }
    }
        
    if (_animationRotationPlaying){
      if (rotationTime / _stepTime <= 1.3){
        // update the endpose position so that it is always "infront" of the previouspose
        rotationTime += deltaTime;
        float phase = (rotationTime / _stepTime);
        _rotation =  Math::lerpShortestPath(_startQuaternion, _finalQuaternion, phase);
      }
      if (rotationTime / _stepTime >= 1) {
        _animationRotationPlaying = false;
      }
    }
  }

  Quaternion minusRotation(Quaternion input1, Quaternion input2){
    Math::Vector3<Rad> eulerAngles1 = input1.normalized().toEuler();
    Math::Vector3<Rad> eulerAngles2 = input2.normalized().toEuler();
    Math::Vector3<Rad> eulerAnglesOutput = eulerAngles1 - eulerAngles2;

    Quaternion a =
      Quaternion::rotation(eulerAnglesOutput[2], Vector3::zAxis())*
      Quaternion::rotation(eulerAnglesOutput[1], Vector3::yAxis())*
      Quaternion::rotation(eulerAnglesOutput[0], Vector3::xAxis());

    return a;
  }


  // Constants for leg positions
  static constexpr int numLegs = 6;
  float x = 0.60f;
  float z = 0.86f;
  Vector3 legOffsetPositions[numLegs] = {
    Vector3(x, 0.0f, z),
    Vector3(x, 0.0f, 0.0f),
    Vector3(x, 0.0f, -z),
    Vector3(-x, 0.0f, z),
    Vector3(-x, 0.0f, 0.0f),
    Vector3(-x, 0.0f, -z)
  };

  // Constants for leg desired end effector poses
  float desiredX = 1.4f;
  float desiredZ = 1.6f;
  Vector3 legDesiredPoses[numLegs] = {
    Vector3(desiredX, 0.0f, desiredZ),
    Vector3(desiredX * 1.333, 0.0f, 0.001f),
    Vector3(desiredX, 0.0f, -desiredZ),
    Vector3(-desiredX, 0.0f, desiredZ),
    Vector3(-desiredX * 1.333, 0.0f, 0.001f),
    Vector3(-desiredX, 0.0f, -desiredZ)
  };


  // Array to hold leg instances
  Leg* legs[numLegs];

  Controller* controllerPointer;

  Quaternion _rotation;

  bool _animationPlaying = false;
  bool _animationPosePlaying = false;
  bool _animationRotationPlaying = false;

  int _gaitToggle = 1;
  int _gaitOrder[6] = {
    1, 2, 
    1, 2, 
    1, 2
  };

  Vector3 _position;

  Vector3 _startPose;
  Vector3 _finalPose;

  Quaternion _finalQuaternion;
  Quaternion _startQuaternion;

  int mode = STANDING;
};

#endif