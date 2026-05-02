#ifndef leg_h
#define leg_h

#include <Magnum/Timeline.h>
#include "joint.h"

#include <Magnum/Math/Quaternion.h>
#include <Magnum/Math/Vector3.h>

#include <iostream>
#include <string>
#include <sstream>
#include <cmath>

using namespace Magnum;
using namespace Math::Literals;

// Forward declarations
extern SceneGraph::DrawableGroup3D _drawables;
extern Scene3D _scene;

class Leg {
public:
    // Constructor
    Leg() {
        // Initialize features of base joint
        BaseJoint = new Joint(Vector3::yAxis(), 0.48f);
        // Initialize features of second joint
        BaseJoint->addChild(Vector3::zAxis(), 0.6f);
        SecondJoint = BaseJoint->_child;
        // Initialize features of third joint
        SecondJoint->addChild(Vector3::zAxis(), 1.3f);
        ThirdJoint = SecondJoint->_child;

        // BaseJoint->_length = 0.48f;

        // SecondJoint->_length = 0.6f;
        // SecondJoint->_axisofrotation = Vector3::zAxis();

        // ThirdJoint->_length = 1.3f;
        // ThirdJoint->_axisofrotation = Vector3::zAxis();
    }

    // Function to update the leg
    void update(float deltaTime) {
        HandleAnimation(deltaTime);

        // Calculate the inverse kinematics
        if (showIK)
            CalculateIK();

        // Propagate throughout all joints in the leg
        // to calculate the forward kinematics given the individual joint angles
        BaseJoint->update(_position, _rotation);
    }

    void CalculateIK(){
        Vector3 startPosition = _position;
        Vector3 endPosition = _endPose;

        Quaternion _invertedRotation = _rotation.inverted();
        endPosition = _invertedRotation.transformVector(endPosition);
        startPosition = _invertedRotation.transformVector(startPosition);
        
        Vector3 deltaPosition = endPosition - startPosition;


        Float angle_1 = atan2f(deltaPosition.z(), deltaPosition.x());

        Float x = (endPosition.z()/sinf(angle_1)) - ((startPosition.z()/sinf(angle_1)) + BaseJoint->_length);
        if (startPosition.z() == endPosition.z())
            x = (endPosition.x()/cosf(angle_1)) - ((startPosition.x()/cosf(angle_1)) + BaseJoint->_length);

        Float y = - deltaPosition.y();

        Float l1 = SecondJoint->_length;
        Float l2 = ThirdJoint->_length;

        // Calculate angle 2
        Float angle_3 = acosf((- powf(l1, 2) - powf(l2, 2) + powf(x, 2) + powf(y, 2))/(2*l1*l2));
        
        // Calculate angle 1
        Float angle_2 = atan2f(y,x) - atan2f((l2*sinf(angle_3)),(l1+l2*cosf(angle_3)));

        if (!std::isnan(angle_1) && !std::isnan(angle_2) && !std::isnan(angle_3)){
            SecondJoint->_angle = - angle_2;
            ThirdJoint->_angle = - angle_3;
        }
        BaseJoint->_angle = - angle_1;
    }

    void NewAnimation(Vector3 desiredPose){
        _startPose = _endPose;
        _finalAnimationPose = desiredPose;

        _animationPlaying = true;

        vectorTime = 0;
    }

    float vectorTime = 0;

    void HandleAnimation(Float deltaTime){
        // if the distance from the desiredpose to the previouspose is greater than the distance to the currentendpose
        // then the endpose has not reached the desiredpose yet
        
        if (_animationPlaying){
            // (this->_finalAnimationPose - this->_previousEndPose).length() >= (this->_finalAnimationPose - this->_endPose).length()
            if (vectorTime / _stepTime <= 1.3){
            // if (Math::lerp(_finalAnimationPose, _previousEndPose, 0) >= Math::lerp(_finalAnimationPose, _endPose, 0)){
                // update the endpose position so that it is always "infront" of the previouspose
                vectorTime += deltaTime;
                float phase = (vectorTime / _stepTime);
                // Adding step height
                Vector3 endPoseHeight;
                if (phase < 0.5){
                    float easeOutPhase = - 4*powf(phase,2) + 4*phase;
                    endPoseHeight = Math::lerp(Vector3(0), Vector3(0, _stepHeight, 0), Math::clamp(easeOutPhase, 0.0f, 1.0f));
                }
                else if (phase > 0.5){
                    float easeOutPhase = - 4*powf(phase,2) + 4*phase;
                    endPoseHeight = Math::lerp(Vector3(0, _stepHeight, 0), Vector3(0), Math::clamp(1-easeOutPhase, 0.0f, 1.0f));
                }
                else endPoseHeight = Vector3(0.0f);

                // Finalise endposition
                _endPose = Math::lerp(_startPose, _finalAnimationPose, phase) + endPoseHeight;
            }
            if (vectorTime / _stepTime >= 1){
                _animationPlaying = false;
            }
        }
    }

    // Member variables
    Joint* BaseJoint;
    Joint* SecondJoint;
    Joint* ThirdJoint;

    Joint* DesiredJoint;

    bool _animationPlaying = false;
    Vector3 _endPose;
    Vector3 _startPose;

    Vector3 _travelVector;
    Vector3 _finalAnimationPose;

    Vector3 _deltaVector;

    Quaternion _rotation;
    Vector3 _position;

    bool showIK = true;
};

#endif