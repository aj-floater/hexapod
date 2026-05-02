#ifndef joint_h
#define joint_h

#include <Magnum/Math/Quaternion.h>
#include <Magnum/Math/Vector3.h>

#include <iostream>
#include <string>
#include <sstream>
#include <cmath>

using namespace Magnum;
using namespace Math::Literals;

class Joint;

class Joint {
public:
    // Constructors
    Joint() : _length(0.0f), _child(nullptr) {
        // null constructor
    }

    Joint(Vector3 axisofrotation, Float length) 
        : _axisofrotation(axisofrotation), _length(length), _child(nullptr) 
    {

    }

    // Function to add a child joint to this joint
    Joint* addChild(Vector3 axisofrotation, Float length) {
      _child = new Joint(axisofrotation, length);
      return _child;
    }

    // Function to update the position and rotation of the joint
    void update(Vector3 position, Quaternion rotation) {
      // Update position and rotation code
      _rotation = rotation * Quaternion::rotation(Rad(_angle), _axisofrotation);
      _position = position;

      // Recursively update child joints
      if (_child) {
          position += _rotation.transformVector(_length * Vector3::xAxis());
          _child->update(position, _rotation);
      }
    }

    // Member variables
    Vector3 _position;
    Quaternion _rotation;

    Vector3 _axisofrotation;
    Float _angle;

    Float _length = 1.0f;
    Joint* _child;
};

#endif